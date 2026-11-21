import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.database import get_db_connection
from app.main import app


STRONG_TOKEN = secrets.token_urlsafe(48)
ADMIN_EMAIL = "datapulseapplication@gmail.com"


def _reset_bootstrap_and_admin():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM admin_bootstrap_state")
    cur.execute("DELETE FROM tokens WHERE user_id IN (SELECT id FROM users WHERE LOWER(email) = ?)", (ADMIN_EMAIL,))
    cur.execute("DELETE FROM users WHERE LOWER(email) = ?", (ADMIN_EMAIL,))
    conn.commit()


def _register_user(client, email: str, password: str = "ExistingPass123!", full_name: str = "Admin"):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert res.status_code == 201
    return res.json()


@pytest.fixture(autouse=True)
def restore_settings_after_test():
    orig_token = settings.ADMIN_BOOTSTRAP_TOKEN
    orig_email = settings.ADMIN_EMAIL
    settings.ADMIN_EMAIL = ADMIN_EMAIL
    _reset_bootstrap_and_admin()
    yield
    settings.ADMIN_BOOTSTRAP_TOKEN = orig_token
    settings.ADMIN_EMAIL = orig_email
    _reset_bootstrap_and_admin()


def test_bootstrap_disabled_when_token_absent_or_weak(client):
    _register_user(client, ADMIN_EMAIL)

    # Absent token -> 404 disabled
    settings.ADMIN_BOOTSTRAP_TOKEN = None
    res = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": STRONG_TOKEN},
    )
    assert res.status_code == 404

    # Weak token (< 32 chars) -> 404 disabled
    settings.ADMIN_BOOTSTRAP_TOKEN = "short-weak-token"
    res_weak = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": "short-weak-token"},
    )
    assert res_weak.status_code == 404


def test_bootstrap_requires_https_and_rejects_query_params(client):
    _register_user(client, ADMIN_EMAIL)
    settings.ADMIN_BOOTSTRAP_TOKEN = STRONG_TOKEN

    # Plain HTTP (no X-Forwarded-Proto: https and http:// base URL) -> 403
    res_http = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL},
        headers={"X-Admin-Bootstrap-Token": STRONG_TOKEN},
    )
    assert res_http.status_code == 403

    # Token passed in URL query string -> 403 rejected
    res_qp = client.post(
        f"/admin/bootstrap/activate?token={STRONG_TOKEN}",
        json={"email": ADMIN_EMAIL},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": STRONG_TOKEN},
    )
    assert res_qp.status_code == 403


def test_bootstrap_rejects_wrong_token_and_wrong_email(client):
    reg_admin = _register_user(client, ADMIN_EMAIL)
    other_email = f"other_{uuid.uuid4().hex[:6]}@datapulse.test"
    reg_other = _register_user(client, other_email, full_name="Other User")
    settings.ADMIN_BOOTSTRAP_TOKEN = STRONG_TOKEN

    # Wrong token -> 403
    res_wrong_tok = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": secrets.token_urlsafe(48)},
    )
    assert res_wrong_tok.status_code == 403
    assert STRONG_TOKEN not in res_wrong_tok.text

    # Wrong email with valid token -> 403 and does NOT promote other user
    res_wrong_email = client.post(
        "/admin/bootstrap/activate",
        json={"email": other_email},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": STRONG_TOKEN},
    )
    assert res_wrong_email.status_code == 403

    # Neither account was promoted
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (reg_other["user"]["id"],))
    assert cur.fetchone()["is_admin"] == 0
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (reg_admin["user"]["id"],))
    assert cur.fetchone()["is_admin"] == 0


def test_bootstrap_does_not_create_missing_user(client):
    settings.ADMIN_BOOTSTRAP_TOKEN = STRONG_TOKEN

    res = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": STRONG_TOKEN},
    )
    assert res.status_code == 404

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE LOWER(email) = ?", (ADMIN_EMAIL,))
    assert cur.fetchone()["cnt"] == 0


