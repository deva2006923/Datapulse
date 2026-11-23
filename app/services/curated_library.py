"""
DataPulse Curated Public Dataset Library Service.

Responsibilities:
  1. Idempotently provision the dedicated `DataPulse Curated Library` system owner
     (separate from the Platform Admin account; 0 credits; un-loginable password hash).
  2. Synchronize `data/curated_manifest.json` metadata into SQLite on startup without
     downloading CSV files, without duplicating records, and without overwriting
     community datasets.
  3. On-demand DuckDB hydration from Cloudflare R2 with single-flight per-dataset
     concurrency locking, mandatory SHA-256 checksum verification, CSV safety
     validation, bounded 200 MB / 25-table LRU cache eviction, and automatic rollback
     on partial failure.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import get_db_connection
from app.services.evaluation import parse_and_evaluate_csv
from app.services.r2_storage import (
    R2ChecksumMismatchError,
    R2ConfigurationError,
    R2ObjectNotFoundError,
    R2SizeLimitError,
    R2StorageClient,
    R2StorageError,
    validate_curated_object_key,
    validate_dataset_object_key,
)
from app.services.storage import (
    DATASET_ID_REGEX,
    dataset_table_exists,
    delete_dataset_storage,
    evict_curated_cache_if_needed,
    get_dataset_columns,
    get_dataset_row_count,
    persist_dataset,
    record_curated_hydration,
    touch_curated_cache_entry,
)

logger = logging.getLogger("datapulse.curated")

CURATED_OWNER_ID = "usr_system_curated_library"
CURATED_OWNER_EMAIL = "curated-library@datapulse.internal"
CURATED_OWNER_NAME = "DataPulse Curated Library"

VALID_CURATED_INGESTION_STATUSES = {"pending_ingestion", "ingested", "failed"}
_SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")
_SYNTHETIC_TEST_ID_PREFIX = "ds_cur_ing_e2e_"

_hydration_locks_guard = threading.Lock()
_hydration_locks: Dict[str, threading.Lock] = {}


def resolve_curated_data_dir(data_dir: Optional[str | Path] = None) -> Path:
    """Resolve the configured packaged curated CSV directory (defaults to `data/curated`)."""
    raw = data_dir if data_dir is not None else (getattr(settings, "CURATED_DATA_DIR", None) or "data/curated")
    p = Path(raw)
    if p.is_absolute():
        return p
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / p
    if candidate.exists():
        return candidate
    cwd_candidate = Path.cwd() / p
    if cwd_candidate.exists():
        return cwd_candidate
    return candidate


def resolve_packaged_curated_csv_path(
    dataset_id: str,
    data_dir: Optional[str | Path] = None,
) -> Path:
    """
    Strictly resolve a packaged curated CSV path inside `CURATED_DATA_DIR` from a validated dataset_id.
    Prevents path traversal, subdirectories, and symlink escapes outside the curated data directory.
    """
    ds_id = (dataset_id or "").strip()
    if (
        not ds_id
        or not ds_id.startswith("ds_cur_")
        or len(ds_id) > 64
        or "/" in ds_id
        or "\\" in ds_id
        or ".." in ds_id
        or not DATASET_ID_REGEX.match(ds_id)
    ):
        raise ValueError(f"Invalid curated dataset identifier: {dataset_id!r}")

    base_dir = resolve_curated_data_dir(data_dir).resolve()
    candidate = (base_dir / f"{ds_id}.csv").resolve()
    if candidate.parent != base_dir or candidate.name != f"{ds_id}.csv":
        raise ValueError(f"Curated dataset path escaped curated data directory for '{ds_id}'.")
    return candidate


def has_packaged_curated_csv(
    dataset_id: str,
    data_dir: Optional[str | Path] = None,
) -> bool:
    """Return True if a validated packaged curated CSV exists on disk inside `CURATED_DATA_DIR`."""
    try:
        path = resolve_packaged_curated_csv_path(dataset_id, data_dir=data_dir)
    except ValueError:
        return False
    return path.is_file()


class CuratedHydrationError(Exception):
    """Raised when a curated dataset cannot be safely hydrated for query execution."""

    def __init__(self, message: str, status_code: int = 503):
        self.status_code = status_code
        super().__init__(message)


def _get_hydration_lock(dataset_id: str) -> threading.Lock:
    with _hydration_locks_guard:
        lock = _hydration_locks.get(dataset_id)
        if lock is None:
            lock = threading.Lock()
            _hydration_locks[dataset_id] = lock
        return lock


def ensure_curated_system_owner(conn=None) -> Dict[str, Any]:
    """
    Safely and idempotently ensure the dedicated DataPulse Curated Library system owner exists.
    - Never uses or modifies the platform administrator account.
    - Holds 0 credits and creates 0 credit_transactions rows.
    - Uses an un-loginable disabled password sentinel so no password can authenticate as this user.
    """
    if conn is None:
        conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, email, full_name, credits, is_admin FROM users WHERE id = ? OR LOWER(email) = ? LIMIT 1",
        (CURATED_OWNER_ID, CURATED_OWNER_EMAIL),
    )
    existing = cursor.fetchone()
    if existing:
        return {
            "id": existing["id"],
            "email": existing["email"],
            "full_name": existing["full_name"],
            "status": "existing",
        }

    now = datetime.datetime.utcnow().isoformat()
    # Non-PBKDF2 / non-hex sentinel guaranteed to never match verify_password()
    disabled_hash = f"!system_disabled!{secrets.token_hex(32)}"
    cursor.execute(
        """
        INSERT INTO users (id, email, password_hash, full_name, credits, reputation_score, is_admin, created_at)
        VALUES (?, ?, ?, ?, 0, 100, 0, ?)
        """,
        (CURATED_OWNER_ID, CURATED_OWNER_EMAIL, disabled_hash, CURATED_OWNER_NAME, now),
    )
    conn.commit()
    logger.info("Provisioned dedicated curated system owner '%s' (%s).", CURATED_OWNER_NAME, CURATED_OWNER_ID)
    return {
        "id": CURATED_OWNER_ID,
        "email": CURATED_OWNER_EMAIL,
        "full_name": CURATED_OWNER_NAME,
        "status": "created",
    }


def _resolve_manifest_path(manifest_path: Optional[str | Path] = None) -> Path:
    raw = manifest_path or settings.CURATED_MANIFEST_PATH or "data/curated_manifest.json"
    p = Path(raw)
    if p.is_absolute():
        return p
    # Resolve relative to repo root (two levels above app/services/curated_library.py)
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / p
    if candidate.exists():
        return candidate
    return Path.cwd() / p


def load_curated_manifest(manifest_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Load and structurally validate `data/curated_manifest.json` (zero network calls)."""
    path = _resolve_manifest_path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Curated manifest file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("datasets"), list):
        raise ValueError("Curated manifest must be a JSON object containing a 'datasets' list.")

    seen_ids = set()
    for idx, entry in enumerate(payload["datasets"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest entry #{idx} must be a JSON object.")
        ds_id = (entry.get("dataset_id") or "").strip()
        if not ds_id.startswith("ds_cur_") or len(ds_id) > 64 or not DATASET_ID_REGEX.match(ds_id):
            raise ValueError(f"Manifest entry #{idx} has invalid curated dataset_id: {ds_id!r}")
        if ds_id in seen_ids:
            raise ValueError(f"Duplicate dataset_id in curated manifest: {ds_id!r}")
        seen_ids.add(ds_id)
        if not entry.get("license_verified"):
            raise ValueError(f"Manifest entry '{ds_id}' is not explicitly marked license_verified=true.")
        if not (entry.get("license") or "").strip() or not (entry.get("source_url") or "").strip():
            raise ValueError(f"Manifest entry '{ds_id}' is missing required license or source_url.")
        status = (entry.get("ingestion_status") or "pending_ingestion").strip().lower()
        if status not in VALID_CURATED_INGESTION_STATUSES:
            raise ValueError(f"Manifest entry '{ds_id}' has invalid ingestion_status: {status!r}")
    return payload


def sync_curated_manifest(
    manifest_path: Optional[str | Path] = None,
    conn=None,
    curated_data_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Idempotently synchronize curated dataset metadata from `data/curated_manifest.json`
    into the relational catalog (`datasets` and `evaluations`, PostgreSQL or SQLite).

    Guarantees:
      - Zero CSV downloads during startup.
      - Zero duplicate records on repeated restarts.
      - Never overwrites or modifies any community dataset (`is_curated = 0`).
      - Never registers synthetic E2E test entries.
      - Always enforces `unlock_price = 0` and `credits_awarded = 0` with zero credit transactions.
    """
    path = _resolve_manifest_path(manifest_path)
    if not path.exists():
        logger.warning("Curated manifest not found at %s; skipping curated metadata sync.", path)
        return {"synced": 0, "inserted": 0, "updated": 0, "skipped_conflicts": 0, "status": "manifest_missing"}

    manifest = load_curated_manifest(path)
    if conn is None:
        conn = get_db_connection()

    owner = ensure_curated_system_owner(conn=conn)
    owner_id = owner["id"]
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    inserted = 0
    updated = 0
    skipped_conflicts = 0

    for entry in manifest["datasets"]:
        ds_id = entry["dataset_id"].strip()
        if ds_id.startswith(_SYNTHETIC_TEST_ID_PREFIX):
            logger.warning("Skipping synthetic E2E test dataset entry '%s' during manifest sync.", ds_id)
            continue
        name = (entry.get("name") or ds_id).strip()
        filename = os.path.basename((entry.get("filename") or f"{ds_id}.csv").replace("\\", "/"))
        domain = (entry.get("domain") or "General & Research").strip()
        summary = (entry.get("content_summary") or f"Curated public dataset in {domain}.").strip()
        source_name = (entry.get("source_name") or "").strip()
        source_url = (entry.get("source_url") or "").strip()
        license_name = (entry.get("license") or "").strip()
        license_url = (entry.get("license_url") or "").strip() or None
        source_version = (entry.get("source_version") or "v1").strip()
        ingestion_status = (entry.get("ingestion_status") or "pending_ingestion").strip().lower()
        retrieved_at = entry.get("retrieved_at")
        object_storage_key = entry.get("object_storage_key")
        sha256_checksum = (entry.get("sha256_checksum") or "").strip().lower() or None
        csv_bytes = int(entry.get("csv_bytes") or 0)
        rows_count = int(entry.get("rows_count") or 0)
        columns_count = int(entry.get("columns_count") or 0)
        schema_obj = entry.get("schema_json") if isinstance(entry.get("schema_json"), dict) else {}
        schema_json_str = json.dumps(schema_obj)
        created_at = retrieved_at or now

        quality_score = float(entry.get("quality_score") or (95.0 if ingestion_status == "ingested" else 0.0))
        fidelity_score = float(entry.get("schema_fidelity_score") or quality_score)
        completeness_score = float(entry.get("completeness_score") or quality_score)
        relevance_score = float(entry.get("domain_relevance_score") or (90.0 if ingestion_status == "ingested" else 0.0))
        overall_score = float(entry.get("overall_score") or quality_score)
        eval_status = "completed" if ingestion_status == "ingested" else "pending"
        eval_progress = 100 if ingestion_status == "ingested" else 0

        cursor.execute("SELECT id, is_curated, created_at, ingestion_status, sha256_checksum, rows_count, columns_count, csv_bytes, object_storage_key FROM datasets WHERE id = ? LIMIT 1", (ds_id,))
        existing = cursor.fetchone()
        if existing:
            if not bool(existing["is_curated"]):
                logger.warning(
                    "Curated sync refused to overwrite community dataset '%s' (is_curated=0).",
                    ds_id,
                )
                skipped_conflicts += 1
                continue

            # A stale manifest (for example, still marked pending_ingestion) must not
            # downgrade a previously validated packaged curated CSV during application startup.
            try:
                local_csv_path = resolve_packaged_curated_csv_path(ds_id, data_dir=curated_data_dir)
            except ValueError:
                local_csv_path = None
            if (
                ingestion_status != "ingested"
                and str(existing["ingestion_status"] or "").lower() == "ingested"
                and local_csv_path is not None
                and local_csv_path.is_file()
                and existing["sha256_checksum"]
            ):
                try:
                    local_digest = hashlib.sha256(local_csv_path.read_bytes()).hexdigest()
                except OSError:
                    local_digest = ""
                if local_digest and hmac.compare_digest(local_digest, str(existing["sha256_checksum"]).lower()):
                    updated += 1
                    continue

            cursor.execute(
                """
                UPDATE datasets
                SET user_id = ?, name = ?, filename = ?, domain = ?, rows_count = ?, columns_count = ?,
                    schema_json = ?, content_summary = ?, unlock_price = 0, content_hash = ?,
                    is_curated = 1, dataset_type = 'curated', source_name = ?, source_url = ?,
                    license = ?, license_url = ?, retrieved_at = ?, object_storage_key = ?,
                    sha256_checksum = ?, ingestion_status = ?, source_version = ?, csv_bytes = ?
                WHERE id = ? AND is_curated = 1
                """,
                (
                    owner_id, name, filename, domain, rows_count, columns_count,
                    schema_json_str, summary, sha256_checksum,
                    source_name, source_url, license_name, license_url, retrieved_at,
                    object_storage_key, sha256_checksum, ingestion_status, source_version, csv_bytes,
                    ds_id,
                ),
            )
            cursor.execute(
                """
                UPDATE evaluations
                SET status = ?, progress = ?, quality_score = ?, schema_fidelity_score = ?,
                    completeness_score = ?, domain_relevance_score = ?, overall_score = ?,
                    credits_awarded = 0, updated_at = ?
                WHERE dataset_id = ?
                """,
                (
                    eval_status, eval_progress, quality_score, fidelity_score,
                    completeness_score, relevance_score, overall_score, now, ds_id,
                ),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO datasets (
                    id, user_id, name, filename, domain, rows_count, columns_count,
                    schema_json, content_summary, unlock_price, content_hash, created_at,
                    is_curated, dataset_type, source_name, source_url, license, license_url,
                    retrieved_at, object_storage_key, sha256_checksum, ingestion_status,
                    source_version, csv_bytes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1, 'curated', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ds_id, owner_id, name, filename, domain, rows_count, columns_count,
                    schema_json_str, summary, sha256_checksum, created_at,
                    source_name, source_url, license_name, license_url,
                    retrieved_at, object_storage_key, sha256_checksum, ingestion_status,
                    source_version, csv_bytes,
                ),
            )
            eval_id = f"eval_{uuid.uuid4().hex[:12]}"
            cursor.execute(
                """
                INSERT INTO evaluations (
                    id, dataset_id, status, progress, quality_score, schema_fidelity_score,
                    completeness_score, domain_relevance_score, overall_score, credits_awarded,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    eval_id, ds_id, eval_status, eval_progress, quality_score, fidelity_score,
                    completeness_score, relevance_score, overall_score, created_at, now,
                ),
            )
            inserted += 1

    conn.commit()
    total_synced = inserted + updated
    logger.info(
        "Curated manifest sync complete: %d synced (%d inserted, %d updated, %d skipped conflicts).",
        total_synced,
        inserted,
        updated,
        skipped_conflicts,
    )
    return {
        "status": "ok",
        "manifest_version": manifest.get("manifest_version"),
        "synced": total_synced,
        "inserted": inserted,
        "updated": updated,
        "skipped_conflicts": skipped_conflicts,
    }


def ensure_curated_dataset_hydrated(
    dataset_row: Dict[str, Any],
    r2_client: Optional[R2StorageClient] = None,
    max_cache_bytes: Optional[int] = None,
    max_cache_tables: Optional[int] = None,
    curated_data_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Ensure a curated dataset is safely hydrated in DuckDB before query execution.

    Retrieval priority:
      1. Fast-path DuckDB LRU cache hit (verified matching SHA-256).
      2. Local packaged CSV in `CURATED_DATA_DIR` (default `data/curated/<dataset_id>.csv`) —
         NO Cloudflare R2 credentials required.
      3. Optional Cloudflare R2 fallback ONLY when the packaged local CSV is absent AND
         an `object_storage_key` is registered AND R2 credentials are explicitly configured.

    Safety guarantees:
      - Rejects un-ingested / unverified entries (never executes against partial data).
      - Strictly resolves packaged CSVs by validated `dataset_id` within `CURATED_DATA_DIR`.
      - Uses a per-dataset single-flight lock so concurrent requests hydrate once.
      - Verifies SHA-256 checksum in constant time before trusting any CSV bytes.
      - Validates CSV formatting, formula-injection sanitization, and hard row/size limits.
      - Enforces bounded 200 MB / 25-table curated LRU cache (never evicts community datasets).
      - Cleans up partial storage artifacts automatically on any failure.
    """
    dataset_id = str(dataset_row.get("id") or "").strip()
    try:
        local_csv_path = resolve_packaged_curated_csv_path(dataset_id, data_dir=curated_data_dir)
    except ValueError as exc:
        raise CuratedHydrationError(f"Invalid curated dataset identifier: '{dataset_id}'", status_code=400) from exc

    ingestion_status = str(dataset_row.get("ingestion_status") or "").strip().lower()
    object_key = (dataset_row.get("object_storage_key") or "").strip()
    expected_sha256 = (dataset_row.get("sha256_checksum") or "").strip().lower()

    if ingestion_status != "ingested" or not expected_sha256 or not _SHA256_HEX_RE.match(expected_sha256):
        raise CuratedHydrationError(
            f"Curated dataset '{dataset_id}' has not completed ingestion or has an invalid checksum "
            f"(status={ingestion_status or 'unknown'}).",
            status_code=503,
        )

    # Prefer packaged local CSV first (zero R2 dependency); fall back to R2 only if absent & configured
    use_local_file = local_csv_path.is_file()
    safe_key: Optional[str] = None
    if not use_local_file:
        if object_key:
            try:
                safe_key = validate_curated_object_key(object_key)
            except ValueError as exc:
                raise CuratedHydrationError(
                    f"Curated dataset '{dataset_id}' has invalid object storage key.", status_code=500
                ) from exc
        else:
            raise CuratedHydrationError(
                f"Packaged CSV file for curated dataset '{dataset_id}' is missing from curated data directory.",
                status_code=404,
            )

    hard_max_bytes = max(1, int(settings.CURATED_HARD_MAX_MB)) * 1024 * 1024
    hard_max_rows = max(1, int(settings.CURATED_HARD_MAX_ROWS))

    lock = _get_hydration_lock(dataset_id)
    with lock:
        # 1. Fast path: already hydrated in DuckDB with matching SHA-256 checksum
        if dataset_table_exists(dataset_id):
            cached_sha = touch_curated_cache_entry(dataset_id)
            if cached_sha and hmac.compare_digest(cached_sha.lower(), expected_sha256):
                return {
                    "dataset_id": dataset_id,
                    "status": "cache_hit",
                    "rows_count": get_dataset_row_count(dataset_id),
                }

        # 2. Retrieve bytes from local packaged CSV first, or optional R2 fallback when configured
        if use_local_file:
            try:
                file_size = local_csv_path.stat().st_size
                if file_size <= 0:
                    raise CuratedHydrationError(
                        f"Packaged curated CSV for '{dataset_id}' is empty.",
                        status_code=422,
                    )
                if file_size > hard_max_bytes:
                    raise CuratedHydrationError(
                        f"Curated dataset '{dataset_id}' exceeds the configured size ceiling.",
                        status_code=413,
                    )
                csv_bytes = local_csv_path.read_bytes()
            except CuratedHydrationError:
                raise
            except OSError as exc:
                raise CuratedHydrationError(
                    f"Unable to read packaged curated CSV for '{dataset_id}'.", status_code=503
                ) from exc
            actual_sha256 = hashlib.sha256(csv_bytes).hexdigest()
            if not hmac.compare_digest(actual_sha256, expected_sha256):
                raise CuratedHydrationError(
                    f"Curated dataset '{dataset_id}' failed packaged CSV SHA-256 integrity verification.",
                    status_code=502,
                )
        else:
            client = r2_client or R2StorageClient()
            if not getattr(client, "is_configured", True):
                raise CuratedHydrationError(
                    f"Packaged CSV file for curated dataset '{dataset_id}' is missing and optional Cloudflare R2 fallback is not configured.",
                    status_code=503,
                )
            try:
                csv_bytes = client.download_and_verify_csv(
                    object_storage_key=safe_key,
                    expected_sha256=expected_sha256,
                    max_uncompressed_bytes=hard_max_bytes,
                )
            except R2ConfigurationError as exc:
                raise CuratedHydrationError(str(exc), status_code=503) from exc
            except R2ObjectNotFoundError as exc:
                raise CuratedHydrationError(
                    f"Curated dataset '{dataset_id}' object is missing from Cloudflare R2.",
                    status_code=404,
                ) from exc
            except R2ChecksumMismatchError as exc:
                raise CuratedHydrationError(
                    f"Curated dataset '{dataset_id}' failed integrity checksum verification.",
                    status_code=502,
                ) from exc
            except R2SizeLimitError as exc:
                raise CuratedHydrationError(str(exc), status_code=413) from exc
            except R2StorageError as exc:
                raise CuratedHydrationError(
                    f"Failed to retrieve curated dataset '{dataset_id}' from object storage: {exc}",
                    status_code=503,
                ) from exc

        # 3. Validate & sanitize CSV before DuckDB ingestion
        csv_text = csv_bytes.decode("utf-8", errors="replace")
        filename = str(dataset_row.get("filename") or f"{dataset_id}.csv")
        domain = str(dataset_row.get("domain") or "General & Research")
        parsed = parse_and_evaluate_csv(csv_text, filename, domain)
        if not parsed.get("valid"):
            raise CuratedHydrationError(
                f"Curated dataset '{dataset_id}' failed CSV validation: {parsed.get('error')}",
                status_code=422,
            )
        if int(parsed["rows_count"]) > hard_max_rows:
            raise CuratedHydrationError(
                f"Curated dataset '{dataset_id}' exceeds hard row ceiling ({hard_max_rows} rows).",
                status_code=422,
            )

        cleaned_csv = parsed.get("cleaned_csv") or csv_text
        cleaned_bytes_len = len(cleaned_csv.encode("utf-8"))

        # 4. Enforce bounded curated LRU cache before loading into DuckDB
        evicted = evict_curated_cache_if_needed(
            incoming_bytes=cleaned_bytes_len,
            max_bytes=max_cache_bytes,
            max_tables=max_cache_tables,
            protect_dataset_id=dataset_id,
        )

        # 5. Atomic DuckDB persistence + verification (rollback on any mismatch)
        try:
            owner_id = str(dataset_row.get("user_id") or CURATED_OWNER_ID)
            persist_res = persist_dataset(
                dataset_id=dataset_id,
                user_id=owner_id,
                filename=filename,
                csv_content=cleaned_csv,
                rows_count=int(parsed["rows_count"]),
                columns_count=int(parsed["columns_count"]),
            )
            actual_rows = get_dataset_row_count(dataset_id)
            actual_cols = len(get_dataset_columns(dataset_id))
            if actual_rows != int(parsed["rows_count"]) or actual_cols != int(parsed["columns_count"]):
                raise RuntimeError(
                    f"Hydrated DuckDB dimensions mismatch ({actual_rows}x{actual_cols} != "
                    f"{parsed['rows_count']}x{parsed['columns_count']})"
                )
            record_curated_hydration(
                dataset_id=dataset_id,
                size_bytes=cleaned_bytes_len,
                sha256_checksum=expected_sha256,
            )
        except Exception as exc:
            delete_dataset_storage(dataset_id)
            logger.exception("Curated hydration failed for %s; rolled back partial storage.", dataset_id)
            raise CuratedHydrationError(
                f"Failed to hydrate curated dataset '{dataset_id}' into DuckDB.",
                status_code=500,
            ) from exc

        return {
            "dataset_id": dataset_id,
            "status": "hydrated_from_local" if use_local_file else "hydrated",
            "rows_count": int(persist_res["rows_count"]),
            "columns_count": int(persist_res["columns_count"]),
            "evicted": evicted,
        }


def ensure_community_dataset_hydrated(
    dataset_row: Dict[str, Any],
    r2_client: Optional[R2StorageClient] = None,
) -> Dict[str, Any]:
    """
    Re-hydrate a community dataset from Cloudflare R2 into local DuckDB when ephemeral local disk
    was reset (e.g. Render dyno restart) and `object_storage_key` + `sha256_checksum` exist.
    Never evicts community datasets from DuckDB and verifies SHA-256 before trusting bytes.
    """
    dataset_id = str(dataset_row.get("id") or "").strip()
    if not dataset_id or not DATASET_ID_REGEX.match(dataset_id):
        raise CuratedHydrationError(f"Invalid dataset identifier: '{dataset_id}'", status_code=400)

    if dataset_table_exists(dataset_id):
        return {"dataset_id": dataset_id, "status": "local_hit", "rows_count": get_dataset_row_count(dataset_id)}

    object_key = (dataset_row.get("object_storage_key") or "").strip()
    expected_sha256 = (dataset_row.get("sha256_checksum") or "").strip().lower()
    if not object_key or not expected_sha256:
        raise CuratedHydrationError(
            f"Analytical storage table for dataset '{dataset_id}' does not exist and no cloud backup is registered.",
            status_code=404,
        )

    try:
        safe_key = validate_dataset_object_key(object_key)
    except ValueError as exc:
        raise CuratedHydrationError(f"Dataset '{dataset_id}' has an invalid object storage key.", status_code=500) from exc

    lock = _get_hydration_lock(dataset_id)
    with lock:
        if dataset_table_exists(dataset_id):
            return {"dataset_id": dataset_id, "status": "local_hit", "rows_count": get_dataset_row_count(dataset_id)}

        client = r2_client or R2StorageClient()
        try:
            csv_bytes = client.download_and_verify_csv(
                object_storage_key=safe_key,
                expected_sha256=expected_sha256,
                max_uncompressed_bytes=settings.max_upload_bytes,
            )
        except R2ConfigurationError as exc:
            raise CuratedHydrationError(str(exc), status_code=503) from exc
        except R2ObjectNotFoundError as exc:
            raise CuratedHydrationError(
                f"Community dataset '{dataset_id}' file is missing from Cloudflare R2.",
                status_code=404,
            ) from exc
        except R2ChecksumMismatchError as exc:
            raise CuratedHydrationError(
                f"Community dataset '{dataset_id}' failed SHA-256 integrity verification.",
                status_code=502,
            ) from exc
        except R2StorageError as exc:
            raise CuratedHydrationError(
                f"Failed to retrieve community dataset '{dataset_id}' from Cloudflare R2: {exc}",
                status_code=503,
            ) from exc

        csv_text = csv_bytes.decode("utf-8", errors="replace")
        filename = str(dataset_row.get("filename") or f"{dataset_id}.csv")
        domain = str(dataset_row.get("domain") or "general")
        parsed = parse_and_evaluate_csv(csv_text, filename, domain)
        if not parsed.get("valid"):
            raise CuratedHydrationError(
                f"Community dataset '{dataset_id}' failed CSV validation during re-hydration.",
                status_code=422,
            )

        cleaned_csv = parsed.get("cleaned_csv") or csv_text
        try:
            persist_res = persist_dataset(
                dataset_id=dataset_id,
                user_id=str(dataset_row.get("user_id") or ""),
                filename=filename,
                csv_content=cleaned_csv,
                rows_count=int(parsed["rows_count"]),
                columns_count=int(parsed["columns_count"]),
            )
        except Exception as exc:
            delete_dataset_storage(dataset_id)
            logger.exception("Community dataset re-hydration failed for %s.", dataset_id)
            raise CuratedHydrationError(
                f"Failed to restore community dataset '{dataset_id}' into DuckDB.",
                status_code=500,
            ) from exc

        logger.info("Re-hydrated community dataset %s from Cloudflare R2 (%d rows).", dataset_id, persist_res["rows_count"])
        return {
            "dataset_id": dataset_id,
            "status": "hydrated_from_r2",
            "rows_count": int(persist_res["rows_count"]),
            "columns_count": int(persist_res["columns_count"]),
        }

