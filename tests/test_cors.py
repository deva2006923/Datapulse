import io
import uuid
import pytest
from app.config import Settings
from app.main import reset_rate_limiter
from app.config import settings as app_settings


def test_cors_explicit_origin(client):
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET"
    }
    res = client.options("/health", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)
def test_cors_preflight_auth_login_local_origins(client, origin):
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type",
    }
    res = client.options("/auth/login", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-origin") != "*"
    assert res.headers.get("access-control-allow-credentials") == "true"
    allow_methods = (res.headers.get("access-control-allow-methods") or "").upper()
    assert "POST" in allow_methods
    allow_headers = (res.headers.get("access-control-allow-headers") or "").lower()
    assert "authorization" in allow_headers
    assert "content-type" in allow_headers


@pytest.mark.parametrize(
    "path,method",
    [
        ("/auth/register", "POST"),
        ("/auth/login", "POST"),
        ("/datasets/upload", "POST"),
        ("/datasets/ds_example/visibility", "PATCH"),
        ("/query", "POST"),
    ],
)
def test_cors_preflight_core_endpoints_from_port_3001(client, path, method):
    origin = "http://localhost:3001"
    res = client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert res.status_code == 200, f"{method} {path} preflight failed: {res.text}"
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_no_wildcard_origins_with_credentials():
    cfg = Settings(
        ENVIRONMENT="production",
        CORS_ORIGINS="*,https://datapulse.ai.studio,http://localhost:3001/",
    )
    assert "*" not in cfg.cors_origins_list
    assert "https://datapulse.ai.studio" in cfg.cors_origins_list
    assert "http://localhost:3001" in cfg.cors_origins_list


def test_cors_end_to_end_register_login_upload_query_from_localhost_3001(client):
    origin = "http://localhost:3001"
    email = f"cors3001_{uuid.uuid4().hex[:8]}@datapulse.test"
    password = "Password123!"

    # 1. Register
    reg = client.post(
        "/auth/register",
        headers={"Origin": origin},
        json={"email": email, "password": password, "full_name": "CORS User"},
    )
    assert reg.status_code == 201, reg.text
    assert reg.headers.get("access-control-allow-origin") == origin
    assert reg.headers.get("access-control-allow-credentials") == "true"

    # 2. Login
    login = client.post(
        "/auth/login",
        headers={"Origin": origin},
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.headers.get("access-control-allow-origin") == origin
    assert login.headers.get("access-control-allow-credentials") == "true"
    token = login.json()["access_token"]
    auth_headers = {"Origin": origin, "Authorization": f"Bearer {token}"}

    # 3. Upload dataset
    csv_body = "city,sales\nAustin,100\nBoston,250\n"
    up = client.post(
        "/datasets/upload",
        headers=auth_headers,
        files={"file": ("cors_sales.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
        data={"name": "CORS Sales Test", "domain": "retail"},
    )
    assert up.status_code == 201, up.text
    assert up.headers.get("access-control-allow-origin") == origin
    assert up.headers.get("access-control-allow-credentials") == "true"
    ds_id = up.json()["id"]

    # 4. Query dataset
    q = client.post(
        "/query",
        headers=auth_headers,
        json={"query": "How many rows are in this dataset?", "dataset_id": ds_id},
    )
    assert q.status_code == 200, q.text
    assert q.headers.get("access-control-allow-origin") == origin
    assert q.headers.get("access-control-allow-credentials") == "true"
    assert q.json()["results"][0]["total_count"] == 2


def test_cors_middleware_is_outermost_so_rate_limit_429_includes_cors_headers(client):
    origin = "http://localhost:3001"
    orig_enabled = app_settings.RATE_LIMIT_ENABLED
    orig_limit = app_settings.RATE_LIMIT_AUTH_PER_MIN
    try:
        reset_rate_limiter()
        app_settings.RATE_LIMIT_ENABLED = True
        app_settings.RATE_LIMIT_AUTH_PER_MIN = 1

        # First call consumes the 1-req/min bucket
        client.post(
            "/auth/login",
            headers={"Origin": origin},
            json={"email": "nobody@datapulse.test", "password": "wrongpassword"},
        )
        # Second call hits rate limiter (429) — CORSMiddleware MUST still attach CORS headers
        rate_limited = client.post(
            "/auth/login",
            headers={"Origin": origin},
            json={"email": "nobody@datapulse.test", "password": "wrongpassword"},
        )
        assert rate_limited.status_code == 429
        assert rate_limited.headers.get("access-control-allow-origin") == origin
        assert rate_limited.headers.get("access-control-allow-credentials") == "true"
    finally:
        app_settings.RATE_LIMIT_ENABLED = orig_enabled
        app_settings.RATE_LIMIT_AUTH_PER_MIN = orig_limit
        reset_rate_limiter()


def test_cors_lovable_app_regex(client):
    headers = {
        "Origin": "https://my-cool-app.lovable.app",
        "Access-Control-Request-Method": "GET"
    }
    res = client.options("/health", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://my-cool-app.lovable.app"
    assert res.headers.get("access-control-allow-credentials") == "true"

def test_cors_lovableproject_regex(client):
    headers = {
        "Origin": "https://preview-789.lovableproject.com",
        "Access-Control-Request-Method": "POST"
    }
    res = client.options("/auth/login", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://preview-789.lovableproject.com"

def test_cors_lovable_dev_regex(client):
    headers = {
        "Origin": "https://staging.lovable.dev",
        "Access-Control-Request-Method": "GET"
    }
    res = client.options("/health", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://staging.lovable.dev"

def test_cors_disallowed_origin(client):
    headers = {
        "Origin": "https://malicious-external-site.com",
        "Access-Control-Request-Method": "GET"
    }
    res = client.options("/health", headers=headers)
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers

def test_cors_headers_and_exposed_content_disposition(client):
    headers = {
        "Origin": "https://sample.lovable.app"
    }
    res = client.get("/health", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://sample.lovable.app"
    assert "content-disposition" in res.headers.get("access-control-expose-headers", "").lower()
