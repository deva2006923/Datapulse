def test_cors_explicit_origin(client):
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET"
    }
    res = client.options("/health", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("access-control-allow-credentials") == "true"

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
    assert "access-control-allow-origin" not in res.headers

def test_cors_headers_and_exposed_content_disposition(client):
    headers = {
        "Origin": "https://sample.lovable.app"
    }
    res = client.get("/health", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://sample.lovable.app"
    assert "content-disposition" in res.headers.get("access-control-expose-headers", "").lower()
