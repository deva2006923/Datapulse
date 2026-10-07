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

def test_health_trailing_slash(client):
    res = client.get("/health/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
