import datetime
import hashlib
import uuid

from app.auth import hash_password, verify_password, needs_password_rehash
from app.config import settings
from app.database import get_db_connection
from app.main import reset_rate_limiter


def test_pbkdf2_salted_hashing_and_legacy_transparent_upgrade(client):
    """Passwords use unique per-user salts with PBKDF2-HMAC-SHA256; legacy SHA-256 hashes upgrade on login."""
    h1 = hash_password("SamePassword123!")
    h2 = hash_password("SamePassword123!")
    assert h1 != h2  # unique random salt per hash
    assert h1.startswith("pbkdf2_sha256$")
    assert verify_password("SamePassword123!", h1) is True
    assert verify_password("WrongPassword123!", h1) is False
    assert needs_password_rehash(h1) is False

    # Simulate an existing legacy SHA-256 user in DB
    email = f"legacy_{uuid.uuid4().hex[:8]}@datapulse.io"
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": "LegacyPassword123!", "full_name": "Legacy User"},
    )
    assert reg.status_code == 201
    uid = reg.json()["user"]["id"]

    legacy_digest = hashlib.sha256(b"datapulse_salt_v1LegacyPassword123!").hexdigest()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (legacy_digest, uid))
    conn.commit()
    assert needs_password_rehash(legacy_digest) is True

    # Login with legacy password succeeds and transparently upgrades stored hash to PBKDF2
    login = client.post(
        "/auth/login",
        json={"email": email, "password": "LegacyPassword123!"},
    )
    assert login.status_code == 200
    cur.execute("SELECT password_hash FROM users WHERE id = ?", (uid,))
    upgraded = cur.fetchone()["password_hash"]
    assert upgraded.startswith("pbkdf2_sha256$")
    assert upgraded != legacy_digest
    assert verify_password("LegacyPassword123!", upgraded) is True


def test_session_token_expiration_and_server_side_logout(client):
    """Expired tokens are rejected with 401 and deleted; POST /auth/logout revokes active token."""
    email = f"session_{uuid.uuid4().hex[:8]}@datapulse.io"
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": "SessionPass123!", "full_name": "Session User"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Valid token works
    assert client.get("/auth/me", headers=headers).status_code == 200

    # Force token expiration in DB
    past = (datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE tokens SET expires_at = ? WHERE token = ?", (past, token))
    conn.commit()

    expired_res = client.get("/auth/me", headers=headers)
    assert expired_res.status_code == 401

    # Expired token was purged from tokens table
    cur.execute("SELECT COUNT(*) AS cnt FROM tokens WHERE token = ?", (token,))
    assert cur.fetchone()["cnt"] == 0

    # New login token can be revoked server-side via POST /auth/logout
    login = client.post("/auth/login", json={"email": email, "password": "SessionPass123!"})
    assert login.status_code == 200
    token2 = login.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}
    assert client.get("/auth/me", headers=headers2).status_code == 200

    logout_res = client.post("/auth/logout", headers=headers2)
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"

    # Reusing revoked token must fail with 401
    assert client.get("/auth/me", headers=headers2).status_code == 401


def test_rate_limiting_and_security_headers(client):
    """Auth rate limiting returns 429 with Retry-After; security headers are attached."""
    orig_enabled = settings.RATE_LIMIT_ENABLED
    orig_auth_limit = settings.RATE_LIMIT_AUTH_PER_MIN
    reset_rate_limiter()
    try:
        settings.RATE_LIMIT_ENABLED = True
        settings.RATE_LIMIT_AUTH_PER_MIN = 3

        ip_headers = {"X-Forwarded-For": f"198.51.100.{uuid.uuid4().int % 200 + 1}"}
        for _ in range(3):
            res = client.post(
                "/auth/login",
                json={"email": "nobody@datapulse.io", "password": "wrongpassword"},
                headers=ip_headers,
            )
            assert res.status_code == 401
            assert res.headers.get("x-content-type-options") == "nosniff"
            assert res.headers.get("x-frame-options") == "DENY"
            assert res.headers.get("cache-control") == "no-store"

        # 4th attempt within window is rate-limited with 429
        blocked = client.post(
            "/auth/login",
            json={"email": "nobody@datapulse.io", "password": "wrongpassword"},
            headers=ip_headers,
        )
        assert blocked.status_code == 429
        assert "retry-after" in blocked.headers

        # Health endpoint is never blocked by rate limiting
        health = client.get("/health", headers=ip_headers)
        assert health.status_code == 200
    finally:
        settings.RATE_LIMIT_ENABLED = orig_enabled
        settings.RATE_LIMIT_AUTH_PER_MIN = orig_auth_limit
        reset_rate_limiter()
