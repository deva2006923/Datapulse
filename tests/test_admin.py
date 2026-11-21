import uuid
import pytest
from app.config import settings
from app.database import get_db_connection
from app.services.admin_bootstrap import create_or_promote_admin, promote_user_to_admin


def create_user(client, email=None, password="Password123!", full_name="Regular User"):
    unique_email = email or f"user_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post("/auth/register", json={
        "email": unique_email,
        "password": password,
        "full_name": full_name
    })
    assert res.status_code == 201
    data = res.json()
    return {
        "user_id": data["user"]["id"],
        "email": unique_email,
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"}
    }


def setup_admin_user(client, password="AdminSecretPass123!"):
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com")
    conn = get_db_connection()
    # Check if admin already exists in test db, promote or create
    res = create_or_promote_admin(email=admin_email, password=password, full_name="DataPulse Administrator", conn=conn)
    
    # Login as admin to get token
    login_res = client.post("/auth/login", json={
        "email": admin_email,
        "password": password
    })
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["user"]["is_admin"] is True
    return {
        "user_id": data["user"]["id"],
        "email": admin_email,
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"}
    }


ADMIN_ENDPOINTS = [
    ("/admin/overview", "GET"),
    ("/admin/analytics", "GET"),
    ("/admin/users", "GET"),
    ("/admin/users/usr_dummy", "GET"),
    ("/admin/users/usr_dummy/queries", "GET"),
    ("/admin/users/usr_dummy/datasets", "GET"),
    ("/admin/users/usr_dummy/transactions", "GET"),
    ("/admin/users/usr_dummy/activity", "GET"),
    ("/admin/datasets", "GET"),
    ("/admin/datasets/ds_dummy", "GET"),
    ("/admin/queries", "GET"),
    ("/admin/transactions", "GET"),
    ("/admin/activity", "GET"),
    ("/admin/audit-logs", "GET"),
]


# 1. Unauthenticated requests receive HTTP 401 on every admin endpoint
@pytest.mark.parametrize("endpoint,method", ADMIN_ENDPOINTS)
def test_admin_endpoints_reject_unauthenticated_with_401(client, endpoint, method):
    res = client.request(method, endpoint)
    assert res.status_code == 401
    assert "detail" in res.json()


# 2. Authenticated non-admin regular users receive HTTP 403 on every admin endpoint
@pytest.mark.parametrize("endpoint,method", ADMIN_ENDPOINTS)
def test_admin_endpoints_reject_regular_user_with_403(client, endpoint, method):
    reg_user = create_user(client, full_name="Alice Regular")
    res = client.request(method, endpoint, headers=reg_user["headers"])
    assert res.status_code == 403
    assert "Administrative privileges required" in res.json()["detail"]


# 3. Registration with designated admin email alone does NOT grant admin rights (403)
def test_registering_admin_email_does_not_grant_admin_access(client):
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com")
    # Register with a user who submits admin email (if not yet registered)
    # Use distinct case to test normalization
    mixed_case_admin_email = admin_email.upper()
    
    # Create random regular user first to avoid collisions if admin exists
    reg_user = create_user(client, prefix="notadmin") if "prefix" in create_user.__code__.co_varnames else create_user(client)
    
    # Check that is_admin is False on registration
    reg_res = client.post("/auth/register", json={
        "email": f"attacker_{uuid.uuid4().hex[:6]}@example.com",
        "password": "Password123!",
        "full_name": "Attacker"
    })
    assert reg_res.status_code == 201
    assert reg_res.json()["user"]["is_admin"] is False
    
    # If someone tries to register with admin_email directly:
    # First ensure we test a clean email if admin_email wasn't registered yet
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE LOWER(email) = ?", (admin_email.lower(),))
    conn.commit()
    
    reg_admin_attempt = client.post("/auth/register", json={
        "email": mixed_case_admin_email,
        "password": "Password123!",
        "full_name": "Pretender"
    })
    assert reg_admin_attempt.status_code == 201
    pretender_token = reg_admin_attempt.json()["access_token"]
    pretender_headers = {"Authorization": f"Bearer {pretender_token}"}
    
    # User's registration response must NOT have is_admin = True
    assert reg_admin_attempt.json()["user"]["is_admin"] is False
    
    # User's /auth/me must NOT have is_admin = True
    me_res = client.get("/auth/me", headers=pretender_headers)
    assert me_res.status_code == 200
    assert me_res.json()["is_admin"] is False
    
    # Calling admin endpoints must return HTTP 403!
    res_overview = client.get("/admin/overview", headers=pretender_headers)
    assert res_overview.status_code == 403


