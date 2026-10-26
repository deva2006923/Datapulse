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
    ("/admin/users", "GET"),
    ("/admin/users/usr_dummy", "GET"),
    ("/admin/datasets", "GET"),
    ("/admin/queries", "GET"),
    ("/admin/transactions", "GET"),
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
