"""
End-to-End & Regression Tests for DataPulse Urgent Fixes:
- Private vs. Public dataset visibility & backend permission enforcement
- Pending curated datasets excluded from queryable catalog by default
- Upload validation & atomic rollback on evaluation failure
- Query execution edge cases (empty prompt, missing column, empty result, AI unavailable 503)
- Backend restart persistence for community datasets and R2 re-hydration for curated datasets
- Credit and royalty accounting integrity
"""

import io
import os
import uuid
from unittest.mock import patch

from app.config import settings
from app.database import get_db_connection, init_db
from app.services.admin_bootstrap import create_or_promote_admin
from app.services.curated_library import CURATED_OWNER_ID, ensure_curated_system_owner
from app.services.nl_query import AIProviderError
from app.services.r2_storage import build_curated_object_key, compute_sha256_bytes
from app.services.storage import (
    dataset_table_exists,
    delete_dataset_storage,
    get_dataset_table_name,
    init_storage,
    reset_storage_connection,
)


def _register(client, prefix="uf"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"User {prefix}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return {
        "user_id": data["user"]["id"],
        "email": email,
        "credits": data["user"]["credits"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _get_admin(client, password="AdminUrgentPass123!"):
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com")
    conn = get_db_connection()
    create_or_promote_admin(
        email=admin_email,
        password=password,
        full_name="Platform Admin",
        conn=conn,
    )
    res = client.post("/auth/login", json={"email": admin_email, "password": password})
    assert res.status_code == 200, res.text
    data = res.json()
    return {
        "user_id": data["user"]["id"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _upload_csv(client, headers, name, csv_text, domain="finance", visibility="public"):
    return client.post(
        "/datasets/upload",
        headers=headers,
        files={"file": (f"{name}.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
        data={"name": name, "domain": domain, "visibility": visibility},
    )


def _get_credits(client, headers):
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200
    return res.json()["credits"]


def test_private_dataset_permissions_and_visibility_toggle(client):
    owner = _register(client, "priv_owner")
    other = _register(client, "priv_other")
    admin = _get_admin(client)

    csv_body = "account_id,region,revenue\n1,North,500\n2,South,750\n3,East,900\n"
    up = _upload_csv(
        client,
        owner["headers"],
        name="Secret Revenue Ledger",
        csv_text=csv_body,
        domain="finance",
        visibility="private",
    )
    assert up.status_code == 201, up.text
    ds = up.json()
    ds_id = ds["id"]
    assert ds["visibility"] == "private"
    assert ds["rows_count"] == 3

    # 1. Owner sees private dataset in All and source=mine, NOT in source=community
    owner_all = client.get("/datasets", headers=owner["headers"]).json()["datasets"]
    assert any(d["id"] == ds_id for d in owner_all)

    owner_mine = client.get("/datasets?source=mine", headers=owner["headers"]).json()["datasets"]
    assert any(d["id"] == ds_id for d in owner_mine)

    owner_comm = client.get("/datasets?source=community", headers=owner["headers"]).json()["datasets"]
    assert not any(d["id"] == ds_id for d in owner_comm)

    # 2. Other user & unauthenticated user CANNOT see private dataset anywhere
    other_all = client.get("/datasets", headers=other["headers"]).json()["datasets"]
    assert not any(d["id"] == ds_id for d in other_all)

    anon_all = client.get("/datasets").json()["datasets"]
    assert not any(d["id"] == ds_id for d in anon_all)

    other_search = client.post(
        "/datasets/search",
        headers=other["headers"],
        json={"query": "Secret Revenue Ledger", "limit": 20},
    )
    assert other_search.status_code == 200
    assert not any(r["dataset_id"] == ds_id for r in other_search.json()["results"])

    # 3. Direct detail / evaluation / unlock / query blocked for non-owner & unauthenticated
    assert client.get(f"/datasets/{ds_id}").status_code == 401
    assert client.get(f"/datasets/{ds_id}", headers=other["headers"]).status_code == 403
    assert client.get(f"/datasets/{ds_id}/evaluation", headers=other["headers"]).status_code == 403
    assert client.post(f"/datasets/{ds_id}/unlock", headers=other["headers"]).status_code == 403

    other_before = _get_credits(client, other["headers"])
    q_blocked = client.post(
        "/query",
        headers=other["headers"],
        json={"query": "How many rows?", "dataset_id": ds_id},
    )
    assert q_blocked.status_code == 403
    assert _get_credits(client, other["headers"]) == other_before

    # 4. Admin can inspect private dataset; owner can query own private dataset for 0 credits
    assert client.get(f"/datasets/{ds_id}", headers=admin["headers"]).status_code == 200

    table_name = get_dataset_table_name(ds_id)
    owner_before = _get_credits(client, owner["headers"])
    with patch("app.routers.query.generate_sql", return_value=f"SELECT COUNT(*) AS total FROM {table_name}"):
        q_own = client.post(
            "/query",
            headers=owner["headers"],
            json={"query": "How many rows?", "dataset_id": ds_id},
        )
    assert q_own.status_code == 200, q_own.text
    assert q_own.json()["credits_charged"] == 0
    assert q_own.json()["results"][0]["total"] == 3
    assert _get_credits(client, owner["headers"]) == owner_before

    # 5. Non-owner cannot change visibility
    bad_toggle = client.patch(
        f"/datasets/{ds_id}/visibility",
        headers=other["headers"],
        json={"visibility": "public"},
    )
    assert bad_toggle.status_code == 403

    # 6. Owner toggles private -> public; other user can now discover & query (1 cr cost, 1 cr owner reward)
    toggle = client.patch(
        f"/datasets/{ds_id}/visibility",
        headers=owner["headers"],
        json={"visibility": "public"},
    )
    assert toggle.status_code == 200, toggle.text
    assert toggle.json()["visibility"] == "public"

    other_comm = client.get("/datasets?source=community", headers=other["headers"]).json()["datasets"]
    assert any(d["id"] == ds_id for d in other_comm)

    owner_before_paid = _get_credits(client, owner["headers"])
    other_before_paid = _get_credits(client, other["headers"])
    with patch("app.routers.query.generate_sql", return_value=f"SELECT SUM(revenue) AS total_rev FROM {table_name}"):
        q_paid = client.post(
            "/query",
            headers=other["headers"],
            json={"query": "Total revenue", "dataset_id": ds_id},
        )
    assert q_paid.status_code == 200, q_paid.text
    assert q_paid.json()["credits_charged"] == 1
    assert q_paid.json()["results"][0]["total_rev"] == 2150
    assert _get_credits(client, other["headers"]) == other_before_paid - 1
    assert _get_credits(client, owner["headers"]) == owner_before_paid + 1


def test_pending_curated_datasets_excluded_by_default_and_ingested_curated_queryable(client):
    user = _register(client, "cur_vis")
    ensure_curated_system_owner()

    pending_id = f"ds_cur_pend_{uuid.uuid4().hex[:8]}"
    ingested_id = f"ds_cur_ing_{uuid.uuid4().hex[:8]}"
    csv_bytes = b"city,temp_c\nLondon,14.5\nTokyo,22.0\n"
    checksum = compute_sha256_bytes(csv_bytes)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Insert 1 pending_ingestion curated dataset and 1 ingested curated dataset
        cursor.execute(
            """
            INSERT INTO datasets (
                id, user_id, name, filename, domain, rows_count, columns_count,
                schema_json, content_summary, unlock_price, visibility,
                is_curated, source_name, source_url, license, ingestion_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'public', 1, ?, ?, ?, ?)
            """,
            (
                pending_id,
                CURATED_OWNER_ID,
                "Pending Curated Weather",
                "pending_weather.csv",
                "Environment & Climate",
                100,
                2,
                '{"city": "string", "temp_c": "float"}',
                "Not yet uploaded to R2.",
                "Test Source",
                "https://example.org/pending",
                "CC0 1.0",
                "pending_ingestion",
            ),
        )
        cursor.execute(
            """
            INSERT INTO datasets (
                id, user_id, name, filename, domain, rows_count, columns_count,
                schema_json, content_summary, unlock_price, visibility,
                is_curated, dataset_type, source_name, source_url, license,
                object_storage_key, sha256_checksum, ingestion_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'public', 1, 'curated', ?, ?, ?, ?, ?, ?)
            """,
            (
                ingested_id,
                CURATED_OWNER_ID,
                "Ingested Curated Weather",
                "ingested_weather.csv",
                "Environment & Climate",
                2,
                2,
                '{"city": "string", "temp_c": "float"}',
                "Verified weather readings.",
                "Test Source",
                "https://example.org/ingested",
                "CC0 1.0",
                build_curated_object_key(ingested_id, checksum, "v1"),
                checksum,
                "ingested",
            ),
        )
        # Set user balance to 0 to verify free curated query succeeds with 0 balance
        cursor.execute("UPDATE users SET credits = 0 WHERE id = ?", (user["user_id"],))
        conn.commit()

        # Default GET /datasets MUST exclude pending_ingestion curated dataset and include ingested one
        default_ids = {d["id"] for d in client.get("/datasets", headers=user["headers"]).json()["datasets"]}
        assert pending_id not in default_ids
        assert ingested_id in default_ids

        curated_ids = {
            d["id"] for d in client.get("/datasets?source=curated", headers=user["headers"]).json()["datasets"]
        }
        assert pending_id not in curated_ids
        assert ingested_id in curated_ids

        # Opt-in include_pending=true still exposes pending curated rows for inspection
        all_with_pending = {
            d["id"]
            for d in client.get(
                "/datasets?source=curated&include_pending=true", headers=user["headers"]
            ).json()["datasets"]
        }
        assert pending_id in all_with_pending

        # Search excludes pending curated datasets
        search_res = client.post(
            "/datasets/search",
            headers=user["headers"],
            json={"query": "Pending Curated Weather", "limit": 20},
        ).json()
        assert not any(r["dataset_id"] == pending_id for r in search_res["results"])

        # Direct query on pending curated returns 503 and charges 0 credits
        q_pending = client.post(
            "/query",
            headers=user["headers"],
            json={"query": "How many rows?", "dataset_id": pending_id},
        )
        assert q_pending.status_code == 503

        # Cannot set a curated dataset to private
        admin = _get_admin(client)
        cur_priv = client.patch(
            f"/datasets/{ingested_id}/visibility",
            headers=admin["headers"],
            json={"visibility": "private"},
        )
        assert cur_priv.status_code == 400

        # Querying ingested curated dataset with 0 balance succeeds, charges 0 credits, creates 0 tx
        tx_before = cursor.execute(
            "SELECT COUNT(*) FROM credit_transactions WHERE user_id IN (?, ?)",
            (user["user_id"], CURATED_OWNER_ID),
        ).fetchone()[0]

        table_name = get_dataset_table_name(ingested_id)

        class _FakeR2:
            def download_and_verify_csv(self, **kwargs):
                assert kwargs.get("expected_sha256") == checksum
                return csv_bytes

        with patch("app.services.curated_library.R2StorageClient", return_value=_FakeR2()), patch(
            "app.routers.query.generate_sql",
            return_value=f"SELECT COUNT(*) AS cnt FROM {table_name}",
        ):
            q_ok = client.post(
                "/query",
                headers=user["headers"],
                json={"query": "Count cities", "dataset_id": ingested_id},
            )
            assert q_ok.status_code == 200, q_ok.text
            assert q_ok.json()["credits_charged"] == 0
            assert q_ok.json()["results"][0]["cnt"] == 2

            # Simulate backend restart + cache wipe -> re-hydrates automatically on next query
            delete_dataset_storage(ingested_id)
            reset_storage_connection()
            init_storage()
            assert not dataset_table_exists(ingested_id)

            q_after_restart = client.post(
                "/query",
                headers=user["headers"],
                json={"query": "Count cities after restart", "dataset_id": ingested_id},
            )
            assert q_after_restart.status_code == 200, q_after_restart.text
            assert q_after_restart.json()["results"][0]["cnt"] == 2
            assert dataset_table_exists(ingested_id)

        tx_after = cursor.execute(
            "SELECT COUNT(*) FROM credit_transactions WHERE user_id IN (?, ?)",
            (user["user_id"], CURATED_OWNER_ID),
        ).fetchone()[0]
        assert tx_after == tx_before
    finally:
        delete_dataset_storage(ingested_id)
        cursor.execute("DELETE FROM datasets WHERE id IN (?, ?)", (pending_id, ingested_id))
        conn.commit()


def test_upload_validation_and_atomic_rollback_on_evaluation_failure(client):
    user = _register(client, "up_rb")
    credits_before = _get_credits(client, user["headers"])

    # 1. Reject non-CSV extension (.xlsx)
    bad_ext = client.post(
        "/datasets/upload",
        headers=user["headers"],
        files={"file": ("sheet.xlsx", io.BytesIO(b"PK\x03\x04dummy"), "application/octet-stream")},
        data={"name": "Bad Excel", "domain": "general"},
    )
    assert bad_ext.status_code == 400
    assert _get_credits(client, user["headers"]) == credits_before

    # 2. Reject empty file
    empty_res = _upload_csv(client, user["headers"], "Empty CSV", "")
    assert empty_res.status_code in (400, 422)
    assert _get_credits(client, user["headers"]) == credits_before

    # 3. Atomic rollback when evaluation pipeline unexpectedly raises
    conn = get_db_connection()
    ds_count_before = conn.execute("SELECT COUNT(*) FROM datasets WHERE user_id = ?", (user["user_id"],)).fetchone()[0]

    created_ids = []
    from app.services.storage import persist_dataset as real_persist

    def _spy_persist(dataset_id, *args, **kwargs):
        created_ids.append(dataset_id)
        return real_persist(dataset_id, *args, **kwargs)

    with patch("app.routers.datasets.persist_dataset", side_effect=_spy_persist), patch(
        "app.routers.datasets.run_evaluation_pipeline",
        side_effect=RuntimeError("Simulated evaluator crash"),
    ):
        failed_up = _upload_csv(
            client,
            user["headers"],
            "Rollback Test Dataset",
            "id,metric\n1,10\n2,20\n",
        )
    assert failed_up.status_code == 500
    assert len(created_ids) == 1
    rolled_back_id = created_ids[0]

    # Verify SQLite, DuckDB, CSV, and user credits were all cleanly rolled back
    ds_count_after = conn.execute("SELECT COUNT(*) FROM datasets WHERE user_id = ?", (user["user_id"],)).fetchone()[0]
    assert ds_count_after == ds_count_before
    assert not dataset_table_exists(rolled_back_id)
    csv_path = os.path.join(os.path.abspath(settings.DATASETS_STORAGE_DIR), f"{rolled_back_id}.csv")
    assert not os.path.exists(csv_path)
    assert _get_credits(client, user["headers"]) == credits_before


def test_query_edge_cases_and_community_restart_persistence(client):
    owner = _register(client, "q_owner")
    querier = _register(client, "q_buyer")

    up = _upload_csv(
        client,
        owner["headers"],
        name="Orders Persistence Dataset",
        csv_text="order_id,category,amount\n101,Books,25\n102,Games,60\n",
        domain="retail",
        visibility="public",
    )
    assert up.status_code == 201, up.text
    ds_id = up.json()["id"]
    table_name = get_dataset_table_name(ds_id)
    buyer_credits = _get_credits(client, querier["headers"])

    # 1. Empty / whitespace query -> 400, 0 credits charged
    q_empty = client.post(
        "/query",
        headers=querier["headers"],
        json={"query": "   ", "dataset_id": ds_id},
    )
    assert q_empty.status_code == 400
    assert _get_credits(client, querier["headers"]) == buyer_credits

    # 2. Missing column SQL -> 422, 0 credits charged
    with patch(
        "app.routers.query.generate_sql",
        return_value=f"SELECT nonexistent_column FROM {table_name}",
    ):
        q_bad_col = client.post(
            "/query",
            headers=querier["headers"],
            json={"query": "Show nonexistent column", "dataset_id": ds_id},
        )
    assert q_bad_col.status_code == 422
    assert _get_credits(client, querier["headers"]) == buyer_credits

    # 3. Unavailable AI provider -> 503, 0 credits charged
    with patch(
        "app.routers.query.generate_sql",
        side_effect=AIProviderError("Gemini API key missing"),
    ):
        q_ai_down = client.post(
            "/query",
            headers=querier["headers"],
            json={"query": "What is average amount?", "dataset_id": ds_id},
        )
    assert q_ai_down.status_code == 503
    assert _get_credits(client, querier["headers"]) == buyer_credits

    # 4. Empty SQL result set -> 200, results == [], truthful non-fabricated answer
    with patch(
        "app.routers.query.generate_sql",
        return_value=f"SELECT * FROM {table_name} WHERE amount > 999999",
    ):
        q_zero = client.post(
            "/query",
            headers=querier["headers"],
            json={"query": "Orders over 999999", "dataset_id": ds_id},
        )
    assert q_zero.status_code == 200, q_zero.text
    assert q_zero.json()["results"] == []
    assert q_zero.json()["records_analyzed"] == 2
    assert "0" in q_zero.json()["answer"] or "no" in q_zero.json()["answer"].lower()
    buyer_after_zero = _get_credits(client, querier["headers"])
    assert buyer_after_zero == buyer_credits - 1

    # 5. Simulate full backend restart -> DuckDB + SQLite reload cleanly and query still succeeds
    reset_storage_connection()
    init_db()
    init_storage()
    assert dataset_table_exists(ds_id)

    with patch(
        "app.routers.query.generate_sql",
        return_value=f"SELECT COUNT(*) AS n, SUM(amount) AS total FROM {table_name}",
    ):
        q_restart = client.post(
            "/query",
            headers=querier["headers"],
            json={"query": "Count and sum orders after restart", "dataset_id": ds_id},
        )
    assert q_restart.status_code == 200, q_restart.text
    assert q_restart.json()["results"][0]["n"] == 2
    assert q_restart.json()["results"][0]["total"] == 85


def test_dataset_metadata_consistent_across_list_detail_and_search(client):
    """
    Regression test: ensure the same dataset ID returns identical domain, unlock_price,
    quality_score, domain_relevance_score, overall_score, filename, ownership, and availability
    across GET /datasets (My Datasets / Marketplace browse), GET /datasets/{id}, and POST /datasets/search.
    """
    owner = _register(client, "meta_owner")
    other = _register(client, "meta_other")

    csv_body = (
        "restaurant_id,name,city,rating,votes\n"
        "1,Spice Route,Bangalore,4.5,320\n"
        "2,Coastal Kitchen,Mumbai,4.2,210\n"
        "3,Tandoor House,Delhi,4.7,540\n"
    )
    up_telecom = client.post(
        "/datasets/upload",
        headers=owner["headers"],
        files={"file": ("Zomato Restaurant Dataset.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
        data={"name": "Customer Churn Analysis Q4", "domain": "telecom", "visibility": "public"},
    )
    assert up_telecom.status_code == 201, up_telecom.text
    ds_a = up_telecom.json()
    ds_a_id = ds_a["id"]

    up_general = client.post(
        "/datasets/upload",
        headers=other["headers"],
        files={"file": ("Zomato Restaurant Dataset.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
        data={"name": "Zomato Restaurant Dataset", "domain": "general", "visibility": "public"},
    )
    assert up_general.status_code == 201, up_general.text
    ds_b_id = up_general.json()["id"]

    # Fetch via GET /datasets (all, mine, community), GET /datasets/{id}, and POST /datasets/search
    list_all = {d["id"]: d for d in client.get("/datasets", headers=owner["headers"]).json()["datasets"]}
    list_mine = {d["id"]: d for d in client.get("/datasets?source=mine", headers=owner["headers"]).json()["datasets"]}
    list_comm = {d["id"]: d for d in client.get("/datasets?source=community", headers=owner["headers"]).json()["datasets"]}
    detail_a = client.get(f"/datasets/{ds_a_id}", headers=owner["headers"]).json()
    search_res = client.post(
        "/datasets/search",
        headers=owner["headers"],
        json={"query": "Zomato", "limit": 50},
    )
    assert search_res.status_code == 200, search_res.text
    search_by_id = {r["dataset_id"]: r for r in search_res.json()["results"]}

    # Both datasets must be discoverable when searching "Zomato" (including via filename)
    assert ds_a_id in list_all and ds_a_id in list_mine and ds_a_id in list_comm
    assert ds_a_id in search_by_id
    assert ds_b_id in search_by_id

    for ds_id, expected in ((ds_a_id, detail_a), (ds_b_id, list_all[ds_b_id])):
        listed = list_all[ds_id]
        searched = search_by_id[ds_id]

        assert listed["domain"] == expected["domain"] == searched["domain"]
        assert listed["unlock_price"] == expected["unlock_price"] == searched["unlock_price"]
        assert listed["quality_score"] == expected["quality_score"] == searched["quality_score"]
        assert (
            listed["domain_relevance_score"]
            == expected["domain_relevance_score"]
            == searched["domain_relevance_score"]
        )
        assert listed["overall_score"] == expected["overall_score"] == searched["overall_score"]
        assert listed["filename"] == expected["filename"] == searched["filename"]
        assert listed["user_id"] == expected["user_id"] == searched["user_id"]
        assert listed["rows_count"] == expected["rows_count"] == searched["rows_count"]
        assert listed["columns_count"] == expected["columns_count"] == searched["columns_count"]
        assert listed["storage_available"] == expected["storage_available"] == searched["storage_available"]
        assert listed["availability"] == expected["availability"] == searched["availability"]
        assert listed["visibility"] == expected["visibility"] == searched["visibility"]
        assert listed["is_curated"] == expected["is_curated"] == searched["is_curated"]

