import uuid
import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.database import get_db_connection
from app.main import app
from app.services.admin_bootstrap import ensure_default_admin


ADMIN_EMAIL = "datapulseapplication@gmail.com"


def _clear_admin_user():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM tokens WHERE user_id IN (SELECT id FROM users WHERE LOWER(email) = ?)",
        (ADMIN_EMAIL,),
    )
    cur.execute("DELETE FROM users WHERE LOWER(email) = ?", (ADMIN_EMAIL,))
    conn.commit()


@pytest.fixture(autouse=True)
def restore_admin_settings():
    orig_email = settings.ADMIN_EMAIL
    orig_password = settings.ADMIN_PASSWORD
    settings.ADMIN_EMAIL = ADMIN_EMAIL
    settings.ADMIN_PASSWORD = None
    _clear_admin_user()
    yield
    settings.ADMIN_EMAIL = orig_email
    settings.ADMIN_PASSWORD = orig_password
    _clear_admin_user()


def test_temporary_bootstrap_endpoint_is_removed(client):
    res = client.post(
        "/admin/bootstrap/activate",
        json={"email": ADMIN_EMAIL},
        headers={"X-Forwarded-Proto": "https", "X-Admin-Bootstrap-Token": "x" * 48},
    )
    assert res.status_code == 404


def test_first_time_startup_provisioning_creates_hashed_admin():
    settings.ADMIN_EMAIL = ADMIN_EMAIL
    settings.ADMIN_PASSWORD = "StrongStartupAdminPass123!"

    # Entering TestClient triggers FastAPI lifespan startup -> ensure_default_admin()
    with TestClient(app) as client:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash, full_name, credits, is_admin FROM users WHERE LOWER(email) = ?",
            (ADMIN_EMAIL,),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["is_admin"] == 1
        assert row["password_hash"] != "StrongStartupAdminPass123!"
        assert row["password_hash"].startswith("pbkdf2_sha256$")

        # Admin can log in and access admin dashboard endpoints
        login_res = client.post(
            "/auth/login",
            json={"email": ADMIN_EMAIL, "password": "StrongStartupAdminPass123!"},
        )
        assert login_res.status_code == 200
        body = login_res.json()
        assert body["user"]["is_admin"] is True
        assert "StrongStartupAdminPass123!" not in login_res.text

        headers = {"Authorization": f"Bearer {body['access_token']}"}
        ov_res = client.get("/admin/overview", headers=headers)
        assert ov_res.status_code == 200
        assert "StrongStartupAdminPass123!" not in ov_res.text

        # Public registration with the admin email is blocked (400) because built-in admin exists
        dup_reg = client.post(
            "/auth/register",
            json={
                "email": ADMIN_EMAIL.upper(),
                "password": "AttackerPassword123!",
                "full_name": "Impersonator",
            },
        )
        assert dup_reg.status_code == 400


def test_repeated_startup_is_idempotent_and_never_creates_duplicates():
    settings.ADMIN_EMAIL = ADMIN_EMAIL
    settings.ADMIN_PASSWORD = "RepeatStartupPassword123!"

    first = ensure_default_admin()
    assert first["status"] == "created"
    assert first["is_admin"] is True

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, password_hash, credits, full_name, created_at FROM users WHERE LOWER(email) = ?",
        (ADMIN_EMAIL,),
    )
    snap_1 = dict(cur.fetchone())

    # Simulate repeated startups (both direct call and full lifespan re-entry)
    second = ensure_default_admin()
    assert second["status"] == "unchanged"
    assert second["id"] == first["id"]

    with TestClient(app):
        pass

    cur.execute(
        "SELECT id, password_hash, credits, full_name, created_at FROM users WHERE LOWER(email) = ?",
        (ADMIN_EMAIL,),
    )
    rows = cur.fetchall()
    assert len(rows) == 1
    assert dict(rows[0]) == snap_1


def test_existing_account_promoted_without_resetting_password_or_credits(client):
    # Pre-existing account registered with is_admin = 0, custom password, name, and credits
    reg_res = client.post(
        "/auth/register",
        json={
            "email": ADMIN_EMAIL,
            "password": "OriginalExistingPassword99!",
            "full_name": "Admin",
        },
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["user"]["id"]
    assert reg_res.json()["user"]["is_admin"] is False

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = 345 WHERE id = ?", (user_id,))
    conn.commit()
    cur.execute("SELECT password_hash, credits, full_name FROM users WHERE id = ?", (user_id,))
    before = dict(cur.fetchone())

    # Startup runs even with a DIFFERENT ADMIN_PASSWORD configured in env
    settings.ADMIN_EMAIL = ADMIN_EMAIL
    settings.ADMIN_PASSWORD = "DifferentEnvPassword456!"

    result = ensure_default_admin()
    assert result["status"] == "promoted"
    assert result["id"] == user_id
    assert result["is_admin"] is True

    # Password hash, credits, full_name, and user count are strictly preserved
    cur.execute(
        "SELECT id, password_hash, credits, full_name, is_admin FROM users WHERE LOWER(email) = ?",
        (ADMIN_EMAIL,),
    )
    rows = cur.fetchall()
    assert len(rows) == 1
    after = dict(rows[0])
    assert after["is_admin"] == 1
    assert after["password_hash"] == before["password_hash"]
    assert after["credits"] == 345
    assert after["full_name"] == "Admin"

    # Original password still logs in with is_admin = True
    ok_login = client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": "OriginalExistingPassword99!"},
    )
    assert ok_login.status_code == 200
    assert ok_login.json()["user"]["is_admin"] is True

    # Different env password does NOT work (password was NOT reset)
    bad_login = client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": "DifferentEnvPassword456!"},
    )
    assert bad_login.status_code == 401


def test_startup_skips_creation_when_password_missing_or_weak():
    settings.ADMIN_EMAIL = ADMIN_EMAIL

    # Missing ADMIN_PASSWORD
    settings.ADMIN_PASSWORD = None
    res_missing = ensure_default_admin()
    assert res_missing["status"] == "skipped_missing_password"

    # Weak ADMIN_PASSWORD (< 8 chars)
    settings.ADMIN_PASSWORD = "short"
    res_weak = ensure_default_admin()
    assert res_weak["status"] == "skipped_weak_password"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE LOWER(email) = ?", (ADMIN_EMAIL,))
    assert cur.fetchone()["cnt"] == 0


def test_ordinary_users_cannot_gain_admin_access(client):
    settings.ADMIN_EMAIL = ADMIN_EMAIL
    settings.ADMIN_PASSWORD = "ProvisionedOwnerPass123!"
    ensure_default_admin()

    # Register an ordinary user (even naming themselves "Admin")
    other_email = f"regular_{uuid.uuid4().hex[:8]}@datapulse.io"
    reg = client.post(
        "/auth/register",
        json={
            "email": other_email,
            "password": "RegularUserPass123!",
            "full_name": "Admin",
        },
    )
    assert reg.status_code == 201
    assert reg.json()["user"]["is_admin"] is False
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    # Verify /auth/me reports is_admin = False and all admin endpoints reject with 403
    assert client.get("/auth/me", headers=headers).json()["is_admin"] is False
    for path in (
        "/admin/overview",
        "/admin/users",
        "/admin/datasets",
        "/admin/queries",
        "/admin/transactions",
    ):
        r = client.get(path, headers=headers)
        assert r.status_code == 403
