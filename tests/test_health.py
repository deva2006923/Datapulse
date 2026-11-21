import uuid
from app.config import settings


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "cors_regex" in data
    assert isinstance(data["cors_regex"], bool)
    assert data["cors_regex"] is True
    assert "embeddings" in data
    assert isinstance(data["embeddings"], bool)
    assert data["version"] == "1.0.0"
    assert data["database_ok"] is True
    assert data["storage_ok"] is True
    assert "environment" in data


def test_health_trailing_slash(client):
    res = client.get("/health/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database_ok"] is True
    assert data["storage_ok"] is True


def test_upload_exceeding_max_size_returns_413(client, monkeypatch):
    # Register fresh user
    email = f"sizecheck_{uuid.uuid4().hex[:8]}@datapulse.test"
    reg = client.post("/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Size Limit Tester",
    })
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    # Temporarily lower upload cap to 1 MB and send slightly over 1 MB CSV
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    oversized_csv = ("a,b\n" + ("1,2\n" * 300000)).encode("utf-8")
    assert len(oversized_csv) > 1024 * 1024

    res = client.post(
        "/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("too_big.csv", oversized_csv, "text/csv")},
        data={"domain": "technology", "name": "Too Big"},
    )
    assert res.status_code == 413
    assert "exceeds maximum allowed size" in res.json()["detail"]
