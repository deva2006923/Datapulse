"""
Production Storage (PostgreSQL Adapter + Cloudflare R2 Community Persistence)
and Curated Dataset Ingestion Pipeline Tests.
"""

import io
import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.database import (
    _CompatRow,
    _PostgresConnectionAdapter,
    _open_postgres_connection,
    _split_sql_script,
    _translate_qmark_to_pyformat,
    get_db_backend,
    get_db_connection,
    is_postgres_backend,
    redact_database_url,
)
from app.services.curated_ingestion import (
    ingest_curated_csv_bytes,
    run_manifest_ingestion,
    validate_manifest_entry_eligibility,
)
from app.services.curated_library import (
    CuratedHydrationError,
    ensure_curated_dataset_hydrated,
    resolve_packaged_curated_csv_path,
    sync_curated_manifest,
)
from app.services.r2_storage import (
    R2StorageClient,
    build_community_object_key,
    compress_csv_bytes,
    compute_sha256_bytes,
    validate_dataset_object_key,
)
from app.services.storage import (
    dataset_table_exists,
    delete_dataset_storage,
    get_dataset_table_name,
    init_storage,
    reset_storage_connection,
)
from scripts.migrate_sqlite_to_postgres import inspect_sqlite_snapshot


def _register(client, prefix="prod"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"User {prefix}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return {
        "user_id": data["user"]["id"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _make_memory_r2_client():
    store = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        # Path format: /<bucket>/<object_key>
        parts = request.url.path.lstrip("/").split("/", 1)
        key = parts[1] if len(parts) > 1 else ""
        if request.method == "PUT":
            store[key] = bytes(request.content)
            return httpx.Response(200)
        if request.method == "GET":
            if key not in store:
                return httpx.Response(404)
            return httpx.Response(200, content=store[key])
        if request.method == "DELETE":
            store.pop(key, None)
            return httpx.Response(204)
        return httpx.Response(405)

    r2 = R2StorageClient(
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        bucket_name="datapulse-test-bucket",
        access_key_id="test_access_key",
        secret_access_key="test_secret_key",
        transport=httpx.MockTransport(_handler),
        sleep_fn=lambda _: None,
    )
    return r2, store


def test_postgres_adapter_translation_rows_and_transactions():
    assert get_db_backend() == "sqlite"

    # Parameter translation preserves '?' inside single quotes and escapes literal '%'
    sql = "SELECT * FROM datasets WHERE name LIKE '%zomato?%' AND domain = ? AND visibility != ?"
    translated = _translate_qmark_to_pyformat(sql)
    assert translated == "SELECT * FROM datasets WHERE name LIKE '%%zomato?%%' AND domain = %s AND visibility != %s"

    stmts = _split_sql_script("CREATE TABLE a (id TEXT); INSERT INTO a VALUES ('x;y');")
    assert len(stmts) == 2
    assert stmts[1] == "INSERT INTO a VALUES ('x;y')"

    # CompatRow behaves identically to sqlite3.Row
    row = _CompatRow(["id", "credits"], ["usr_1", 100])
    assert row["id"] == "usr_1"
    assert row[1] == 100
    assert dict(row) == {"id": "usr_1", "credits": 100}
    assert row.keys() == ["id", "credits"]

    # Simulated PostgreSQL connection adapter translates queries & forwards commit/rollback
    fake_raw_cursor = MagicMock()
    fake_raw_cursor.description = [("id",), ("credits",)]
    fake_raw_cursor.fetchone.return_value = ("usr_pg_1", 250)
    fake_raw_cursor.rowcount = 1
    fake_raw_conn = MagicMock()
    fake_raw_conn.cursor.return_value = fake_raw_cursor

    pg_conn = _PostgresConnectionAdapter(fake_raw_conn)
    cur = pg_conn.cursor()
    cur.execute("SELECT id, credits FROM users WHERE id = ?", ("usr_pg_1",))
    fetched = cur.fetchone()
    assert fetched["id"] == "usr_pg_1"
    assert fetched["credits"] == 250
    pg_conn.commit()
    pg_conn.rollback()

    fake_raw_cursor.execute.assert_called_once_with(
        "SELECT id, credits FROM users WHERE id = %s",
        ("usr_pg_1",),
    )
    assert fake_raw_conn.commit.call_count == 1
    assert fake_raw_conn.rollback.call_count == 1


def test_community_upload_persists_to_r2_and_rehydrates_after_ephemeral_restart(client):
    owner = _register(client, "r2c_owner")
    buyer = _register(client, "r2c_buyer")
    r2_client, r2_store = _make_memory_r2_client()

    csv_body = "city,orders,revenue\nSeattle,12,1800\nDenver,8,950\n"
    with patch("app.routers.datasets.R2StorageClient", return_value=r2_client), patch(
        "app.services.curated_library.R2StorageClient", return_value=r2_client
    ):
        up = client.post(
            "/datasets/upload",
            headers=owner["headers"],
            files={"file": ("cloud_orders.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
            data={"name": "Cloud Backed Orders", "domain": "retail", "visibility": "public"},
        )
        assert up.status_code == 201, up.text
        ds_id = up.json()["id"]

        # Verify community object was uploaded to Cloudflare R2 under community/<id>/<sha256>.csv.gz
        assert len(r2_store) == 1
        stored_key = next(iter(r2_store.keys()))
        assert stored_key.startswith(f"community/{ds_id}/")
        assert validate_dataset_object_key(stored_key) == stored_key

        # Simulate ephemeral container restart wiping local DuckDB table and CSV file
        delete_dataset_storage(ds_id)
        reset_storage_connection()
        init_storage()
        assert not dataset_table_exists(ds_id)

        # Listing should still report Cloud-Backed Ready (storage_available=True)
        detail = client.get(f"/datasets/{ds_id}", headers=buyer["headers"]).json()
        assert detail["storage_available"] is True
        assert detail["availability"] == "Cloud-Backed Ready"

        # Querying automatically re-hydrates from R2, executes SQL on DuckDB, and applies marketplace credits
        buyer_before = client.get("/auth/me", headers=buyer["headers"]).json()["credits"]
        owner_before = client.get("/auth/me", headers=owner["headers"]).json()["credits"]
        table_name = get_dataset_table_name(ds_id)

        with patch(
            "app.routers.query.generate_sql",
            return_value=f"SELECT SUM(revenue) AS total_rev FROM {table_name}",
        ):
            q = client.post(
                "/query",
                headers=buyer["headers"],
                json={"query": "Total revenue", "dataset_id": ds_id},
            )
        assert q.status_code == 200, q.text
        assert q.json()["results"] == [{"total_rev": 2750}]
        assert q.json()["credits_charged"] == 1
        assert dataset_table_exists(ds_id)
        assert client.get("/auth/me", headers=buyer["headers"]).json()["credits"] == buyer_before - 1
        assert client.get("/auth/me", headers=owner["headers"]).json()["credits"] == owner_before + 1


def test_community_upload_rolls_back_r2_object_on_evaluation_failure_and_blocks_missing_r2_in_prod(client):
    owner = _register(client, "r2rb_owner")
    r2_client, r2_store = _make_memory_r2_client()

    # 1. Evaluation crash after R2 upload must delete the R2 object cleanly
    with patch("app.routers.datasets.R2StorageClient", return_value=r2_client), patch(
        "app.routers.datasets.run_evaluation_pipeline",
        side_effect=RuntimeError("Simulated evaluation crash"),
    ):
        res = client.post(
            "/datasets/upload",
            headers=owner["headers"],
            files={"file": ("rollback_r2.csv", io.BytesIO(b"a,b\n1,2\n3,4\n"), "text/csv")},
            data={"name": "Rollback R2 Test", "domain": "general"},
        )
    assert res.status_code == 500
    assert len(r2_store) == 0

    # 2. When R2_REQUIRED_IN_PRODUCTION=True in production and R2 is unconfigured, upload fails with 503
    unconfigured_r2 = R2StorageClient(endpoint_url="", bucket_name="", access_key_id="", secret_access_key="")
    with patch.object(settings, "ENVIRONMENT", "production"), patch.object(
        settings, "R2_REQUIRED_IN_PRODUCTION", True
    ), patch("app.routers.datasets.R2StorageClient", return_value=unconfigured_r2):
        blocked = client.post(
            "/datasets/upload",
            headers=owner["headers"],
            files={"file": ("prod_no_r2.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
            data={"name": "No R2 Prod Upload", "domain": "general"},
        )
    assert blocked.status_code == 503


def test_curated_ingestion_license_enforcement_r2_upload_search_and_free_query(client):
    user = _register(client, "cur_ing_user")
    r2_client, r2_store = _make_memory_r2_client()

    # 1. Unverified / Needs Verification licenses are strictly excluded
    ok_bad, reason_bad = validate_manifest_entry_eligibility(
        {
            "dataset_id": "ds_cur_bad_license",
            "license": "Needs Verification",
            "license_verified": False,
            "source_name": "Unknown",
            "source_url": "https://example.org/data.csv",
        }
    )
    assert not ok_bad
    assert "license" in (reason_bad or "").lower()

    # 2. Dry-run audit of actual 171-entry curated_manifest.json reports 171 eligible, 0 failed, 0 excluded
    dry_report = run_manifest_ingestion(dry_run=True, upload_to_r2=False)
    assert dry_report["total_processed"] == 171
    assert dry_report["success_count"] == 171
    assert dry_report["failure_count"] == 0
    assert dry_report["excluded_count"] == 0

    # 3. Full ingestion of a verified curated dataset -> R2 upload -> Search discovery -> Free 0-credit query
    ds_id = f"ds_cur_ing_e2e_{uuid.uuid4().hex[:8]}"
    entry = {
        "dataset_id": ds_id,
        "name": "Global Renewable Solar Output Curated",
        "filename": "global_solar_output.csv",
        "domain": "Energy & Utilities",
        "content_summary": "Verified open solar energy generation measurements by country.",
        "source_name": "Our World in Data",
        "source_url": "https://github.com/owid/energy-data",
        "license": "CC-BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_verified": True,
        "source_version": "v1",
    }
    csv_bytes = b"country,year,solar_twh\nGermany,2024,62.5\nIndia,2024,118.4\n"

    conn = get_db_connection()
    with tempfile.TemporaryDirectory() as tmp_curated_dir:
        try:
            with patch.object(settings, "CURATED_DATA_DIR", tmp_curated_dir):
                ing_res = ingest_curated_csv_bytes(
                    entry,
                    csv_bytes,
                    r2_client=r2_client,
                    upload_to_r2=True,
                    conn=conn,
                )
                assert ing_res["status"] == "ingested"
                assert ing_res["rows_count"] == 2
                assert ing_res["columns_count"] == 3
                assert ing_res["object_storage_key"] in r2_store

                # Discover via natural-language search (POST /datasets/search)
                search = client.post(
                    "/datasets/search",
                    headers=user["headers"],
                    json={"query": "Global Renewable Solar Output", "limit": 20},
                )
                assert search.status_code == 200
                matches = {r["dataset_id"]: r for r in search.json()["results"]}
                assert ds_id in matches
                assert matches[ds_id]["unlock_price"] == 0
                assert matches[ds_id]["is_curated"] is True

                # Query with 0 balance -> hydrates, returns real DuckDB rows, 0 credits charged, 0 transactions
                conn.execute("UPDATE users SET credits = 0 WHERE id = ?", (user["user_id"],))
                conn.commit()
                tx_before = conn.execute(
                    "SELECT COUNT(*) FROM credit_transactions WHERE user_id = ?", (user["user_id"],)
                ).fetchone()[0]

                table_name = get_dataset_table_name(ds_id)
                with patch("app.services.curated_library.R2StorageClient", return_value=r2_client), patch(
                    "app.routers.query.generate_sql",
                    return_value=f"SELECT country, solar_twh FROM {table_name} ORDER BY solar_twh DESC LIMIT 1",
                ):
                    q = client.post(
                        "/query",
                        headers=user["headers"],
                        json={"query": "Top solar country", "dataset_id": ds_id},
                    )
                assert q.status_code == 200, q.text
                assert q.json()["credits_charged"] == 0
                assert q.json()["results"] == [{"country": "India", "solar_twh": 118.4}]
                tx_after = conn.execute(
                    "SELECT COUNT(*) FROM credit_transactions WHERE user_id = ?", (user["user_id"],)
                ).fetchone()[0]
                assert tx_after == tx_before
        finally:
            delete_dataset_storage(ds_id)
            conn.execute("DELETE FROM evaluations WHERE dataset_id = ?", (ds_id,))
            conn.execute("DELETE FROM datasets WHERE id = ?", (ds_id,))
            conn.commit()


def test_sqlite_migration_snapshot_helper_reads_without_mutating():
    snap = inspect_sqlite_snapshot(settings.DATABASE_PATH)
    assert "counts" in snap
    assert "users" in snap["counts"]
    assert isinstance(snap["total_user_credits"], int)


def test_postgres_backend_selection_and_credential_redaction():
    # Default in local dev/tests is SQLite
    with patch.object(settings, "DATABASE_URL", None):
        assert get_db_backend() == "sqlite"
        assert is_postgres_backend() is False

    # PostgreSQL backend selected when DATABASE_URL is postgres:// or postgresql://
    for url in (
        "postgresql://dp_user:superSecretPass123@db.example.neon.tech:5432/datapulse?sslmode=require",
        "postgres://dp_user:superSecretPass123@db.example.com:5432/datapulse",
    ):
        with patch.object(settings, "DATABASE_URL", url):
            assert get_db_backend() == "postgresql"
            assert is_postgres_backend() is True

    # Redaction hides credentials in both URI and libpq password= forms
    redacted_uri = redact_database_url(
        "postgresql://dp_user:superSecretPass123@db.example.neon.tech:5432/datapulse?sslmode=require"
    )
    assert "superSecretPass123" not in redacted_uri
    assert "dp_user" not in redacted_uri
    assert "db.example.neon.tech:5432/datapulse" in redacted_uri

    redacted_libpq = redact_database_url("host=db.example.com user=dp_user password=superSecretPass123 dbname=dp")
    assert "superSecretPass123" not in redacted_libpq
    assert "password=***" in redacted_libpq

    # Connection error never leaks raw DATABASE_URL credentials
    with patch.object(
        settings,
        "DATABASE_URL",
        "postgresql://secretuser:topsecretpw@127.0.0.1:1/datapulse",
    ), patch("app.database.psycopg") as mock_psycopg:
        mock_psycopg.connect.side_effect = RuntimeError(
            "connection failed for postgresql://secretuser:topsecretpw@127.0.0.1:1/datapulse"
        )
        with pytest.raises(RuntimeError) as exc_info:
            _open_postgres_connection()
        assert "topsecretpw" not in str(exc_info.value)
        assert "secretuser" not in str(exc_info.value)


def test_packaged_curated_csv_discovery_hydration_restart_recovery_without_r2(client):
    """
    Verify Render Free architecture end-to-end without ANY R2 credentials:
      - All 30 packaged curated CSV datasets are synchronized and discoverable via GET /datasets?source=curated
      - Synthetic E2E test CSV is NOT registered as a marketplace dataset
      - Querying a packaged curated dataset hydrates directly from data/curated/ with 0 R2 credentials
      - Simulated Render ephemeral restart (wiping DuckDB) re-hydrates automatically on next query
      - 0 credits charged and 0 credit transactions created
    """
    user = _register(client, "pkg_free_user")
    conn = get_db_connection()
    conn.execute("UPDATE users SET credits = 0 WHERE id = ?", (user["user_id"],))
    conn.commit()

    # Sync real manifest twice to confirm idempotency & zero synthetic entries
    sync1 = sync_curated_manifest(conn=conn)
    sync2 = sync_curated_manifest(conn=conn)
    assert sync1["synced"] == 171
    assert sync2["inserted"] == 0

    curated_res = client.get("/datasets?source=curated", headers=user["headers"])
    assert curated_res.status_code == 200
    curated_list = curated_res.json()["datasets"]
    assert len(curated_list) == 30
    assert all(d["is_curated"] is True for d in curated_list)
    assert all(d["unlock_price"] == 0 for d in curated_list)
    assert all(d["storage_available"] is True for d in curated_list)
    assert all(not d["id"].startswith("ds_cur_ing_e2e_") for d in curated_list)

    # Pick a real packaged curated dataset and ensure DuckDB starts without it (fresh restart)
    target_id = "ds_cur_hc_drug_use_by_age_nsduh_fivethirtyeight"
    delete_dataset_storage(target_id)
    assert not dataset_table_exists(target_id)

    tx_before = conn.execute(
        "SELECT COUNT(*) FROM credit_transactions WHERE user_id = ?", (user["user_id"],)
    ).fetchone()[0]

    # Query with NO R2 credentials configured (R2_ENDPOINT_URL etc. are None)
    table_name = get_dataset_table_name(target_id)
    with patch(
        "app.routers.query.generate_sql",
        return_value=f"SELECT COUNT(*) AS row_total FROM {table_name}",
    ):
        q1 = client.post(
            "/query",
            headers=user["headers"],
            json={"dataset_id": target_id, "query": "How many age groups are recorded?"},
        )
    assert q1.status_code == 200, q1.text
    assert q1.json()["credits_charged"] == 0
    assert q1.json()["results"] == [{"row_total": 17}]
    assert dataset_table_exists(target_id)

    # Simulate Render Free ephemeral restart wiping DuckDB & temp files -> re-hydrates seamlessly from data/curated/
    delete_dataset_storage(target_id)
    reset_storage_connection()
    init_storage()
    assert not dataset_table_exists(target_id)

    with patch(
        "app.routers.query.generate_sql",
        return_value=f"SELECT COUNT(*) AS row_total FROM {table_name}",
    ):
        q2 = client.post(
            "/query",
            headers=user["headers"],
            json={"dataset_id": target_id, "query": "How many age groups are recorded after restart?"},
        )
    assert q2.status_code == 200, q2.text
    assert q2.json()["credits_charged"] == 0
    assert q2.json()["results"] == [{"row_total": 17}]
    assert dataset_table_exists(target_id)

    # Confirm 0 credits deducted and 0 transactions created
    assert client.get("/auth/me", headers=user["headers"]).json()["credits"] == 0
    tx_after = conn.execute(
        "SELECT COUNT(*) FROM credit_transactions WHERE user_id = ?", (user["user_id"],)
    ).fetchone()[0]
    assert tx_after == tx_before


def test_packaged_curated_csv_prefers_local_over_r2_verifies_sha256_and_handles_missing_files(client):
    """
    Verify:
      1. Path traversal / non-curated IDs are strictly rejected by resolve_packaged_curated_csv_path.
      2. Valid packaged CSV hydrates locally FIRST without touching R2 even when object_storage_key is present.
      3. Tampered/corrupted packaged CSV fails SHA-256 verification (HTTP 502) and never loads into DuckDB or charges credits.
      4. Missing packaged CSV without R2 returns clear HTTP 404 (or HTTP 503 if R2 key exists without R2 creds).
    """
    # 1. Strict ID validation prevents traversal
    with pytest.raises(ValueError):
        resolve_packaged_curated_csv_path("../secrets")
    with pytest.raises(ValueError):
        resolve_packaged_curated_csv_path("ds_comm_not_curated")
    with pytest.raises(ValueError):
        resolve_packaged_curated_csv_path("ds_cur_bad/../../etc/passwd")

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        ds_ok = f"ds_cur_local_ok_{uuid.uuid4().hex[:6]}"
        raw_ok = b"region,units\nNorth,42\nSouth,58\n"
        sha_ok = compute_sha256_bytes(raw_ok)
        (tmp_dir / f"{ds_ok}.csv").write_bytes(raw_ok)

        row_ok = {
            "id": ds_ok,
            "user_id": "usr_system_curated_library",
            "filename": f"{ds_ok}.csv",
            "domain": "Retail & E-commerce",
            "ingestion_status": "ingested",
            "sha256_checksum": sha_ok,
            # Even with an object_storage_key set, packaged local CSV must be used FIRST with zero R2 calls
            "object_storage_key": f"curated/{ds_ok}/v1/{sha_ok}.csv.gz",
        }
        try:
            with patch("app.services.curated_library.R2StorageClient") as mock_r2_cls:
                res = ensure_curated_dataset_hydrated(row_ok, curated_data_dir=tmp_dir)
                assert res["status"] == "hydrated_from_local"
                assert res["rows_count"] == 2
                mock_r2_cls.assert_not_called()
        finally:
            delete_dataset_storage(ds_ok)

        # 3. Corrupted packaged CSV fails SHA-256 check (status 502) and never hydrates into DuckDB
        ds_bad = f"ds_cur_corrupt_{uuid.uuid4().hex[:6]}"
        (tmp_dir / f"{ds_bad}.csv").write_bytes(b"region,units\nTAMPERED,9999\n")
        row_bad = {
            "id": ds_bad,
            "user_id": "usr_system_curated_library",
            "filename": f"{ds_bad}.csv",
            "domain": "Retail & E-commerce",
            "ingestion_status": "ingested",
            "sha256_checksum": sha_ok,  # Mismatched expected digest
            "object_storage_key": None,
        }
        with pytest.raises(CuratedHydrationError) as corrupt_exc:
            ensure_curated_dataset_hydrated(row_bad, curated_data_dir=tmp_dir)
        assert corrupt_exc.value.status_code == 502
        assert "SHA-256" in str(corrupt_exc.value)
        assert not dataset_table_exists(ds_bad)

        # 4a. Missing packaged CSV with no R2 fallback -> clear HTTP 404
        ds_missing = f"ds_cur_missing_{uuid.uuid4().hex[:6]}"
        row_missing = {
            "id": ds_missing,
            "user_id": "usr_system_curated_library",
            "filename": f"{ds_missing}.csv",
            "domain": "Retail & E-commerce",
            "ingestion_status": "ingested",
            "sha256_checksum": sha_ok,
            "object_storage_key": None,
        }
        with pytest.raises(CuratedHydrationError) as miss_exc:
            ensure_curated_dataset_hydrated(row_missing, curated_data_dir=tmp_dir)
        assert miss_exc.value.status_code == 404
        assert "missing" in str(miss_exc.value).lower()

        # 4b. Missing packaged CSV with R2 object key but unconfigured R2 credentials -> clear HTTP 503
        row_missing_r2 = dict(row_missing)
        row_missing_r2["object_storage_key"] = f"curated/{ds_missing}/v1/{sha_ok}.csv.gz"
        with pytest.raises(CuratedHydrationError) as r2_exc:
            ensure_curated_dataset_hydrated(row_missing_r2, curated_data_dir=tmp_dir)
        assert r2_exc.value.status_code == 503
        assert "not configured" in str(r2_exc.value).lower()


def test_production_community_upload_rejected_cleanly_without_durable_storage_and_preserves_credits(client):
    """
    On Render Free (ENVIRONMENT=production, no R2 credentials configured):
      - Default R2_REQUIRED_IN_PRODUCTION is True.
      - POST /datasets/upload fails with HTTP 503 and a clear message.
      - Zero dataset records created, zero credit balance changes, zero credit_transactions rows added.
    """
    owner = _register(client, "prod_free_up")
    conn = get_db_connection()
    credits_before = conn.execute("SELECT credits FROM users WHERE id = ?", (owner["user_id"],)).fetchone()["credits"]
    ds_before = conn.execute("SELECT COUNT(*) FROM datasets WHERE user_id = ?", (owner["user_id"],)).fetchone()[0]
    tx_before = conn.execute(
        "SELECT COUNT(*) FROM credit_transactions WHERE user_id = ?", (owner["user_id"],)
    ).fetchone()[0]

    assert settings.R2_REQUIRED_IN_PRODUCTION is True
    with patch.object(settings, "ENVIRONMENT", "production"):
        res = client.post(
            "/datasets/upload",
            headers=owner["headers"],
            files={"file": ("prod_free.csv", io.BytesIO(b"col1,col2\n1,2\n3,4\n"), "text/csv")},
            data={"name": "Render Free Blocked Upload", "domain": "retail"},
        )
    assert res.status_code == 503
    assert "permanent file storage" in res.json()["detail"].lower()

    credits_after = conn.execute("SELECT credits FROM users WHERE id = ?", (owner["user_id"],)).fetchone()["credits"]
    ds_after = conn.execute("SELECT COUNT(*) FROM datasets WHERE user_id = ?", (owner["user_id"],)).fetchone()[0]
    tx_after = conn.execute(
        "SELECT COUNT(*) FROM credit_transactions WHERE user_id = ?", (owner["user_id"],)
    ).fetchone()[0]
    assert credits_after == credits_before
    assert ds_after == ds_before
    assert tx_after == tx_before