# 4. Correctly provisioned administrator can access all admin endpoints
def test_provisioned_admin_access_success(client):
    admin = setup_admin_user(client)
    
    # 4a. Overview
    overview_res = client.get("/admin/overview", headers=admin["headers"])
    assert overview_res.status_code == 200
    data = overview_res.json()
    assert "total_users" in data
    assert "total_datasets" in data
    assert "total_queries" in data
    assert "total_credits_issued" in data
    assert "recent_activity" in data
    assert isinstance(data["recent_activity"], list)

    # 4b. Users list
    users_res = client.get("/admin/users", headers=admin["headers"])
    assert users_res.status_code == 200
    users_data = users_res.json()
    assert users_data["total"] >= 1
    assert any(u["email"].lower() == admin["email"].lower() and u["is_admin"] is True for u in users_data["items"])

    # 4c. User detail
    admin_detail = client.get(f"/admin/users/{admin['user_id']}", headers=admin["headers"])
    assert admin_detail.status_code == 200
    assert admin_detail.json()["id"] == admin["user_id"]
    assert admin_detail.json()["is_admin"] is True

    # 4d. Datasets list
    datasets_res = client.get("/admin/datasets", headers=admin["headers"])
    assert datasets_res.status_code == 200
    assert "items" in datasets_res.json()

    # 4e. Global queries list
    queries_res = client.get("/admin/queries", headers=admin["headers"])
    assert queries_res.status_code == 200
    assert "items" in queries_res.json()

    # 4f. Transactions list
    tx_res = client.get("/admin/transactions", headers=admin["headers"])
    assert tx_res.status_code == 200
    assert "items" in tx_res.json()

    # 4g. Audit logs list
    audit_res = client.get("/admin/audit-logs", headers=admin["headers"])
    assert audit_res.status_code == 200
    assert audit_res.json()["total"] >= 1


# 5. Parameter tampering (e.g. changing ?user_id=...) cannot bypass authorization
def test_parameter_tampering_cannot_bypass_admin_auth(client):
    admin = setup_admin_user(client)
    regular = create_user(client, full_name="Regular Bob")

    # Regular user supplies admin's user_id in query parameter
    tampered_res = client.get(f"/admin/overview?user_id={admin['user_id']}&email={admin['email']}", headers=regular["headers"])
    assert tampered_res.status_code == 403

    tampered_users = client.get(f"/admin/users?user_id={admin['user_id']}", headers=regular["headers"])
    assert tampered_users.status_code == 403


# 6. Admin APIs do not leak passwords, tokens, or secret hashes
def test_admin_apis_do_not_leak_passwords_or_secrets(client):
    admin = setup_admin_user(client)
    regular = create_user(client, password="MySecretPassword123!", full_name="Secretive User")

    # Inspect users listing
    users_res = client.get("/admin/users", headers=admin["headers"])
    assert users_res.status_code == 200
    raw_text = users_res.text.lower()
    assert "password" not in raw_text
    assert "password_hash" not in raw_text
    assert "mysecretpassword123!" not in raw_text
    assert "secret_key" not in raw_text

    # Inspect user detail
    detail_res = client.get(f"/admin/users/{regular['user_id']}", headers=admin["headers"])
    assert detail_res.status_code == 200
    raw_detail_text = detail_res.text.lower()
    assert "password_hash" not in raw_detail_text
    assert "mysecretpassword123!" not in raw_detail_text
    assert "token" not in raw_detail_text


