import uuid
import pytest
from app.services.nl_query import set_ai_generator
from app.services.storage import get_dataset_table_name
from app.database import get_db_connection


def create_user_with_token(client, prefix="user"):
    unique_email = f"{prefix}_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post("/auth/register", json={
        "email": unique_email,
        "password": "Password123!",
        "full_name": f"{prefix.capitalize()} FullName"
    })
    assert res.status_code == 201
    data = res.json()
    token = data["access_token"]
    user_id = data["user"]["id"]
    return {
        "user_id": user_id,
        "email": unique_email,
        "headers": {"Authorization": f"Bearer {token}"}
    }


def upload_sample_dataset(client, user_headers, name="Test Dataset"):
    csv_data = "metric,category,val\nm1,A,10\nm2,B,20\nm3,A,30\n"
    files = {"file": ("data.csv", csv_data, "text/csv")}
    res = client.post(
        "/datasets/upload",
        headers=user_headers,
        files=files,
        data={"domain": "technology", "name": name}
    )
    assert res.status_code == 201
    return res.json()


@pytest.fixture(autouse=True)
def reset_ai():
    yield
    set_ai_generator(None)


# 1. User A sees their own history
def test_user_a_sees_own_history(client):
    user_a = create_user_with_token(client, "usera")
    ds = upload_sample_dataset(client, user_a["headers"], "Sales Dataset A")
    table = get_dataset_table_name(ds["id"])

    set_ai_generator(lambda q, t, cols: f"SELECT metric, val FROM {table}")
    res = client.post("/query", headers=user_a["headers"], json={
        "query": "Show metrics and values for User A",
        "dataset_id": ds["id"]
    })
    assert res.status_code == 200

    # Retrieve history
    hist_res = client.get("/query/history", headers=user_a["headers"])
    assert hist_res.status_code == 200
    data = hist_res.json()
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["userId"] == user_a["user_id"]
    assert item["user_id"] == user_a["user_id"]
    assert item["naturalPrompt"] == "Show metrics and values for User A"
    assert "metric" in item["generatedSql"]
    assert item["status"] == "SUCCESS"
    assert item["datasetName"] == "Sales Dataset A"


# 2. User B sees their own history but not User A's records
def test_history_session_isolation_between_users(client):
    user_a = create_user_with_token(client, "user_iso_a")
    user_b = create_user_with_token(client, "user_iso_b")

    ds_a = upload_sample_dataset(client, user_a["headers"], "Dataset Alpha")
    ds_b = upload_sample_dataset(client, user_b["headers"], "Dataset Beta")

    table_a = get_dataset_table_name(ds_a["id"])
    table_b = get_dataset_table_name(ds_b["id"])

    # User A executes query
    set_ai_generator(lambda q, t, cols: f"SELECT metric FROM {table_a}")
    res_a = client.post("/query", headers=user_a["headers"], json={
        "query": "User A secret private question",
        "dataset_id": ds_a["id"]
    })
    assert res_a.status_code == 200

    # User B executes query
    set_ai_generator(lambda q, t, cols: f"SELECT category FROM {table_b}")
    res_b = client.post("/query", headers=user_b["headers"], json={
        "query": "User B confidential analysis",
        "dataset_id": ds_b["id"]
    })
    assert res_b.status_code == 200

    # Check User A's history
    hist_a = client.get("/query/history", headers=user_a["headers"]).json()
    a_prompts = [it["naturalPrompt"] for it in hist_a["items"]]
    assert "User A secret private question" in a_prompts
    assert "User B confidential analysis" not in a_prompts
    for it in hist_a["items"]:
        assert it["userId"] == user_a["user_id"]

    # Check User B's history
    hist_b = client.get("/query/history", headers=user_b["headers"]).json()
    b_prompts = [it["naturalPrompt"] for it in hist_b["items"]]
    assert "User B confidential analysis" in b_prompts
    assert "User A secret private question" not in b_prompts
    for it in hist_b["items"]:
        assert it["userId"] == user_b["user_id"]


# 3. An authenticated user cannot access another user's history by modifying request parameters
def test_cannot_access_other_user_history_via_query_params(client):
    user_a = create_user_with_token(client, "user_victim")
    user_b = create_user_with_token(client, "user_attacker")

    ds_a = upload_sample_dataset(client, user_a["headers"], "Victim Dataset")
    table_a = get_dataset_table_name(ds_a["id"])

    set_ai_generator(lambda q, t, cols: f"SELECT metric FROM {table_a}")
    client.post("/query", headers=user_a["headers"], json={
        "query": "Victim proprietary prompt",
        "dataset_id": ds_a["id"]
    })

    # Attacker tries passing user_id or userId query parameters pointing to victim
    res_attack_1 = client.get(
        f"/query/history?user_id={user_a['user_id']}",
        headers=user_b["headers"]
    )
    assert res_attack_1.status_code == 200
    data_1 = res_attack_1.json()
    assert "Victim proprietary prompt" not in [it["naturalPrompt"] for it in data_1["items"]]
    for it in data_1["items"]:
        assert it["userId"] == user_b["user_id"]

    res_attack_2 = client.get(
        f"/query/history?userId={user_a['user_id']}",
        headers=user_b["headers"]
    )
    assert res_attack_2.status_code == 200
    data_2 = res_attack_2.json()
    assert "Victim proprietary prompt" not in [it["naturalPrompt"] for it in data_2["items"]]
    for it in data_2["items"]:
        assert it["userId"] == user_b["user_id"]


# 4. Unauthenticated requests are rejected with 401
def test_unauthenticated_requests_rejected(client):
    # No header
    res1 = client.get("/query/history")
    assert res1.status_code == 401

    # Invalid token
    res2 = client.get("/query/history", headers={"Authorization": "Bearer invalid_token_123"})
    assert res2.status_code == 401

    # Trailing slash also rejects
    res3 = client.get("/query/history/")
    assert res3.status_code == 401