def test_bootstrap_promotes_existing_account_once_preserves_fields_and_blocks_repeat(client):
    reg_admin = _register_user(client, ADMIN_EMAIL, password="MyExistingPassword99!", full_name="Admin")
    other_email = f"regular_{uuid.uuid4().hex[:6]}@datapulse.test"
    reg_other = _register_user(client, other_email, password="RegularUserPass1!", full_name="Regular User")
    settings.ADMIN_BOOTSTRAP_TOKEN = STRONG_TOKEN

    # Before promotion: account cannot access admin APIs
    pre_me = client.get("/auth/me", headers={"Authorization": f"Bearer {reg_admin['access_token']}"})
    assert pre_me.status_code == 200
    assert pre_me.json()["is_admin"] is False
    pre_admin = client.get("/admin/overview", headers={"Authorization": f"Bearer {reg_admin['access_token']}"})
    assert pre_admin.status_code == 403

    # Snapshot password hash, credits, and user count before activation
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash, credits, full_name FROM users WHERE id = ?", (reg_admin["user"]["id"],))
    before = dict(cur.fetchone())
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    user_count_before = cur.fetchone()["cnt"]

    # Activate via HTTPS POST + header token
    act_res = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL.upper()},  # case-insensitive match
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": STRONG_TOKEN},
    )
    assert act_res.status_code == 200
    body = act_res.json()
    assert body["status"] == "activated"
    assert body["email"] == ADMIN_EMAIL
    assert body["is_admin"] is True

    # Never returns passwords, tokens, or secrets
    raw = act_res.text
    assert STRONG_TOKEN not in raw
    assert "MyExistingPassword99!" not in raw
    assert before["password_hash"] not in raw
    assert reg_admin["access_token"] not in raw

    # Only users.is_admin changed; password, credits, name, and user count unchanged
    cur.execute("SELECT password_hash, credits, full_name, is_admin FROM users WHERE id = ?", (reg_admin["user"]["id"],))
    after = dict(cur.fetchone())
    assert after["is_admin"] == 1
    assert after["password_hash"] == before["password_hash"]
    assert after["credits"] == before["credits"]
    assert after["full_name"] == before["full_name"]

    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    assert cur.fetchone()["cnt"] == user_count_before

    # Audit log recorded without storing bootstrap token
    cur.execute(
        "SELECT action, admin_email, details FROM admin_audit_logs WHERE action = 'ADMIN_BOOTSTRAP_ACTIVATE' ORDER BY created_at DESC LIMIT 1"
    )
    audit = cur.fetchone()
    assert audit is not None
    assert audit["admin_email"] == ADMIN_EMAIL
    assert STRONG_TOKEN not in (audit["details"] or "")

    # Existing password still works for login and grants admin dashboard access
    login_res = client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": "MyExistingPassword99!"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["user"]["is_admin"] is True
    admin_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    assert client.get("/admin/overview", headers=admin_headers).status_code == 200

    # Normal user still receives 403 on admin endpoints
    other_headers = {"Authorization": f"Bearer {reg_other['access_token']}"}
    assert client.get("/admin/overview", headers=other_headers).status_code == 403
    assert client.get("/admin/users", headers=other_headers).status_code == 403

    # Repeated activation is rejected (endpoint now disabled -> 404)
    repeat_res = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": STRONG_TOKEN},
    )
    assert repeat_res.status_code == 404


def test_bootstrap_concurrent_requests_only_succeed_once():
    setup_client = TestClient(app)
    _register_user(setup_client, ADMIN_EMAIL)
    other_email = f"concurrent_{uuid.uuid4().hex[:6]}@datapulse.test"
    reg_other = _register_user(setup_client, other_email, full_name="Bystander")
    settings.ADMIN_BOOTSTRAP_TOKEN = STRONG_TOKEN

    def attempt(_idx: int):
        with TestClient(app, base_url="https://testserver") as c:
            return c.post(
                "/admin/bootstrap/activate",
                json={"email": ADMIN_EMAIL},
                headers={"X-Admin-Bootstrap-Token": STRONG_TOKEN},
            ).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(attempt, range(6)))

    assert codes.count(200) == 1
    assert all(code in (200, 404, 409) for code in codes)

    # Exactly one admin exists and bystander was never promoted
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (reg_other["user"]["id"],))
    assert cur.fetchone()["is_admin"] == 0
    cur.execute("SELECT COUNT(*) AS cnt FROM admin_bootstrap_state WHERE consumed = 1")
    assert cur.fetchone()["cnt"] == 1