# 7. Pagination, searching, and filtering on admin endpoints
def test_admin_pagination_and_filters(client):
    admin = setup_admin_user(client)
    
    # Create several distinct users
    u1 = create_user(client, full_name="FilterAlpha User")
    u2 = create_user(client, full_name="FilterBeta User")

    # Search by full name
    search_res = client.get("/admin/users?search=FilterAlpha", headers=admin["headers"])
    assert search_res.status_code == 200
    data = search_res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == u1["user_id"]

    # Pagination
    page_res = client.get("/admin/users?page=1&limit=2", headers=admin["headers"])
    assert page_res.status_code == 200
    assert len(page_res.json()["items"]) <= 2
    assert page_res.json()["page"] == 1
    assert page_res.json()["limit"] == 2


# 8. User-specific query history remains isolated from normal users
def test_user_query_history_isolation_unaffected(client):
    user_a = create_user(client, full_name="User Alpha")
    user_b = create_user(client, full_name="User Beta")
    admin = setup_admin_user(client)

    # User A runs a query record via standard endpoint or mocked DB
    conn = get_db_connection()
    cursor = conn.cursor()
    qid = f"qry_test_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
        INSERT INTO queries (id, user_id, query_text, results_json, dataset_name, generated_sql, status, created_at)
        VALUES (?, ?, 'User A private prompt', '[]', 'Private Dataset A', 'SELECT * FROM test_a', 'SUCCESS', CURRENT_TIMESTAMP)
    """, (qid, user_a["user_id"]))
    conn.commit()

    # User B checks their query history -> must NOT see User A's query
    user_b_hist = client.get("/query/history", headers=user_b["headers"])
    assert user_b_hist.status_code == 200
    b_items = user_b_hist.json()["items"]
    assert not any(item["id"] == qid for item in b_items)

    # Admin checks global queries -> sees query
    admin_queries = client.get(f"/admin/queries?user_id={user_a['user_id']}", headers=admin["headers"])
    assert admin_queries.status_code == 200
    assert any(q["id"] == qid for q in admin_queries.json()["items"])


# 9. Complete User History Explorer and Activity Timeline
def test_admin_user_history_explorer(client):
    admin = setup_admin_user(client)
    user = create_user(client, full_name="Explorer Target")
    uid = user["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Add dataset
    ds_id = f"ds_test_{uuid.uuid4().hex[:8]}"
    cur.execute("""
        INSERT INTO datasets (id, user_id, name, filename, domain, rows_count, columns_count, schema_json, content_summary, created_at)
        VALUES (?, ?, 'Target Dataset', 'target.csv', 'technology', 100, 5, '{}', 'Summary', '2026-01-01T10:00:00')
    """, (ds_id, uid))

    # 2. Add evaluation
    cur.execute("""
        INSERT INTO evaluations (id, dataset_id, status, quality_score, overall_score, credits_awarded, created_at)
        VALUES (?, ?, 'COMPLETED', 90.0, 92.5, 50, '2026-01-01T10:05:00')
    """, (f"eval_{uuid.uuid4().hex[:8]}", ds_id))

    # 3. Add queries (1 success, 1 failed)
    q1_id = f"qry_ok_{uuid.uuid4().hex[:8]}"
    cur.execute("""
        INSERT INTO queries (id, user_id, query_text, results_json, dataset_id, dataset_name, generated_sql, status, credits_charged, execution_time_ms, created_at)
        VALUES (?, ?, 'Successful query prompt', '[]', ?, 'Target Dataset', 'SELECT * FROM target', 'SUCCESS', 5, 25, '2026-01-02T12:00:00')
    """, (q1_id, uid, ds_id))

    q2_id = f"qry_fail_{uuid.uuid4().hex[:8]}"
    cur.execute("""
        INSERT INTO queries (id, user_id, query_text, results_json, dataset_id, dataset_name, generated_sql, status, credits_charged, error_message, created_at)
        VALUES (?, ?, 'Failing query prompt', '[]', ?, 'Target Dataset', NULL, 'SQL_REJECTED', 0, 'Syntax error', '2026-01-03T15:00:00')
    """, (q2_id, uid, ds_id))

    # 4. Add transaction
    tx_id = f"tx_test_{uuid.uuid4().hex[:8]}"
    cur.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, 50, 'reward', 'Upload reward for dataset', 'completed', '2026-01-01T10:05:00')
    """, (tx_id, uid))
    conn.commit()

    # Verify user detail breakdown
    detail_res = client.get(f"/admin/users/{uid}", headers=admin["headers"])
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["total_datasets"] == 1
    assert detail["total_queries"] == 2
    assert detail["total_queries_successful"] == 1
    assert detail["total_queries_failed"] == 1
    assert len(detail["datasets"]) == 1
    assert detail["datasets"][0]["name"] == "Target Dataset"
    assert detail["datasets"][0]["availability"] in ("Available", "Metadata Only")

    # Verify user-specific queries endpoint
    user_queries_res = client.get(f"/admin/users/{uid}/queries", headers=admin["headers"])
    assert user_queries_res.status_code == 200
    uq_data = user_queries_res.json()
    assert uq_data["total"] == 2
    assert any(q["id"] == q1_id and q["execution_status"] == "SUCCESS" for q in uq_data["items"])
    assert any(q["id"] == q2_id and q["execution_status"] == "SQL_REJECTED" for q in uq_data["items"])

    # Query status filter on user queries
    success_filter_res = client.get(f"/admin/users/{uid}/queries?status=SUCCESS", headers=admin["headers"])
    assert success_filter_res.status_code == 200
    assert success_filter_res.json()["total"] == 1
    assert success_filter_res.json()["items"][0]["id"] == q1_id

    # Verify user-specific datasets endpoint
    user_ds_res = client.get(f"/admin/users/{uid}/datasets", headers=admin["headers"])
    assert user_ds_res.status_code == 200
    assert user_ds_res.json()["total"] == 1
    assert user_ds_res.json()["items"][0]["id"] == ds_id

    # Verify user-specific transactions endpoint
    user_tx_res = client.get(f"/admin/users/{uid}/transactions", headers=admin["headers"])
    assert user_tx_res.status_code == 200
    assert user_tx_res.json()["total"] == 2  # Signup bonus + reward
    assert any(t["id"] == tx_id for t in user_tx_res.json()["items"])

    # Verify user activity timeline endpoint
    user_act_res = client.get(f"/admin/users/{uid}/activity", headers=admin["headers"])
    assert user_act_res.status_code == 200
    timeline = user_act_res.json()
    assert timeline["total"] >= 4
    act_types = [item["type"] for item in timeline["items"]]
    assert "USER_REGISTER" in act_types
    assert "DATASET_UPLOAD" in act_types
    assert "QUERY_EXECUTION" in act_types
    assert "CREDIT_TRANSACTION" in act_types
    # Verify chronological ordering
    timestamps = [item["timestamp"] for item in timeline["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


# 10. Global Activity Explorer endpoint and multi-filter verification
def test_admin_global_activity_explorer(client):
    admin = setup_admin_user(client)
    user = create_user(client, full_name="Activity Subject")
    uid = user["user_id"]

    # Global activity view
    global_act_res = client.get("/admin/activity?limit=10", headers=admin["headers"])
    assert global_act_res.status_code == 200
    data = global_act_res.json()
    assert data["total"] >= 1
    assert len(data["items"]) <= 10
    assert "timestamp" in data["items"][0]
    assert "type" in data["items"][0]

    # Filter global activity by user_id
    scoped_res = client.get(f"/admin/activity?user_id={uid}", headers=admin["headers"])
    assert scoped_res.status_code == 200
    scoped_data = scoped_res.json()
    for item in scoped_data["items"]:
        assert item["user_id"] == uid or (item["metadata"] and item["metadata"].get("target_resource") == uid)


# 11. User directory activity, date filtering, and sorting
def test_admin_user_directory_advanced_filters(client):
    admin = setup_admin_user(client)
    active_user = create_user(client, full_name="Active Querier")
    inactive_user = create_user(client, full_name="Silent Lurker")

    # Insert query for active user
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO queries (id, user_id, query_text, results_json, status, created_at)
        VALUES (?, ?, 'Active query', '[]', 'SUCCESS', CURRENT_TIMESTAMP)
    """, (f"qry_{uuid.uuid4().hex[:8]}", active_user["user_id"]))
    conn.commit()

    # Filter has_queries
    queries_filter_res = client.get("/admin/users?activity=has_queries", headers=admin["headers"])
    assert queries_filter_res.status_code == 200
    has_queries_ids = [u["id"] for u in queries_filter_res.json()["items"]]
    assert active_user["user_id"] in has_queries_ids
    assert inactive_user["user_id"] not in has_queries_ids

    # Sort by queries_count descending
    sort_res = client.get("/admin/users?sort_by=queries_count&sort_order=desc", headers=admin["headers"])
    assert sort_res.status_code == 200
    items = sort_res.json()["items"]
    assert items[0]["queries_count"] >= items[-1]["queries_count"]

    # Search by exact user ID
    id_search = client.get(f"/admin/users?search={active_user['user_id']}", headers=admin["headers"])
    assert id_search.status_code == 200
    assert id_search.json()["total"] == 1
    assert id_search.json()["items"][0]["id"] == active_user["user_id"]
    assert id_search.json()["items"][0]["last_activity"] is not None

    # Inactive filter (both 'inactive' and legacy 'no_activity' alias)
    for filter_val in ("inactive", "no_activity"):
        inact_res = client.get(f"/admin/users?activity={filter_val}", headers=admin["headers"])
        assert inact_res.status_code == 200
        inact_ids = [u["id"] for u in inact_res.json()["items"]]
        assert inactive_user["user_id"] in inact_ids
        assert active_user["user_id"] not in inact_ids


# 12. Platform Analytics: date ranges, granularities, KPIs, and leaderboards
def test_admin_analytics_date_ranges_and_leaderboards(client):
    admin = setup_admin_user(client)
    u = create_user(client, full_name="Analytics Power User")
    uid = u["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()
    ds_id = f"ds_an_{uuid.uuid4().hex[:8]}"
    cur.execute("""
        INSERT INTO datasets (id, user_id, name, filename, domain, rows_count, columns_count, schema_json, content_summary, unlock_price, created_at)
        VALUES (?, ?, 'Analytics Sales', 'sales.csv', 'retail', 250, 6, '{"region":"string","revenue":"float"}', 'Sales data', 15, '2026-02-10T09:00:00')
    """, (ds_id, uid))
    cur.execute("""
        INSERT INTO evaluations (id, dataset_id, status, progress, quality_score, schema_fidelity_score, completeness_score, domain_relevance_score, overall_score, credits_awarded, created_at, updated_at)
        VALUES (?, ?, 'completed', 100, 88.0, 90.0, 92.0, 85.0, 88.0, 94, '2026-02-10T09:01:00', '2026-02-10T09:01:00')
    """, (f"eval_{uuid.uuid4().hex[:8]}", ds_id))
    cur.execute("""
        INSERT INTO queries (id, user_id, query_text, results_json, dataset_id, dataset_name, generated_sql, status, credits_charged, execution_time_ms, result_count, created_at)
        VALUES (?, ?, 'Top revenue regions', '[]', ?, 'Analytics Sales', 'SELECT region FROM t', 'SUCCESS', 1, 35, 10, '2026-02-11T14:30:00')
    """, (f"qry_an_{uuid.uuid4().hex[:8]}", uid, ds_id))
    conn.commit()

    # All-time daily analytics
    res = client.get("/admin/analytics?range=all&granularity=daily", headers=admin["headers"])
    assert res.status_code == 200
    body = res.json()
    assert body["granularity"] == "daily"
    assert body["kpis"]["total_users"] >= 2
    assert body["kpis"]["total_datasets"] >= 1
    assert body["kpis"]["total_queries"] >= 1
    assert len(body["user_registration_trend"]) >= 1
    assert len(body["dataset_upload_trend"]) >= 1
    assert len(body["query_activity_trend"]) >= 1
    assert len(body["credit_movement_trend"]) >= 1
    assert any(d["dataset_id"] == ds_id for d in body["most_queried_datasets"])
    assert any(x["user_id"] == uid for x in body["most_active_users"])
    assert any(x["user_id"] == uid for x in body["most_contributing_users"])

    # Custom date range & weekly/monthly granularity
    for gran in ("weekly", "monthly"):
        g_res = client.get(
            f"/admin/analytics?range=custom&start_date=2026-02-01&end_date=2026-02-28&granularity={gran}",
            headers=admin["headers"],
        )
        assert g_res.status_code == 200
        g_body = g_res.json()
        assert g_body["granularity"] == gran
        assert g_body["kpis"]["datasets_in_period"] >= 1
        assert g_body["kpis"]["total_queries"] >= 1


# 13. Complete pagination across all pages, empty user history, and credit running balances
def test_admin_user_pagination_empty_history_and_credit_balances(client):
    admin = setup_admin_user(client)
    heavy_user = create_user(client, full_name="Heavy Paginated User")
    empty_user = create_user(client, full_name="Brand New Empty User")
    h_uid = heavy_user["user_id"]
    e_uid = empty_user["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    # Insert 12 queries for heavy_user to test multi-page server-side pagination (limit=5 -> 3 pages)
    inserted_qids = []
    for i in range(12):
        qid = f"qry_pg_{i:02d}_{uuid.uuid4().hex[:6]}"
        inserted_qids.append(qid)
        cur.execute("""
            INSERT INTO queries (id, user_id, query_text, results_json, dataset_name, generated_sql, status, credits_charged, execution_time_ms, created_at)
            VALUES (?, ?, ?, '[]', 'Paginated DS', 'SELECT 1', 'SUCCESS', 1, 10, ?)
        """, (qid, h_uid, f"Paginated question {i}", f"2026-03-{i+1:02d}T10:00:00"))

    # Insert positive & negative transactions to verify running balance_after and direction filters
    cur.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, 50, 'upload_reward', 'Basic upload reward', 'completed', '2026-03-01T11:00:00')
    """, (f"tx_pos_{uuid.uuid4().hex[:6]}", h_uid))
    cur.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, -10, 'query_fee', 'Query execution fee', 'completed', '2026-03-02T11:00:00')
    """, (f"tx_neg_{uuid.uuid4().hex[:6]}", h_uid))
    conn.commit()

    # Walk all pages for heavy_user queries: verify exact count, no duplicates, no missing records
    collected_ids = []
    page = 1
    while True:
        r = client.get(f"/admin/users/{h_uid}/queries?page={page}&limit=5", headers=admin["headers"])
        assert r.status_code == 200
        payload = r.json()
        assert payload["total"] == 12
        collected_ids.extend(item["id"] for item in payload["items"])
        if not payload["has_more"]:
            break
        page += 1

    assert page == 3
    assert len(collected_ids) == 12
    assert len(set(collected_ids)) == 12
    assert set(collected_ids) == set(inserted_qids)

    # Verify empty history user handles 0 queries and 0 datasets cleanly
    e_detail = client.get(f"/admin/users/{e_uid}", headers=admin["headers"])
    assert e_detail.status_code == 200
    assert e_detail.json()["total_queries"] == 0
    assert e_detail.json()["total_datasets"] == 0

    e_queries = client.get(f"/admin/users/{e_uid}/queries", headers=admin["headers"])
    assert e_queries.status_code == 200
    assert e_queries.json()["total"] == 0
    assert e_queries.json()["items"] == []

    # Verify transactions direction filter & running balance_after
    pos_tx = client.get(f"/admin/users/{h_uid}/transactions?direction=positive", headers=admin["headers"])
    assert pos_tx.status_code == 200
    assert all(t["amount"] > 0 for t in pos_tx.json()["items"])

    neg_tx = client.get(f"/admin/users/{h_uid}/transactions?direction=negative", headers=admin["headers"])
    assert neg_tx.status_code == 200
    assert neg_tx.json()["total"] == 1
    assert neg_tx.json()["items"][0]["amount"] == -10
    assert isinstance(neg_tx.json()["items"][0]["balance_after"], int)


# 14. Dataset inspection detail, global activity sort order, and token/secret redaction
def test_admin_dataset_detail_and_activity_sort_and_redaction(client):
    admin = setup_admin_user(client)
    owner = create_user(client, full_name="Dataset Owner")
    oid = owner["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()
    ds_id = f"ds_insp_{uuid.uuid4().hex[:8]}"
    cur.execute("""
        INSERT INTO datasets (id, user_id, name, filename, domain, rows_count, columns_count, schema_json, content_summary, unlock_price, created_at)
        VALUES (?, ?, 'Inspection Catalog', 'inspect.csv', 'healthcare', 500, 4, '{"patient_id":"integer","age":"integer","bmi":"float","notes":"string"}', 'Clinical summary', 20, '2026-04-01T08:00:00')
    """, (ds_id, oid))
    cur.execute("""
        INSERT INTO evaluations (id, dataset_id, status, progress, quality_score, schema_fidelity_score, completeness_score, domain_relevance_score, overall_score, credits_awarded, created_at, updated_at)
        VALUES (?, ?, 'completed', 100, 91.0, 95.0, 90.0, 90.0, 91.0, 96, '2026-04-01T08:01:00', '2026-04-01T08:01:00')
    """, (f"eval_{uuid.uuid4().hex[:8]}", ds_id))
    cur.execute("""
        INSERT INTO dataset_versions (id, dataset_id, version, user_id, quality_score, relevance_score, overall_score, delta_score, credits_awarded, changes_summary, created_at)
        VALUES (?, ?, 'v2.0', ?, 96.0, 94.0, 95.0, 4.0, 8, 'Cleaned missing BMI values', '2026-04-02T10:00:00')
    """, (f"ver_{uuid.uuid4().hex[:8]}", ds_id, oid))
    conn.commit()

    # Dataset inspection endpoint
    ds_res = client.get(f"/admin/datasets/{ds_id}", headers=admin["headers"])
    assert ds_res.status_code == 200
    ds_body = ds_res.json()
    assert ds_body["id"] == ds_id
    assert ds_body["owner_id"] == oid
    assert ds_body["version_count"] == 2
    assert ds_body["improvement_rewards"] == 8
    assert len(ds_body["schema_columns"]) == 4
    assert "rows" not in ds_body  # Never expose raw dataset rows

    # Unknown dataset returns 404
    missing_ds = client.get("/admin/datasets/ds_nonexistent_999", headers=admin["headers"])
    assert missing_ds.status_code == 404

    # Global activity sort order ascending vs descending & sensitive token redaction
    asc_res = client.get("/admin/activity?sort_order=asc&limit=20", headers=admin["headers"])
    assert asc_res.status_code == 200
    asc_ts = [item["timestamp"] for item in asc_res.json()["items"]]
    assert asc_ts == sorted(asc_ts)
    assert owner["token"] not in asc_res.text
    assert admin["token"] not in asc_res.text
    assert "password_hash" not in asc_res.text.lower()

    desc_res = client.get("/admin/activity?sort_order=desc&limit=20", headers=admin["headers"])
    assert desc_res.status_code == 200
    desc_ts = [item["timestamp"] for item in desc_res.json()["items"]]
    assert desc_ts == sorted(desc_ts, reverse=True)