# 5. Failed queries appear only in the history of the user who submitted them
def test_failed_queries_associated_with_correct_user(client):
    user_fail = create_user_with_token(client, "user_fail")
    user_clean = create_user_with_token(client, "user_clean")

    ds = upload_sample_dataset(client, user_fail["headers"], "Fail Test DS")
    table = get_dataset_table_name(ds["id"])

    # User attempts dangerous SQL injection / DROP TABLE
    set_ai_generator(lambda q, t, cols: f"DROP TABLE {table}")
    bad_res = client.post("/query", headers=user_fail["headers"], json={
        "query": "Drop this table immediately",
        "dataset_id": ds["id"]
    })
    assert bad_res.status_code == 422

    # Check User Fail history
    hist_fail = client.get("/query/history", headers=user_fail["headers"]).json()
    assert hist_fail["total"] >= 1
    rejected_items = [it for it in hist_fail["items"] if it["status"] == "SQL_REJECTED"]
    assert len(rejected_items) >= 1
    assert rejected_items[0]["naturalPrompt"] == "Drop this table immediately"
    assert rejected_items[0]["userId"] == user_fail["user_id"]

    # Check User Clean history: does NOT see the failed query
    hist_clean = client.get("/query/history", headers=user_clean["headers"]).json()
    assert "Drop this table immediately" not in [it["naturalPrompt"] for it in hist_clean["items"]]


# 6. Pagination and newest-first ordering work correctly
def test_pagination_and_newest_first_ordering(client):
    user = create_user_with_token(client, "user_pages")
    ds = upload_sample_dataset(client, user["headers"], "Paging Dataset")
    table = get_dataset_table_name(ds["id"])

    # Execute 5 queries sequentially
    prompts = [f"Query number {i}" for i in range(1, 6)]
    for p in prompts:
        set_ai_generator(lambda q, t, cols: f"SELECT metric FROM {table}")
        res = client.post("/query", headers=user["headers"], json={
            "query": p,
            "dataset_id": ds["id"]
        })
        assert res.status_code == 200

    # Page 1, limit 2: should return the 2 newest queries (Query 5, Query 4)
    p1 = client.get("/query/history?page=1&limit=2", headers=user["headers"]).json()
    assert p1["total"] == 5
    assert p1["page"] == 1
    assert p1["limit"] == 2
    assert p1["has_more"] is True
    assert len(p1["items"]) == 2
    assert p1["items"][0]["naturalPrompt"] == "Query number 5"
    assert p1["items"][1]["naturalPrompt"] == "Query number 4"

    # Page 2, limit 2: should return Query 3, Query 2
    p2 = client.get("/query/history?page=2&limit=2", headers=user["headers"]).json()
    assert p2["page"] == 2
    assert p2["has_more"] is True
    assert len(p2["items"]) == 2
    assert p2["items"][0]["naturalPrompt"] == "Query number 3"
    assert p2["items"][1]["naturalPrompt"] == "Query number 2"

    # Page 3, limit 2: should return Query 1
    p3 = client.get("/query/history?page=3&limit=2", headers=user["headers"]).json()
    assert p3["page"] == 3
    assert p3["has_more"] is False
    assert len(p3["items"]) == 1
    assert p3["items"][0]["naturalPrompt"] == "Query number 1"


# 7. Search and status filtering work on the history endpoint
def test_history_search_and_status_filtering(client):
    user = create_user_with_token(client, "user_search")
    ds = upload_sample_dataset(client, user["headers"], "Filter DS")
    table = get_dataset_table_name(ds["id"])

    # 1 success query
    set_ai_generator(lambda q, t, cols: f"SELECT metric FROM {table}")
    client.post("/query", headers=user["headers"], json={
        "query": "Revenue by Region",
        "dataset_id": ds["id"]
    })

    # 1 failed query
    set_ai_generator(lambda q, t, cols: f"DELETE FROM {table}")
    client.post("/query", headers=user["headers"], json={
        "query": "Delete old revenue metrics",
        "dataset_id": ds["id"]
    })

    # Filter by SUCCESS
    res_succ = client.get("/query/history?status=SUCCESS", headers=user["headers"]).json()
    assert all(it["status"] == "SUCCESS" for it in res_succ["items"])
    assert any("Revenue by Region" in it["naturalPrompt"] for it in res_succ["items"])

    # Filter by SQL_REJECTED
    res_rej = client.get("/query/history?status=SQL_REJECTED", headers=user["headers"]).json()
    assert all(it["status"] == "SQL_REJECTED" for it in res_rej["items"])
    assert any("Delete old revenue" in it["naturalPrompt"] for it in res_rej["items"])

    # Search keyword
    res_search = client.get("/query/history?search=Region", headers=user["headers"]).json()
    assert len(res_search["items"]) == 1
    assert res_search["items"][0]["naturalPrompt"] == "Revenue by Region"


# 8. Unowned / orphan records are preserved and never exposed
def test_unowned_records_never_exposed(client):
    user = create_user_with_token(client, "user_orphan_check")
    conn = get_db_connection()
    c = conn.cursor()
    # Insert an unowned record with non-existent user_id
    c.execute("""
        INSERT INTO queries (id, user_id, query_text, results_json, status, created_at)
        VALUES ('qry_orphan_999', 'usr_non_existent', 'Orphan sensitive prompt', '{}', 'SUCCESS', '2026-01-01T00:00:00')
    """)
    conn.commit()

    # User fetches history
    res = client.get("/query/history", headers=user["headers"]).json()
    assert "Orphan sensitive prompt" not in [it["naturalPrompt"] for it in res["items"]]
