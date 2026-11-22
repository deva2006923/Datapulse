import io
import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import settings
from app.database import get_db_connection
from app.services.admin_bootstrap import create_or_promote_admin
from app.services.storage import dataset_table_exists, get_dataset_row_count
from scripts.migrate_local_datasets import (
    APPROVED_DATASET_IDS,
    HttpResponse,
    LocalDatasetRecord,
    load_approved_local_datasets,
    run_migration,
    validate_requested_dataset_ids,
)


def _create_user(client, email=None, password="Password123!", full_name="Migration User"):
    unique_email = email or f"mig_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post(
        "/auth/register",
        json={"email": unique_email, "password": password, "full_name": full_name},
    )
    assert res.status_code == 201
    data = res.json()
    return {
        "user_id": data["user"]["id"],
        "email": unique_email,
        "credits": data["user"]["credits"],
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _setup_admin(client, password="AdminMigrationPass123!"):
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com")
    conn = get_db_connection()
    create_or_promote_admin(
        email=admin_email,
        password=password,
        full_name="Platform Administrator",
        conn=conn,
    )
    login_res = client.post("/auth/login", json={"email": admin_email, "password": password})
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["user"]["is_admin"] is True
    return {
        "user_id": data["user"]["id"],
        "email": admin_email,
        "password": password,
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _sample_csv(rows=3):
    lines = ["id,department,salary"]
    for i in range(1, rows + 1):
        lines.append(f"{i},Engineering,{50000 + i * 1000}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _cleanup_dataset(ds_id: str):
    from app.services.storage import delete_dataset_storage

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM dataset_unlocks WHERE dataset_id = ?", (ds_id,))
    cur.execute("DELETE FROM dataset_versions WHERE dataset_id = ?", (ds_id,))
    cur.execute("DELETE FROM evaluations WHERE dataset_id = ?", (ds_id,))
    cur.execute("DELETE FROM datasets WHERE id = ?", (ds_id,))
    conn.commit()
    delete_dataset_storage(ds_id)


def _client_requester(client):
    """Adapts Starlette TestClient to scripts.migrate_local_datasets.RequesterFn."""

    def _req(method: str, path: str, headers: dict, data=None) -> HttpResponse:
        resp = client.request(method=method, url=path, headers=headers, content=data)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return HttpResponse(status=resp.status_code, body=body)

    return _req


# ---------------------------------------------------------------------------
# 1. Authorization & Validation Tests for POST /admin/datasets/import
# ---------------------------------------------------------------------------

def test_import_rejects_unauthenticated_and_non_admin(client):
    regular = _create_user(client)
    csv_bytes = _sample_csv()
    form = {
        "dataset_id": f"ds_auth_{uuid.uuid4().hex[:8]}",
        "name": "Unauthorized Dataset",
        "filename": "unauth.csv",
    }

    r_unauth = client.post(
        "/admin/datasets/import",
        data=form,
        files={"file": ("unauth.csv", csv_bytes, "text/csv")},
    )
    assert r_unauth.status_code == 401

    r_reg = client.post(
        "/admin/datasets/import",
        headers=regular["headers"],
        data=form,
        files={"file": ("unauth.csv", csv_bytes, "text/csv")},
    )
    assert r_reg.status_code == 403


def test_import_validates_dataset_id_and_csv(client):
    admin = _setup_admin(client)

    # Invalid dataset_id format
    r_bad_id = client.post(
        "/admin/datasets/import",
        headers=admin["headers"],
        data={"dataset_id": "bad_id;DROP TABLE", "name": "Bad ID"},
        files={"file": ("good.csv", _sample_csv(), "text/csv")},
    )
    assert r_bad_id.status_code == 422

    # Non-CSV filename
    r_bad_ext = client.post(
        "/admin/datasets/import",
        headers=admin["headers"],
        data={"dataset_id": f"ds_ext_{uuid.uuid4().hex[:8]}", "name": "Bad Ext"},
        files={"file": ("notes.txt", b"a,b\n1,2\n", "text/plain")},
    )
    assert r_bad_ext.status_code == 400

    # Empty CSV
    r_empty = client.post(
        "/admin/datasets/import",
        headers=admin["headers"],
        data={"dataset_id": f"ds_emp_{uuid.uuid4().hex[:8]}", "name": "Empty CSV"},
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert r_empty.status_code == 422


# ---------------------------------------------------------------------------
# 2. Dry-Run, Metadata Preservation, Owner Resolution & Zero Credits
# ---------------------------------------------------------------------------

def test_import_dry_run_makes_zero_writes(client):
    admin = _setup_admin(client)
    ds_id = f"ds_dry_{uuid.uuid4().hex[:8]}"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM datasets")
    before_ds = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM credit_transactions")
    before_tx = cur.fetchone()[0]

    res = client.post(
        "/admin/datasets/import",
        headers=admin["headers"],
        data={
            "dataset_id": ds_id,
            "name": "Dry Run Dataset",
            "filename": "dry.csv",
            "domain": "retail",
            "unlock_price": "48",
            "owner_email": "nonexistent_owner@example.com",
            "quality_score": "96.22",
            "schema_fidelity_score": "100.0",
            "completeness_score": "99.93",
            "domain_relevance_score": "85.0",
            "overall_score": "96.22",
            "created_at": "2026-10-10T12:46:11.301960",
            "dry_run": "true",
        },
        files={"file": ("dry.csv", _sample_csv(4), "text/csv")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "dry_run_ok"
    assert body["dry_run"] is True
    assert body["owner_email"].lower() == admin["email"].lower()
    assert body["owner_fallback_used"] is True
    assert body["credits_awarded"] == 0
    assert body["unlock_price"] == 48
    assert body["overall_score"] == 96.22

    # Confirm zero database or DuckDB writes occurred
    cur.execute("SELECT COUNT(*) FROM datasets")
    assert cur.fetchone()[0] == before_ds
    cur.execute("SELECT COUNT(*) FROM credit_transactions")
    assert cur.fetchone()[0] == before_tx
    assert dataset_table_exists(ds_id) is False


def test_import_preserves_metadata_owner_fallback_zero_credits_and_is_queryable(client):
    admin = _setup_admin(client)
    existing_owner = _create_user(
        client,
        email=f"owner_{uuid.uuid4().hex[:6]}@datapulse.test",
        full_name="Existing Owner",
    )

    ds_preserved = f"ds_own_{uuid.uuid4().hex[:8]}"
    ds_fallback = f"ds_fbk_{uuid.uuid4().hex[:8]}"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE id = ?", (existing_owner["user_id"],))
    owner_credits_before = cur.fetchone()["credits"]
    cur.execute("SELECT credits FROM users WHERE id = ?", (admin["user_id"],))
    admin_credits_before = cur.fetchone()["credits"]
    cur.execute("SELECT COUNT(*) FROM credit_transactions")
    tx_count_before = cur.fetchone()[0]

    try:
        # 2a. Existing owner preserved by email
        r1 = client.post(
            "/admin/datasets/import",
            headers=admin["headers"],
            data={
                "dataset_id": ds_preserved,
                "name": "Preserved Owner Listing",
                "filename": "hr.csv",
                "domain": "education",
                "unlock_price": "49",
                "owner_email": existing_owner["email"].upper(),
                "quality_score": "96.25",
                "schema_fidelity_score": "100.0",
                "completeness_score": "100.0",
                "domain_relevance_score": "85.0",
                "overall_score": "96.25",
                "created_at": "2026-10-21T06:21:05.344408",
            },
            files={"file": ("hr.csv", _sample_csv(5), "text/csv")},
        )
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["status"] == "imported"
        assert b1["dataset_id"] == ds_preserved
        assert b1["owner_id"] == existing_owner["user_id"]
        assert b1["owner_email"].lower() == existing_owner["email"].lower()
        assert b1["owner_fallback_used"] is False
        assert b1["unlock_price"] == 49
        assert b1["overall_score"] == 96.25
        assert b1["credits_awarded"] == 0
        assert b1["storage_available"] is True
        assert b1["duckdb_row_count"] == 5

        # 2b. Missing owner falls back to admin email — AND identical CSV content is preserved under distinct dataset_id!
        r2 = client.post(
            "/admin/datasets/import",
            headers=admin["headers"],
            data={
                "dataset_id": ds_fallback,
                "name": "Duplicate CSV Distinct Listing",
                "filename": "hr.csv",
                "domain": "telecom",
                "unlock_price": "10",
                "owner_email": "missing_user_999@example.com",
                "quality_score": "92.92",
                "schema_fidelity_score": "90.48",
                "completeness_score": "100.0",
                "domain_relevance_score": "85.0",
                "overall_score": "92.92",
                "created_at": "2026-10-26T05:22:16.728552",
            },
            files={"file": ("hr.csv", _sample_csv(5), "text/csv")},
        )
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["status"] == "imported"
        assert b2["dataset_id"] == ds_fallback
        assert b2["owner_id"] == admin["user_id"]
        assert b2["owner_email"].lower() == admin["email"].lower()
        assert b2["owner_fallback_used"] is True
        assert b2["unlock_price"] == 10
        assert b2["overall_score"] == 92.92
        assert b2["credits_awarded"] == 0
        assert b2["content_hash"] == b1["content_hash"]
        assert b2["storage_available"] is True

        # 2c. Second duplicate CSV listing ALSO assigned to admin fallback must succeed (distinct dataset_id)
        ds_fallback_dup = f"ds_fbk2_{uuid.uuid4().hex[:7]}"
        try:
            r3 = client.post(
                "/admin/datasets/import",
                headers=admin["headers"],
                data={
                    "dataset_id": ds_fallback_dup,
                    "name": "Second Admin Fallback Duplicate CSV",
                    "filename": "hr.csv",
                    "domain": "general",
                    "unlock_price": "48",
                    "owner_email": "another_missing@example.com",
                },
                files={"file": ("hr.csv", _sample_csv(5), "text/csv")},
            )
            assert r3.status_code == 200
            assert r3.json()["status"] == "imported"
            assert r3.json()["owner_id"] == admin["user_id"]
            assert r3.json()["content_hash"] == b2["content_hash"]
        finally:
            _cleanup_dataset(ds_fallback_dup)

        # 2d. Zero credits awarded and zero credit_transactions created
        cur.execute("SELECT credits FROM users WHERE id = ?", (existing_owner["user_id"],))
        assert cur.fetchone()["credits"] == owner_credits_before
        cur.execute("SELECT credits FROM users WHERE id = ?", (admin["user_id"],))
        assert cur.fetchone()["credits"] == admin_credits_before
        cur.execute("SELECT COUNT(*) FROM credit_transactions")
        assert cur.fetchone()[0] == tx_count_before

        # 2e. Admin detail endpoint shows 0 migration rewards and Available DuckDB storage
        ad_res = client.get(f"/admin/datasets/{ds_preserved}", headers=admin["headers"])
        assert ad_res.status_code == 200
        ad_body = ad_res.json()
        assert ad_body["availability"] == "Available"
        assert ad_body["total_rewards"] == 0
        assert ad_body["basic_upload_reward"] == 0
        assert ad_body["quality_reward"] == 0
        assert ad_body["unlock_price"] == 49
        assert ad_body["created_at"] == "2026-10-21T06:21:05.344408"

        # 2f. Idempotency: re-importing same dataset_id skips without overwriting or awarding credits
        r_dup = client.post(
            "/admin/datasets/import",
            headers=admin["headers"],
            data={
                "dataset_id": ds_preserved,
                "name": "SHOULD NOT OVERWRITE",
                "filename": "hr.csv",
                "unlock_price": "999",
            },
            files={"file": ("hr.csv", _sample_csv(2), "text/csv")},
        )
        assert r_dup.status_code == 200
        b_dup = r_dup.json()
        assert b_dup["status"] == "skipped"
        assert b_dup["already_exists"] is True
        assert b_dup["name"] == "Preserved Owner Listing"
        assert b_dup["unlock_price"] == 49
        assert b_dup["rows_count"] == 5

        # 2g. Imported dataset is immediately queryable via POST /query (including SELECT * LIMIT 10 and COUNT(*))
        q_res = client.post(
            "/query",
            headers=admin["headers"],
            json={"dataset_id": ds_fallback, "query": "How many rows are in this dataset?"},
        )
        assert q_res.status_code == 200
        assert q_res.json()["dataset_id"] == ds_fallback
        assert q_res.json()["results"] is not None

        q_sample = client.post(
            "/query",
            headers=admin["headers"],
            json={"dataset_id": ds_fallback, "query": "Show first 3 rows"},
        )
        assert q_sample.status_code == 200
        assert q_sample.json()["dataset_id"] == ds_fallback
        assert len(q_sample.json()["results"]) == 3
    finally:
        _cleanup_dataset(ds_preserved)
        _cleanup_dataset(ds_fallback)


# ---------------------------------------------------------------------------
# 3. Atomic Rollback on Failure (Server-Side)
# ---------------------------------------------------------------------------

def test_import_rolls_back_duckdb_and_csv_on_sqlite_failure(client):
    admin = _setup_admin(client)
    ds_id = f"ds_rbk_{uuid.uuid4().hex[:8]}"

    # Simulate a DuckDB verification mismatch after persist_dataset succeeds
    with patch("app.routers.admin.get_dataset_row_count", return_value=999999):
        res = client.post(
            "/admin/datasets/import",
            headers=admin["headers"],
            data={
                "dataset_id": ds_id,
                "name": "Rollback Test",
                "filename": "rb.csv",
            },
            files={"file": ("rb.csv", _sample_csv(3), "text/csv")},
        )
    assert res.status_code == 500

    # Verify zero leftover artifacts in SQLite, DuckDB, and CSV storage
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM datasets WHERE id = ?", (ds_id,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM evaluations WHERE dataset_id = ?", (ds_id,))
    assert cur.fetchone()[0] == 0
    assert dataset_table_exists(ds_id) is False
    csv_file = Path(settings.DATASETS_STORAGE_DIR) / f"{ds_id}.csv"
    assert not csv_file.exists()


# ---------------------------------------------------------------------------
# 4. Migration Script Allowlist, Dry-Run, Execute, Idempotency & Rollback
# ---------------------------------------------------------------------------

def test_script_enforces_strict_five_dataset_allowlist():
    assert len(APPROVED_DATASET_IDS) == 5
    assert validate_requested_dataset_ids(None) == APPROVED_DATASET_IDS
    assert validate_requested_dataset_ids(["ds_4ea9dd2fad18"]) == ("ds_4ea9dd2fad18",)

    with pytest.raises(ValueError, match="unapproved"):
        validate_requested_dataset_ids(["ds_fake_test_dataset_999"])


def _build_fake_local_env(tmpdir: Path):
    """Creates a synthetic local SQLite + CSV storage containing the 5 approved IDs PLUS 20 test datasets."""
    db_path = tmpdir / "local_datapulse.db"
    csv_dir = tmpdir / "datasets"
    csv_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT);
        CREATE TABLE datasets (
            id TEXT PRIMARY KEY, user_id TEXT, name TEXT, filename TEXT, domain TEXT,
            rows_count INTEGER, columns_count INTEGER, content_summary TEXT,
            unlock_price INTEGER, created_at TEXT
        );
        CREATE TABLE evaluations (
            id TEXT PRIMARY KEY, dataset_id TEXT UNIQUE, status TEXT, progress INTEGER,
            quality_score REAL, schema_fidelity_score REAL, completeness_score REAL,
            domain_relevance_score REAL, overall_score REAL, credits_awarded INTEGER
        );
        """
    )

    approved_specs = [
        ("ds_4ea9dd2fad18", "nithyapriya2426@gmail.com", "employee_attrition_dirty_practice.csv", "employee_attrition_dirty_practice.csv", "retail", 10, 96.22, _sample_csv(4)),
        ("ds_29bdba6e06c4", "devaprakassh5@gmail.com", "Zomato Restaurant Dataset", "Zomato Restaurant Dataset.csv", "general", 10, 92.92, _sample_csv(6)),
        ("ds_1145c9ac8987", "harinikanagaofficial@gmail.com", "Zomato Dataset", "Zomato Restaurant Dataset.csv", "general", 48, 92.92, _sample_csv(6)),
        ("ds_90ec661cdf80", "harishvsb2005@gmail.com", "IBM HR Analytics Employee Attrition & Performance", "WA_Fn-UseC_-HR-Employee-Attrition.csv", "education", 49, 96.25, _sample_csv(5)),
        ("ds_affea73a8720", "ravikap0063@gmail.com", "employee", "WA_Fn-UseC_-HR-Employee-Attrition.csv", "telecom", 49, 96.25, _sample_csv(5)),
    ]

    for idx, (ds_id, email, name, fname, domain, price, score, csv_bytes) in enumerate(approved_specs):
        uid = f"usr_loc_{idx}"
        rows_cnt = len(csv_bytes.decode("utf-8").strip().splitlines()) - 1
        conn.execute("INSERT INTO users (id, email) VALUES (?, ?)", (uid, email))
        conn.execute(
            """
            INSERT INTO datasets (id, user_id, name, filename, domain, rows_count, columns_count, content_summary, unlock_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ds_id, uid, name, fname, domain, rows_cnt, 3, f"Summary for {name}", price, f"2026-10-1{idx}T10:00:00"),
        )
        conn.execute(
            """
            INSERT INTO evaluations (id, dataset_id, status, progress, quality_score, schema_fidelity_score, completeness_score, domain_relevance_score, overall_score, credits_awarded)
            VALUES (?, ?, 'completed', 100, ?, 100.0, 100.0, 85.0, ?, 98)
            """,
            (f"eval_loc_{idx}", ds_id, score, score),
        )
        (csv_dir / f"{ds_id}.csv").write_bytes(csv_bytes)

    # Also add 20 fake automated test datasets that MUST NEVER be loaded or migrated
    conn.execute("INSERT INTO users (id, email) VALUES ('usr_test', 'test@datapulse.test')")
    for i in range(20):
        tid = f"ds_autotest_{i:04d}"
        conn.execute(
            """
            INSERT INTO datasets (id, user_id, name, filename, domain, rows_count, columns_count, content_summary, unlock_price, created_at)
            VALUES (?, 'usr_test', 'Automated Test', 'test.csv', 'general', 2, 3, 'Test', 10, '2026-10-01T00:00:00')
            """,
            (tid,),
        )
        (csv_dir / f"{tid}.csv").write_bytes(_sample_csv(2))

    conn.commit()
    conn.close()
    return db_path, csv_dir


def test_migration_script_end_to_end_dry_run_execute_idempotency_and_rollback(client):
    admin = _setup_admin(client)
    # Register ONE of the 5 original owners in target backend to verify mixed owner preservation + admin fallback
    preserved_owner_email = "harishvsb2005@gmail.com"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE LOWER(email) = ?", (preserved_owner_email,))
    if not cur.fetchone():
        _create_user(client, email=preserved_owner_email, full_name="Harish Prod")

    # Ensure clean slate for the 5 approved IDs in test DB
    for ds_id in APPROVED_DATASET_IDS:
        _cleanup_dataset(ds_id)

    requester = _client_requester(client)

    with tempfile.TemporaryDirectory() as td:
        db_path, csv_dir = _build_fake_local_env(Path(td))

        # Load local datasets: must return strictly the 5 approved datasets (never the 20 test rows)
        records = load_approved_local_datasets(sqlite_path=db_path, storage_dir=csv_dir)
        assert [r.dataset_id for r in records] == list(APPROVED_DATASET_IDS)

        try:
            # A. Dry run -> 5 dry_run_ok, 0 writes
            dry_report = run_migration(
                records=records,
                requester=requester,
                admin_email=admin["email"],
                admin_password=admin["password"],
                dry_run=True,
            )
            assert dry_report["success"] is True
            assert dry_report["mode"] == "dry_run"
            assert dry_report["dry_run_ready_count"] == 5
            assert dry_report["imported_count"] == 0
            assert dry_report["post_snapshot"]["total_datasets"] == dry_report["pre_snapshot"]["total_datasets"]
            assert (
                dry_report["post_snapshot"]["total_credits_in_circulation"]
                == dry_report["pre_snapshot"]["total_credits_in_circulation"]
            )
            # Ensure password/token never appear in serialized report
            raw_dry = json.dumps(dry_report)
            assert admin["password"] not in raw_dry
            assert admin["token"] not in raw_dry

            # B. Live execute -> all 5 imported, duplicate CSV pairs preserved, mixed ownership, 0 credits, verification PASSED
            exec_report = run_migration(
                records=records,
                requester=requester,
                admin_email=admin["email"],
                admin_password=admin["password"],
                dry_run=False,
            )
            assert exec_report["success"] is True, exec_report["errors"]
            assert exec_report["imported_count"] == 5
            assert exec_report["skipped_count"] == 0
            assert exec_report["verification"]["passed"] is True
            assert (
                exec_report["post_snapshot"]["total_credits_in_circulation"]
                == exec_report["pre_snapshot"]["total_credits_in_circulation"]
            )

            by_id = {r["dataset_id"]: r for r in exec_report["results"]}
            assert by_id["ds_90ec661cdf80"]["owner_email"].lower() == preserved_owner_email
            assert by_id["ds_90ec661cdf80"]["owner_fallback_used"] is False
            assert by_id["ds_4ea9dd2fad18"]["owner_email"].lower() == admin["email"].lower()
            assert by_id["ds_4ea9dd2fad18"]["owner_fallback_used"] is True
            assert by_id["ds_29bdba6e06c4"]["unlock_price"] == 10
            assert by_id["ds_1145c9ac8987"]["unlock_price"] == 48
            assert by_id["ds_29bdba6e06c4"]["content_hash"] == by_id["ds_1145c9ac8987"]["content_hash"]

            # C. Re-run execute (idempotency) -> all 5 skipped, 0 newly imported, 0 credits
            rerun_report = run_migration(
                records=records,
                requester=requester,
                admin_email=admin["email"],
                admin_password=admin["password"],
                dry_run=False,
            )
            assert rerun_report["success"] is True, rerun_report["errors"]
            assert rerun_report["imported_count"] == 0
            assert rerun_report["skipped_count"] == 5
            assert rerun_report["verification"]["passed"] is True

            # D. Batch rollback test: clean up, corrupt 3rd CSV so import fails mid-batch -> 1st & 2nd rolled back!
            for ds_id in APPROVED_DATASET_IDS:
                _cleanup_dataset(ds_id)
            (csv_dir / f"{APPROVED_DATASET_IDS[2]}.csv").write_bytes(b"")  # empty CSV triggers 422 on 3rd item

            # Reconstruct records pointing at the corrupted 3rd file
            corrupted_records = list(records)
            fail_report = run_migration(
                records=corrupted_records,
                requester=requester,
                admin_email=admin["email"],
                admin_password=admin["password"],
                dry_run=False,
                rollback_on_error=True,
            )
            assert fail_report["success"] is False
            assert len(fail_report["rollback"]) == 2
            assert all(r["rolled_back"] for r in fail_report["rollback"])
            # First two datasets must have been completely rolled back from target DB & DuckDB
            for ds_id in APPROVED_DATASET_IDS[:2]:
                assert dataset_table_exists(ds_id) is False
                cur.execute("SELECT COUNT(*) FROM datasets WHERE id = ?", (ds_id,))
                assert cur.fetchone()[0] == 0
        finally:
            for ds_id in APPROVED_DATASET_IDS:
                _cleanup_dataset(ds_id)
