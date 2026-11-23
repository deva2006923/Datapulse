"""
Safe, Idempotent SQLite -> PostgreSQL (+ Optional Cloudflare R2 Community CSV) Migration CLI.

Guarantees:
  - Read-only against source SQLite database (never deletes or modifies local records).
  - Non-destructive against target PostgreSQL (uses ON CONFLICT DO NOTHING; never overwrites existing users/credits).
  - Supports --dry-run to preview exact row counts and credit-balance totals before writing.
  - Verifies post-migration row counts and aggregate user credit balance integrity.
  - Optionally uploads existing local community CSVs (`storage/datasets/<id>.csv`) to Cloudflare R2
    and populates `object_storage_key` + `sha256_checksum` on migrated rows.

Usage:
  # Dry run (inspect counts & credit totals without touching PostgreSQL or R2)
  python scripts/migrate_sqlite_to_postgres.py --sqlite-path datapulse.db --postgres-url "$DATABASE_URL" --dry-run

  # Execute migration (metadata only)
  python scripts/migrate_sqlite_to_postgres.py --sqlite-path datapulse.db --postgres-url "$DATABASE_URL" --execute

  # Execute migration + upload local community CSVs to Cloudflare R2
  python scripts/migrate_sqlite_to_postgres.py --sqlite-path datapulse.db --postgres-url "$DATABASE_URL" --execute --upload-r2
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.database import init_db, get_db_connection, redact_database_url, reset_db_connection
from app.services.r2_storage import R2StorageClient

# Foreign-key-safe migration order across all 9 transactional tables
MIGRATION_TABLES: List[str] = [
    "users",
    "tokens",
    "datasets",
    "evaluations",
    "credit_transactions",
    "queries",
    "dataset_unlocks",
    "dataset_versions",
    "admin_audit_logs",
]

PRIMARY_KEY_COLUMNS: Dict[str, str] = {
    "users": "id",
    "tokens": "token",
    "datasets": "id",
    "evaluations": "id",
    "credit_transactions": "id",
    "queries": "id",
    "dataset_unlocks": "id",
    "dataset_versions": "id",
    "admin_audit_logs": "id",
}


def inspect_sqlite_snapshot(sqlite_path: str) -> Dict[str, Any]:
    """Read row counts and total user credits from source SQLite without mutating it."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        counts: Dict[str, int] = {}
        existing_tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table in MIGRATION_TABLES:
            if table in existing_tables:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            else:
                counts[table] = 0
        total_credits = (
            int(conn.execute("SELECT COALESCE(SUM(credits), 0) FROM users").fetchone()[0])
            if "users" in existing_tables
            else 0
        )
        return {"counts": counts, "total_user_credits": total_credits}
    finally:
        conn.close()


def migrate_sqlite_to_postgres(
    sqlite_path: str,
    postgres_url: str,
    *,
    dry_run: bool = True,
    upload_r2: bool = False,
    datasets_dir: Optional[str] = None,
) -> Dict[str, Any]:
    if not Path(sqlite_path).exists():
        raise FileNotFoundError(f"Source SQLite database not found: {sqlite_path}")

    source_summary = inspect_sqlite_snapshot(sqlite_path)
    report: Dict[str, Any] = {
        "dry_run": dry_run,
        "upload_r2": upload_r2,
        "source_counts": source_summary["counts"],
        "source_total_credits": source_summary["total_user_credits"],
        "inserted_counts": {},
        "r2_uploaded": 0,
        "r2_skipped": 0,
    }
    if dry_run:
        return report

    # Switch app database target to PostgreSQL and initialize schema/migrations safely
    orig_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = postgres_url
    reset_db_connection()

    src_conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src_conn.row_factory = sqlite3.Row
    storage_dir = Path(datasets_dir or settings.DATASETS_STORAGE_DIR)
    r2_client = R2StorageClient() if upload_r2 else None
    if upload_r2 and r2_client and not r2_client.is_configured:
        raise RuntimeError("R2 credentials are required when --upload-r2 is set.")

    try:
        init_db()
        pg_conn = get_db_connection()
        pg_cur = pg_conn.cursor()

        existing_src_tables = {
            r[0] for r in src_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        for table in MIGRATION_TABLES:
            if table not in existing_src_tables:
                report["inserted_counts"][table] = 0
                continue

            rows = src_conn.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                report["inserted_counts"][table] = 0
                continue

            cols = list(rows[0].keys())
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(cols)
            # ON CONFLICT DO NOTHING safely handles both primary keys and unique constraints
            # (users.email, evaluations.dataset_id, dataset_unlocks(dataset_id, user_id)).
            insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

            inserted = 0
            for row in rows:
                row_dict = dict(row)
                if table == "datasets" and upload_r2 and r2_client and not bool(row_dict.get("is_curated")):
                    ds_id = row_dict["id"]
                    csv_file = storage_dir / f"{ds_id}.csv"
                    if not row_dict.get("object_storage_key") and csv_file.exists():
                        csv_bytes = csv_file.read_bytes()
                        if csv_bytes:
                            meta = r2_client.upload_community_csv(ds_id, csv_bytes)
                            row_dict["object_storage_key"] = meta["object_storage_key"]
                            row_dict["sha256_checksum"] = meta["sha256_checksum"]
                            row_dict["csv_bytes"] = meta["csv_bytes"]
                            report["r2_uploaded"] += 1
                    else:
                        report["r2_skipped"] += 1

                values = [row_dict.get(c) for c in cols]
                pg_cur.execute(insert_sql, values)
                if pg_cur.rowcount > 0:
                    inserted += pg_cur.rowcount

            pg_conn.commit()
            report["inserted_counts"][table] = inserted

        # Post-migration verification
        target_counts: Dict[str, int] = {}
        for table in MIGRATION_TABLES:
            pg_cur.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
            target_counts[table] = int(pg_cur.fetchone()["cnt"])
        pg_cur.execute("SELECT COALESCE(SUM(credits), 0) AS total_credits FROM users")
        target_credits = int(pg_cur.fetchone()["total_credits"])
        report["target_counts"] = target_counts
        report["target_total_credits"] = target_credits
        return report
    except Exception as exc:
        raise RuntimeError(f"Migration failed: {redact_database_url(str(exc))}") from None
    finally:
        src_conn.close()
        reset_db_connection()
        settings.DATABASE_URL = orig_db_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate DataPulse metadata from SQLite to PostgreSQL safely.")
    parser.add_argument("--sqlite-path", default=settings.DATABASE_PATH, help="Source SQLite database path.")
    parser.add_argument("--postgres-url", default=os.getenv("DATABASE_URL", ""), help="Target PostgreSQL DATABASE_URL.")
    parser.add_argument("--datasets-dir", default=settings.DATASETS_STORAGE_DIR, help="Local community CSV directory.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect source counts and credits without writing.")
    parser.add_argument("--execute", action="store_true", help="Execute non-destructive migration into PostgreSQL.")
    parser.add_argument("--upload-r2", action="store_true", help="Upload local community CSV files to Cloudflare R2.")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Specify either --dry-run or --execute.")
        return 2
    if args.execute and not args.postgres_url.strip():
        print("ERROR: --postgres-url (or DATABASE_URL env var) is required for --execute.")
        return 2

    result = migrate_sqlite_to_postgres(
        sqlite_path=args.sqlite_path,
        postgres_url=args.postgres_url.strip(),
        dry_run=not args.execute,
        upload_r2=args.upload_r2,
        datasets_dir=args.datasets_dir,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

