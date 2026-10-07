def test_full_auth_dataset_credits_lifecycle(client):
    # 1. Register
    reg = client.post("/auth/register", json={
        "email": "lifecycle_test@datapulse.test",
        "password": "Password123!",
        "full_name": "Lifecycle Tester"
    })
    assert reg.status_code == 201
    user_data = reg.json()
    token = user_data["access_token"]
    assert user_data["user"]["credits"] == 100
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Duplicate registration rejected
    dup = client.post("/auth/register", json={
        "email": "lifecycle_test@datapulse.test",
        "password": "Password123!",
        "full_name": "Duplicate Tester"
    })
    assert dup.status_code == 400

    # 3. Login
    login = client.post("/auth/login", json={
        "email": "lifecycle_test@datapulse.test",
        "password": "Password123!"
    })
    assert login.status_code == 200
    assert "access_token" in login.json()

    # 4. Upload Dataset
    csv_data = "item_id,label,confidence\n1,alpha,0.95\n2,beta,0.88\n3,gamma,0.92\n"
    files = {"file": ("items.csv", csv_data, "text/csv")}
    upload = client.post("/datasets/upload", headers=headers, files=files, data={"domain": "technology", "name": "Test Items"})
    assert upload.status_code == 201
    ds_id = upload.json()["id"]

    # 5. Check evaluation
    eval_res = client.get(f"/datasets/{ds_id}/evaluation", headers=headers)
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["status"] == "completed"
    assert eval_data["overall_score"] > 0
    assert eval_data["credits_awarded"] > 0

    # 6. Search
    search_res = client.post("/datasets/search", json={"query": "alpha beta items", "limit": 5})
    assert search_res.status_code == 200
    assert len(search_res.json()["results"]) >= 1

    # 7. Query
    query_res = client.post("/query", json={"query": "What items are in the catalog?"}, headers=headers)
    assert query_res.status_code == 200
    assert query_res.json()["records_analyzed"] >= 3

    # 8. Redeem Validation Error (negative amount -> 422)
    invalid_redeem = client.post("/credits/redeem", json={"amount": -10, "payout_method": "upi", "destination": "abc@upi"}, headers=headers)
    assert invalid_redeem.status_code == 422

    # 9. Redeem Validation Error (excessive amount -> 400)
    excess_redeem = client.post("/credits/redeem", json={"amount": 999999, "payout_method": "upi", "destination": "abc@upi"}, headers=headers)
    assert excess_redeem.status_code in (400, 422)

    # 10. Valid Redeem
    valid_redeem = client.post("/credits/redeem", json={"amount": 50, "payout_method": "paypal", "destination": "tester@paypal.com"}, headers=headers)
    assert valid_redeem.status_code == 200
    assert valid_redeem.json()["success"] is True

    # 11. User Stats
    stats_res = client.get("/me/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["datasets_uploaded"] == 1
    assert stats["total_evaluations_completed"] == 1
    assert len(stats["recent_transactions"]) >= 2
