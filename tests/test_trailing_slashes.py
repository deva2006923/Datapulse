def test_trailing_slashes_no_redirect(client):
    # Verify both /health and /health/ return 200 (not 307 or 301)
    res1 = client.get("/health", follow_redirects=False)
    assert res1.status_code == 200
    
    res2 = client.get("/health/", follow_redirects=False)
    assert res2.status_code == 200

def test_trailing_slashes_authenticated_route(client):
    # Register a user to get token
    reg = client.post("/auth/register", json={
        "email": "slash_test@datapulse.test",
        "password": "Password123!",
        "full_name": "Slash Tester"
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test /me and /me/
    res1 = client.get("/me", headers=headers, follow_redirects=False)
    assert res1.status_code == 200
    assert res1.json()["email"] == "slash_test@datapulse.test"
    
    res2 = client.get("/me/", headers=headers, follow_redirects=False)
    assert res2.status_code == 200
    assert res2.json()["email"] == "slash_test@datapulse.test"

    # Test /me/stats and /me/stats/
    res3 = client.get("/me/stats", headers=headers, follow_redirects=False)
    assert res3.status_code == 200
    
    res4 = client.get("/me/stats/", headers=headers, follow_redirects=False)
    assert res4.status_code == 200
