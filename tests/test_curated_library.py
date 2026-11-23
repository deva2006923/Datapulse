import concurrent.futures
import gzip
import json
import sqlite3
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.config import settings
from app.database import get_db_connection, init_db
from app.services.admin_bootstrap import create_or_promote_admin
from app.services.curated_library import (
    CURATED_OWNER_EMAIL,
    CURATED_OWNER_ID,
    CURATED_OWNER_NAME,
    CuratedHydrationError,
    ensure_curated_dataset_hydrated,
    ensure_curated_system_owner,
    load_curated_manifest,
    sync_curated_manifest,
)
from app.services.r2_storage import (
    R2ChecksumMismatchError,
    R2ConfigurationError,
    R2ObjectNotFoundError,
    R2SizeLimitError,
    R2StorageClient,
    build_curated_object_key,
    compress_csv_bytes,
    compute_sha256_bytes,
    validate_curated_object_key,
)
from app.services.storage import (
    dataset_table_exists,
    delete_dataset_storage,
    get_curated_cache_stats,
    get_dataset_row_count,
    persist_dataset,
)


def _register_user(client, email=None, password="Password123!", full_name="Test User"):
    em = email or f"cur_user_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post(
        "/auth/register",
        json={"email": em, "password": password, "full_name": full_name},
    )
    assert res.status_code == 201
    data = res.json()
    return {
        "user_id": data["user"]["id"],
        "email": em,
        "credits": data["user"]["credits"],
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _setup_admin(client, password="AdminCuratedPass123!"):
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com")
    conn = get_db_connection()
    create_or_promote_admin(
        email=admin_email,
        password=password,
        full_name="Platform Administrator",
        conn=conn,
    )
    res = client.post("/auth/login", json={"email": admin_email, "password": password})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["is_admin"] is True
    return {
        "user_id": data["user"]["id"],
        "email": admin_email,
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _make_inmemory_r2_client(max_retries=3):
    """Build an R2StorageClient backed by an in-memory httpx.MockTransport (zero network)."""
    store: dict[str, bytes] = {}
    calls: list[tuple[str, str]] = []
    fail_next: dict[str, int] = {"GET": 0, "PUT": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        # Verify SigV4 authorization header is always present
        assert request.headers.get("authorization", "").startswith("AWS4-HMAC-SHA256 ")
        assert "x-amz-date" in request.headers
        assert "x-amz-content-sha256" in request.headers

        path = request.url.path
        calls.append((request.method, path))

        if fail_next.get(request.method, 0) > 0:
            fail_next[request.method] -= 1
            return httpx.Response(503, content=b"Service Unavailable")

        if request.method == "PUT":
            store[path] = bytes(request.content)
            return httpx.Response(200)
        if request.method == "GET":
            if path not in store:
                return httpx.Response(404, content=b"NoSuchKey")
            return httpx.Response(200, content=store[path])
        return httpx.Response(405)

    client = R2StorageClient(
        endpoint_url="https://mock-account.r2.cloudflarestorage.com",
        bucket_name="datapulse-curated-test",
        access_key_id="AKIA_MOCK_KEY",
        secret_access_key="MOCK_SECRET_KEY_VALUE",
        region="auto",
        max_retries=max_retries,
        transport=httpx.MockTransport(_handler),
        sleep_fn=lambda _s: None,
    )
    return client, store, calls, fail_next


def _cleanup_dataset(ds_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM dataset_unlocks WHERE dataset_id = ?", (ds_id,))
    cur.execute("DELETE FROM dataset_versions WHERE dataset_id = ?", (ds_id,))
    cur.execute("DELETE FROM evaluations WHERE dataset_id = ?", (ds_id,))
    cur.execute("DELETE FROM datasets WHERE id = ?", (ds_id,))
    conn.commit()
    delete_dataset_storage(ds_id)


# ---------------------------------------------------------------------------
# 1. Stage 0 & Stage 3: Complete 171-Entry Verified Manifest Integrity & Duplicate Prevention
# ---------------------------------------------------------------------------

EXPECTED_VERIFIED_DOMAIN_DISTRIBUTION = {
    "Healthcare & Medicine": 20,
    "Finance & Banking": 6,
    "Retail & E-commerce": 16,
    "HR & Employment": 14,
    "Education": 7,
    "Marketing & Customer Analytics": 13,
    "Transportation & Logistics": 7,
    "Real Estate": 12,
    "Environment & Climate": 10,
    "Government & Public Data": 15,
    "Technology & Cybersecurity": 10,
    "Agriculture & Food": 14,
    "Sports & Entertainment": 9,
    "Energy & Utilities": 8,
    "General & Research": 10,
}

ALLOWLISTED_OPEN_LICENSES = {
    "CC-BY 4.0",
    "Creative Commons Attribution 4.0 International",
    "CC0-1.0",
    "Creative Commons 1.0 Universal (Public Domain Dedication)",
    "Public Domain",
    "Public Domain U.S. Government",
    "Open Data Commons Public Domain Dedication and License",
    "Open Data Commons Open Database License",
    "Canada Open Government Licence",
    "Nova Scotia Open Government Licence",
    "MIT",
    "Unlicense",
}


def test_curated_manifest_contains_all_171_verified_candidates_and_excludes_unverified():
    manifest = load_curated_manifest("data/curated_manifest.json")
    datasets = manifest["datasets"]
    assert len(datasets) == 171

    domain_counts = Counter(d["domain"] for d in datasets)
    assert len(domain_counts) == 15
    assert dict(domain_counts) == EXPECTED_VERIFIED_DOMAIN_DISTRIBUTION

    seen_ids = set()
    seen_urls = set()
    ingested_entries = []
    pending_entries = []
    curated_dir = Path("data/curated")

    for entry in datasets:
        ds_id = entry["dataset_id"]
        src_url = entry["source_url"]
        lic = entry["license"]

        assert ds_id.startswith("ds_cur_")
        assert not ds_id.startswith("ds_cur_ing_e2e_")
        assert len(ds_id) <= 64
        assert ds_id not in seen_ids
        seen_ids.add(ds_id)

        assert src_url.startswith("https://")
        assert src_url not in seen_urls
        seen_urls.add(src_url)

        assert entry["license_verified"] is True
        assert lic in ALLOWLISTED_OPEN_LICENSES, f"Unexpected license: {lic!r}"
        assert "verify" not in lic.lower()
        assert "see terms" not in lic.lower()
        assert entry["license_url"].startswith("https://")
        assert entry["object_storage_key"] is None

        if entry["ingestion_status"] == "ingested":
            ingested_entries.append(entry)
            csv_path = curated_dir / f"{ds_id}.csv"
            assert csv_path.is_file(), f"Packaged curated CSV missing for ingested manifest entry: {ds_id}"
            assert entry["sha256_checksum"] == compute_sha256_bytes(csv_path.read_bytes())
            assert int(entry["rows_count"]) > 0
            assert int(entry["columns_count"]) > 0
            assert int(entry["csv_bytes"]) == csv_path.stat().st_size
            assert isinstance(entry["schema_json"], dict) and len(entry["schema_json"]) > 0
        else:
            pending_entries.append(entry)
            assert entry["ingestion_status"] == "pending_ingestion"
            assert entry["sha256_checksum"] is None

    assert len(ingested_entries) == 30
    assert len(pending_entries) == 141


def test_manifest_loader_rejects_duplicate_ids_and_unverified_licenses():
    with tempfile.TemporaryDirectory() as td:
        dup_path = Path(td) / "dup_manifest.json"
        dup_path.write_text(
            json.dumps(
                {
                    "manifest_version": "test",
                    "datasets": [
                        {
                            "dataset_id": "ds_cur_dup_one",
                            "name": "First",
                            "source_url": "https://example.org/1",
                            "license": "CC0-1.0",
                            "license_verified": True,
                            "ingestion_status": "pending_ingestion",
                        },
                        {
                            "dataset_id": "ds_cur_dup_one",
                            "name": "Duplicate",
                            "source_url": "https://example.org/2",
                            "license": "CC0-1.0",
                            "license_verified": True,
                            "ingestion_status": "pending_ingestion",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Duplicate dataset_id"):
            load_curated_manifest(dup_path)

        unver_path = Path(td) / "unverified_manifest.json"
        unver_path.write_text(
            json.dumps(
                {
                    "manifest_version": "test",
                    "datasets": [
                        {
                            "dataset_id": "ds_cur_unverified_1",
                            "name": "Unverified",
                            "source_url": "https://example.org/3",
                            "license": "See Terms of Use",
                            "license_verified": False,
                            "ingestion_status": "pending_ingestion",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="license_verified"):
            load_curated_manifest(unver_path)


# ---------------------------------------------------------------------------
# 2. Stage 1 & Stage 3: Schema Migrations, Dedicated System Owner & Restart Idempotency
# ---------------------------------------------------------------------------

def test_schema_migrations_system_owner_and_manifest_sync_idempotency(client):
    conn = get_db_connection()
    cur = conn.cursor()

    # Verify additive schema columns exist
    cur.execute("PRAGMA table_info(datasets)")
    cols = {r[1] for r in cur.fetchall()}
    expected_cols = {
        "is_curated",
        "dataset_type",
        "source_name",
        "source_url",
        "license",
        "license_url",
        "retrieved_at",
        "object_storage_key",
        "sha256_checksum",
        "ingestion_status",
        "source_version",
        "csv_bytes",
    }
    assert expected_cols.issubset(cols)

    # Create a community user + upload a community dataset before sync to ensure zero disturbance
    community_user = _register_user(client, full_name="Community Creator")
    upload_res = client.post(
        "/datasets/upload",
        headers=community_user["headers"],
        data={"domain": "retail", "name": "Community Retail Sales"},
        files={"file": ("comm.csv", b"item,sales\nWidget,100\nGadget,250\n", "text/csv")},
    )
    assert upload_res.status_code == 201
    comm_ds_id = upload_res.json()["id"]

    cur.execute("SELECT COUNT(*) FROM credit_transactions")
    tx_before = cur.fetchone()[0]
    cur.execute("SELECT credits FROM users WHERE id = ?", (community_user["user_id"],))
    comm_credits_before = cur.fetchone()["credits"]

    # Sync #1 (and repeat init_db + Sync #2 to simulate container restart)
    res1 = sync_curated_manifest(conn=conn)
    init_db()
    res2 = sync_curated_manifest(conn=conn)

    assert res1["synced"] == 171
    assert res2["synced"] == 171
    assert res2["inserted"] == 0
    assert res2["updated"] == 171
    assert res2["skipped_conflicts"] == 0

    # Dedicated system owner exists, is NOT admin, has 0 credits, and cannot authenticate
    owner = ensure_curated_system_owner(conn=conn)
    assert owner["id"] == CURATED_OWNER_ID
    assert owner["email"] == CURATED_OWNER_EMAIL
    assert owner["full_name"] == CURATED_OWNER_NAME
    cur.execute("SELECT credits, is_admin FROM users WHERE id = ?", (CURATED_OWNER_ID,))
    owner_row = cur.fetchone()
    assert owner_row["credits"] == 0
    assert owner_row["is_admin"] == 0

    bad_login = client.post(
        "/auth/login",
        json={"email": CURATED_OWNER_EMAIL, "password": "anypassword123"},
    )
    assert bad_login.status_code == 401

    # Exactly 171 curated datasets in SQLite, 0 duplicates, 0 credit transactions minted
    cur.execute("SELECT COUNT(*) FROM datasets WHERE is_curated = 1")
    assert cur.fetchone()[0] == 171
    cur.execute("SELECT COUNT(*) FROM credit_transactions")
    assert cur.fetchone()[0] == tx_before

    # Existing community dataset and credits are completely preserved
    cur.execute("SELECT user_id, is_curated, dataset_type, name FROM datasets WHERE id = ?", (comm_ds_id,))
    comm_row = cur.fetchone()
    assert comm_row["user_id"] == community_user["user_id"]
    assert comm_row["is_curated"] == 0
    assert comm_row["dataset_type"] == "community"
    assert comm_row["name"] == "Community Retail Sales"
    cur.execute("SELECT credits FROM users WHERE id = ?", (community_user["user_id"],))
    assert cur.fetchone()["credits"] == comm_credits_before


def test_manifest_sync_never_overwrites_community_dataset_on_id_collision():
    conn = get_db_connection()
    cur = conn.cursor()
    conflict_id = f"ds_cur_collision_{uuid.uuid4().hex[:6]}"
    now = "2026-11-22T00:00:00"
    owner = ensure_curated_system_owner(conn=conn)
    try:
        cur.execute(
            """
            INSERT INTO datasets (
                id, user_id, name, filename, domain, rows_count, columns_count,
                schema_json, content_summary, unlock_price, created_at, is_curated, dataset_type
            ) VALUES (?, ?, 'User Community Dataset', 'u.csv', 'retail', 5, 2, '{}', 'User summary', 25, ?, 0, 'community')
            """,
            (conflict_id, owner["id"], now),
        )
        conn.commit()

        with tempfile.TemporaryDirectory() as td:
            mpath = Path(td) / "manifest.json"
            mpath.write_text(
                json.dumps(
                    {
                        "manifest_version": "test",
                        "datasets": [
                            {
                                "dataset_id": conflict_id,
                                "name": "SHOULD NOT OVERWRITE",
                                "filename": "cur.csv",
                                "domain": "Education",
                                "content_summary": "Attempted overwrite",
                                "source_name": "Test",
                                "source_url": "https://example.org/ds",
                                "license": "CC0-1.0",
                                "license_verified": True,
                                "ingestion_status": "pending_ingestion",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            sync_res = sync_curated_manifest(manifest_path=mpath, conn=conn)
            assert sync_res["skipped_conflicts"] == 1
            cur.execute("SELECT name, is_curated, unlock_price FROM datasets WHERE id = ?", (conflict_id,))
            row = cur.fetchone()
            assert row["name"] == "User Community Dataset"
            assert row["is_curated"] == 0
            assert row["unlock_price"] == 25
    finally:
        _cleanup_dataset(conflict_id)


# ---------------------------------------------------------------------------
# 3. Stage 2: Cloudflare R2 Upload, Download, Retries, Key Safety & Checksum Errors
# ---------------------------------------------------------------------------

def test_r2_object_key_validation_and_configuration_errors():
    valid_sha = "a" * 64
    key = build_curated_object_key("ds_cur_test_1", valid_sha, "v1")
    assert key == f"curated/ds_cur_test_1/v1/{valid_sha}.csv.gz"
    assert validate_curated_object_key(key) == key

    with pytest.raises(ValueError):
        validate_curated_object_key("curated/../etc/passwd")
    with pytest.raises(ValueError):
        build_curated_object_key("../bad", valid_sha)
    with pytest.raises(ValueError):
        build_curated_object_key("ds_cur_ok", "not_a_sha")

    unconfigured = R2StorageClient(
        endpoint_url="", bucket_name="", access_key_id="", secret_access_key=""
    )
    assert unconfigured.is_configured is False
    with pytest.raises(R2ConfigurationError):
        unconfigured.upload_compressed_csv("ds_cur_ok", b"a,b\n1,2\n")


def test_r2_upload_download_retry_404_checksum_and_size_cap():
    r2, store, calls, fail_next = _make_inmemory_r2_client(max_retries=3)
    raw_csv = b"city,population\nAustin,974447\nSeattle,749256\n"

    # Transient 503 on first PUT retries and succeeds
    fail_next["PUT"] = 1
    meta = r2.upload_compressed_csv("ds_cur_r2_cities", raw_csv, source_version="v1")
    assert meta["sha256_checksum"] == compute_sha256_bytes(raw_csv)
    assert meta["csv_bytes"] == len(raw_csv)
    assert meta["compressed_bytes"] > 0

    # Transient 503 on first GET retries and verifies SHA-256
    fail_next["GET"] = 1
    downloaded = r2.download_and_verify_csv(
        object_storage_key=meta["object_storage_key"],
        expected_sha256=meta["sha256_checksum"],
    )
    assert downloaded == raw_csv

    # Tampered object triggers R2ChecksumMismatchError
    stored_path = next(iter(store.keys()))
    store[stored_path] = compress_csv_bytes(b"city,population\nTAMPERED,0\n")
    with pytest.raises(R2ChecksumMismatchError):
        r2.download_and_verify_csv(
            object_storage_key=meta["object_storage_key"],
            expected_sha256=meta["sha256_checksum"],
        )

    # Missing object raises R2ObjectNotFoundError
    missing_key = build_curated_object_key("ds_cur_missing", "b" * 64, "v1")
    with pytest.raises(R2ObjectNotFoundError):
        r2.download_and_verify_csv(missing_key, "b" * 64)

    # Oversized decompressed CSV triggers R2SizeLimitError (gzip-bomb guard)
    big_csv = b"x,y\n" + (b"1,2\n" * 500)
    big_meta = r2.upload_compressed_csv("ds_cur_r2_big", big_csv, max_uncompressed_bytes=10000)
    with pytest.raises(R2SizeLimitError):
        r2.download_and_verify_csv(
            object_storage_key=big_meta["object_storage_key"],
            expected_sha256=big_meta["sha256_checksum"],
            max_uncompressed_bytes=100,
        )


# ---------------------------------------------------------------------------
# 4. Stage 4: On-Demand DuckDB Hydration, Concurrency, Restart Recovery & LRU Eviction
# ---------------------------------------------------------------------------

def _insert_ingested_curated_row(ds_id: str, name: str, domain: str, r2: R2StorageClient, csv_bytes: bytes):
    conn = get_db_connection()
    cur = conn.cursor()
    owner = ensure_curated_system_owner(conn=conn)
    meta = r2.upload_compressed_csv(ds_id, csv_bytes, source_version="v1")
    now = "2026-11-22T10:00:00"
    rows_cnt = len(csv_bytes.decode("utf-8").strip().splitlines()) - 1
    cur.execute(
        """
        INSERT INTO datasets (
            id, user_id, name, filename, domain, rows_count, columns_count,
            schema_json, content_summary, unlock_price, content_hash, created_at,
            is_curated, dataset_type, source_name, source_url, license, license_url,
            retrieved_at, object_storage_key, sha256_checksum, ingestion_status,
            source_version, csv_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, 2, '{"item":"string","value":"integer"}', 'Curated test dataset', 0, ?, ?, 1, 'curated', 'Test Portal', 'https://example.org/data', 'CC0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', ?, ?, ?, 'ingested', 'v1', ?)
        """,
        (
            ds_id, owner["id"], name, f"{ds_id}.csv", domain, rows_cnt,
            meta["sha256_checksum"], now, now, meta["object_storage_key"], meta["sha256_checksum"], meta["csv_bytes"],
        ),
    )
    cur.execute(
        """
        INSERT INTO evaluations (
            id, dataset_id, status, progress, quality_score, schema_fidelity_score,
            completeness_score, domain_relevance_score, overall_score, credits_awarded,
            error_message, created_at, updated_at
        ) VALUES (?, ?, 'completed', 100, 96.0, 100.0, 100.0, 90.0, 96.0, 0, NULL, ?, ?)
        """,
        (f"eval_{uuid.uuid4().hex[:12]}", ds_id, now, now),
    )
    conn.commit()
    cur.execute("SELECT * FROM datasets WHERE id = ?", (ds_id,))
    return dict(cur.fetchone()), meta


def test_on_demand_hydration_concurrency_restart_recovery_and_lru_eviction(client):
    r2, _store, calls, _fail = _make_inmemory_r2_client()
    ds_ids = [f"ds_cur_lru_{i}_{uuid.uuid4().hex[:6]}" for i in range(4)]
    comm_ds_id = f"ds_comm_keep_{uuid.uuid4().hex[:6]}"

    try:
        # Persist a community table to verify LRU eviction NEVER drops community tables
        persist_dataset(
            dataset_id=comm_ds_id,
            user_id="usr_comm_owner",
            filename="keep.csv",
            csv_content="k,v\na,1\nb,2\n",
            rows_count=2,
            columns_count=2,
        )
        assert dataset_table_exists(comm_ds_id) is True

        rows_meta = []
        for idx, ds_id in enumerate(ds_ids):
            csv_bytes = f"item,value\nalpha_{idx},{10 + idx}\nbeta_{idx},{20 + idx}\n".encode("utf-8")
            row_dict, _ = _insert_ingested_curated_row(ds_id, f"Curated LRU {idx}", "Finance & Banking", r2, csv_bytes)
            rows_meta.append(row_dict)

        # 4a. Concurrent hydration of ds_ids[0] downloads from R2 strictly ONCE (single-flight lock)
        get_calls_before = sum(1 for m, _ in calls if m == "GET")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futs = [
                ex.submit(ensure_curated_dataset_hydrated, rows_meta[0], r2, 1024 * 1024, 2)
                for _ in range(4)
            ]
            results = [f.result() for f in futs]
        get_calls_after = sum(1 for m, _ in calls if m == "GET")
        assert get_calls_after - get_calls_before == 1
        assert sum(1 for r in results if r["status"] == "hydrated") == 1
        assert sum(1 for r in results if r["status"] == "cache_hit") == 3
        assert get_dataset_row_count(ds_ids[0]) == 2

        # 4b. Simulate Render ephemeral restart (drop DuckDB table + CSV) -> recovers seamlessly from R2!
        delete_dataset_storage(ds_ids[0])
        assert dataset_table_exists(ds_ids[0]) is False
        rec_res = ensure_curated_dataset_hydrated(rows_meta[0], r2_client=r2, max_cache_bytes=1024 * 1024, max_cache_tables=2)
        assert rec_res["status"] == "hydrated"
        assert dataset_table_exists(ds_ids[0]) is True

        # 4c. Enforce max_cache_tables=2 LRU eviction: hydrate #1 and #2 -> #0 is evicted, community table untouched!
        ensure_curated_dataset_hydrated(rows_meta[1], r2_client=r2, max_cache_bytes=1024 * 1024, max_cache_tables=2)
        ensure_curated_dataset_hydrated(rows_meta[2], r2_client=r2, max_cache_bytes=1024 * 1024, max_cache_tables=2)
        stats = get_curated_cache_stats()
        assert stats["count"] <= 2
        assert dataset_table_exists(ds_ids[0]) is False
        assert dataset_table_exists(ds_ids[2]) is True
        assert dataset_table_exists(comm_ds_id) is True  # Community table NEVER evicted!

        # 4d. Pending/un-ingested curated dataset MUST refuse hydration cleanly
        pending_row = dict(rows_meta[3])
        pending_row["ingestion_status"] = "pending_ingestion"
        pending_row["object_storage_key"] = None
        with pytest.raises(CuratedHydrationError) as exc:
            ensure_curated_dataset_hydrated(pending_row, r2_client=r2)
        assert exc.value.status_code == 503
    finally:
        for ds_id in ds_ids:
            _cleanup_dataset(ds_id)
        delete_dataset_storage(comm_ds_id)


# ---------------------------------------------------------------------------
# 5. Stage 5: Free Curated Queries (0 Credits, 0 Rewards), Community Credit Invariance & Visibility
# ---------------------------------------------------------------------------

def test_free_curated_queries_zero_balance_and_community_credits_unchanged(client):
    r2, _store, _calls, _fail = _make_inmemory_r2_client()
    curated_id = f"ds_cur_free_{uuid.uuid4().hex[:8]}"
    csv_bytes = b"item,value\nSolar,120\nWind,95\nHydro,80\n"

    zero_credit_user = _register_user(client, full_name="Zero Balance Analyst")
    comm_owner = _register_user(client, full_name="Community Seller")
    comm_buyer = _register_user(client, full_name="Community Buyer")
    admin = _setup_admin(client)

    conn = get_db_connection()
    cur = conn.cursor()
    # Set zero_credit_user's balance to 0 to prove curated queries require 0 credits
    cur.execute("UPDATE users SET credits = 0 WHERE id = ?", (zero_credit_user["user_id"],))
    conn.commit()

    try:
        _insert_ingested_curated_row(curated_id, "Clean Energy Output", "Energy & Utilities", r2, csv_bytes)

        # 5a. Curated dataset visible to BOTH regular user and Platform Admin with source filters
        for hdrs in (zero_credit_user["headers"], admin["headers"]):
            list_all = client.get("/datasets", headers=hdrs)
            assert list_all.status_code == 200
            found = [d for d in list_all.json()["datasets"] if d["id"] == curated_id]
            assert len(found) == 1
            assert found[0]["is_curated"] is True
            assert found[0]["dataset_type"] == "curated"
            assert found[0]["unlock_price"] == 0
            assert found[0]["availability"] == "On-Demand Ready"
            assert found[0]["storage_available"] is True

            list_cur = client.get("/datasets?source=curated&domain=energy%20%26%20utilities", headers=hdrs)
            assert list_cur.status_code == 200
            assert any(d["id"] == curated_id for d in list_cur.json()["datasets"])

        # 5b. Unlocking a curated dataset costs 0 credits and creates 0 transactions
        cur.execute("SELECT COUNT(*) FROM credit_transactions")
        tx_before = cur.fetchone()[0]
        unl_res = client.post(f"/datasets/{curated_id}/unlock", headers=zero_credit_user["headers"])
        assert unl_res.status_code == 200
        assert unl_res.json()["credits_charged"] == 0
        assert unl_res.json()["unlocked"] is True

        # 5c. Regular user with 0 credits queries curated dataset -> hydrates on demand from R2, returns real rows, 0 credits charged, 0 reward transactions!
        with patch("app.services.curated_library.R2StorageClient", return_value=r2):
            q_res = client.post(
                "/query",
                headers=zero_credit_user["headers"],
                json={"dataset_id": curated_id, "query": "How many rows are in this dataset?"},
            )
        assert q_res.status_code == 200, q_res.text
        q_body = q_res.json()
        assert q_body["credits_charged"] == 0
        assert q_body["dataset_id"] == curated_id
        assert q_body["results"] is not None

        # Confirm zero balance changes and zero new credit_transactions
        cur.execute("SELECT credits FROM users WHERE id = ?", (zero_credit_user["user_id"],))
        assert cur.fetchone()["credits"] == 0
        cur.execute("SELECT credits FROM users WHERE id = ?", (CURATED_OWNER_ID,))
        assert cur.fetchone()["credits"] == 0
        cur.execute("SELECT COUNT(*) FROM credit_transactions")
        assert cur.fetchone()[0] == tx_before

        # 5d. Security: regular user cannot delete or improve curated dataset (403)
        assert client.delete(f"/datasets/{curated_id}", headers=zero_credit_user["headers"]).status_code == 403
        assert (
            client.post(
                f"/datasets/{curated_id}/improve",
                headers=zero_credit_user["headers"],
                json={
                    "new_quality_score": 99.0,
                    "new_relevance_score": 99.0,
                    "changes_summary": "Unauthorized curated edit attempt",
                },
            ).status_code
            == 403
        )

        # 5e. Community Marketplace credit logic remains 100% unchanged!
        up = client.post(
            "/datasets/upload",
            headers=comm_owner["headers"],
            data={"domain": "retail", "name": "Paid Community Dataset"},
            files={"file": ("paid.csv", b"sku,revenue\nA1,500\nB2,700\n", "text/csv")},
        )
        assert up.status_code == 201
        comm_id = up.json()["id"]
        try:
            cur.execute("SELECT credits FROM users WHERE id = ?", (comm_owner["user_id"],))
            owner_cr_before = cur.fetchone()["credits"]
            cur.execute("SELECT credits FROM users WHERE id = ?", (comm_buyer["user_id"],))
            buyer_cr_before = cur.fetchone()["credits"]

            # Non-owner query charges 1 credit and rewards owner 1 credit
            cq = client.post(
                "/query",
                headers=comm_buyer["headers"],
                json={"dataset_id": comm_id, "query": "How many rows are in this dataset?"},
            )
            assert cq.status_code == 200
            assert cq.json()["credits_charged"] == settings.QUERY_COST

            cur.execute("SELECT credits FROM users WHERE id = ?", (comm_owner["user_id"],))
            assert cur.fetchone()["credits"] == owner_cr_before + settings.DATASET_OWNER_REWARD
            cur.execute("SELECT credits FROM users WHERE id = ?", (comm_buyer["user_id"],))
            assert cur.fetchone()["credits"] == buyer_cr_before - settings.QUERY_COST

            # Owner self-query remains free (0 credits charged, 0 rewarded)
            sq = client.post(
                "/query",
                headers=comm_owner["headers"],
                json={"dataset_id": comm_id, "query": "How many rows are in this dataset?"},
            )
            assert sq.status_code == 200
            assert sq.json()["credits_charged"] == 0
        finally:
            _cleanup_dataset(comm_id)
    finally:
        _cleanup_dataset(curated_id)

