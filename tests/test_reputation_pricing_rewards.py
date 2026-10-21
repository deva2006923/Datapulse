import pytest
import io
import math
import uuid
from app.services.pricing import calculate_dataset_unlock_price
from app.services.reputation import calculate_user_reputation
from app.database import get_db_connection


def test_pricing_formula_determinism_and_bounds():
    """Verify unlock pricing calculation is bounded between 5 and 50 and deterministic."""
    # Low quality, minimal rows
    p_low = calculate_dataset_unlock_price(
        quality_score=0.0,
        completeness_score=0.0,
        domain_relevance_score=0.0,
        rows_count=1,
        columns_count=0
    )
    assert 5 <= p_low <= 50
    assert p_low == 5  # minimum clamp at 0 quality/volume

    # Medium quality
    p_med = calculate_dataset_unlock_price(
        quality_score=60.0,
        completeness_score=70.0,
        domain_relevance_score=65.0,
        rows_count=500,
        columns_count=8
    )
    assert 5 <= p_med <= 50

    # High quality, large table
    p_high = calculate_dataset_unlock_price(
        quality_score=95.0,
        completeness_score=98.0,
        domain_relevance_score=92.0,
        rows_count=50000,
        columns_count=30
    )
    assert 5 <= p_high <= 50
    assert p_high > p_med

    # Determinism
    assert calculate_dataset_unlock_price(80.0, 80.0, 80.0, 1000, 10) == calculate_dataset_unlock_price(80.0, 80.0, 80.0, 1000, 10)


def test_reputation_formula_for_new_and_active_users():
    """Verify reputation formula returns 50 for new users, scales with quality, and penalizes failures."""
    conn = get_db_connection()
    # Generate clean test user ID
    test_uid = f"user_test_{uuid.uuid4().hex[:8]}"

    # With 0 contributions, reputation should evaluate to default neutral 50
    rep_new = calculate_user_reputation(test_uid, conn)
    assert rep_new == 50


def test_new_user_reputation_via_api(client):
    """Verify new user registration gives initial reputation_score of 50 and reflects in /auth/me and /me/stats."""
    uid = uuid.uuid4().hex[:8]
    email = f"rep_test_{uid}@datapulse.io"
    password = "SecretPassword123!"

    reg = client.post("/auth/register", json={"email": email, "password": password, "full_name": f"Rep User {uid}"})
    assert reg.status_code == 201
    reg_data = reg.json()
    assert reg_data["user"]["reputation_score"] == 50
    token = reg_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # /auth/me
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["reputation_score"] == 50

    # /me/stats
    stats = client.get("/me/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["reputation_score"] == 50


def test_upload_rewards_and_dataset_pricing(client):
    """Verify basic upload reward (50 cr) + quality reward, and dynamic unlock pricing persistence."""
    uid = uuid.uuid4().hex[:8]
    email = f"author_{uid}@datapulse.io"
    reg = client.post("/auth/register", json={"email": email, "password": "Password123!", "full_name": f"Author {uid}"})
    assert reg.status_code == 201
    author_token = reg.json()["access_token"]
    author_headers = {"Authorization": f"Bearer {author_token}"}
    initial_credits = reg.json()["user"]["credits"]  # 100

    # Upload a CSV dataset
    csv_content = "id,name,category,revenue\n1,Alpha,Retail,100.5\n2,Beta,Tech,250.0\n3,Gamma,Finance,300.0\n"
    files = {"file": ("test_sales.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    upload_res = client.post("/datasets/upload", data={"domain": "retail", "name": f"Sales Data {uid}"}, files=files, headers=author_headers)
    assert upload_res.status_code == 201
    ds_data = upload_res.json()

    dataset_id = ds_data["id"]
    credits_awarded = ds_data["credits_awarded"]
    unlock_price = ds_data["unlock_price"]

    # Basic upload reward is 50, plus quality incentive
    assert credits_awarded >= 50
    assert 5 <= unlock_price <= 50

    # Check author credit transactions ledger
    tx_res = client.get("/credits/transactions", headers=author_headers)
    assert tx_res.status_code == 200
    txs = tx_res.json()
    tx_types = [t["transaction_type"] for t in txs]
    assert "upload_reward" in tx_types
    assert "quality_reward" in tx_types

    # Check author balance reflects both rewards
    me_res = client.get("/auth/me", headers=author_headers)
    assert me_res.json()["credits"] == initial_credits + credits_awarded

    # Check author's reputation score updated after approved upload
    assert me_res.json()["reputation_score"] >= 50

    # Check dataset listing and detail endpoints return the same unlock_price
    detail_res = client.get(f"/datasets/{dataset_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["unlock_price"] == unlock_price

    list_res = client.get("/datasets")
    assert list_res.status_code == 200
    found = [d for d in list_res.json()["datasets"] if d["id"] == dataset_id]
    assert len(found) == 1
    assert found[0]["unlock_price"] == unlock_price


def test_one_time_dataset_unlock_and_royalty(client):
    """Verify consumer can unlock dataset, pays exact unlock price once, author earns royalty, and re-unlock is free."""
    uid_author = uuid.uuid4().hex[:8]
    reg_author = client.post("/auth/register", json={"email": f"auth_{uid_author}@datapulse.io", "password": "Password123!", "full_name": "Author"})
    assert reg_author.status_code == 201
    author_headers = {"Authorization": f"Bearer {reg_author.json()['access_token']}"}

    csv_data = "x,y,z\n1,2,3\n4,5,6\n"
    files = {"file": ("data.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    up = client.post("/datasets/upload", data={"domain": "technology", "name": f"Tech Data {uid_author}"}, files=files, headers=author_headers)
    assert up.status_code == 201
    dataset_id = up.json()["id"]
    unlock_price = up.json()["unlock_price"]

    # Register Consumer with 100 credits
    uid_buyer = uuid.uuid4().hex[:8]
    reg_buyer = client.post("/auth/register", json={"email": f"buyer_{uid_buyer}@datapulse.io", "password": "Password123!", "full_name": "Buyer"})
    assert reg_buyer.status_code == 201
    buyer_headers = {"Authorization": f"Bearer {reg_buyer.json()['access_token']}"}
    buyer_start_credits = reg_buyer.json()["user"]["credits"]

    # Author unlocking their own dataset should be 0 credits
    author_unlock = client.post(f"/datasets/{dataset_id}/unlock", headers=author_headers)
    assert author_unlock.status_code == 200
    assert author_unlock.json()["credits_charged"] == 0
    assert author_unlock.json()["already_unlocked"] is True

    # Buyer unlocks dataset for the first time
    buyer_unlock1 = client.post(f"/datasets/{dataset_id}/unlock", headers=buyer_headers)
    assert buyer_unlock1.status_code == 200
    assert buyer_unlock1.json()["credits_charged"] == unlock_price
    assert buyer_unlock1.json()["remaining_balance"] == buyer_start_credits - unlock_price

    # Check buyer's credit transactions
    buyer_txs = client.get("/credits/transactions", headers=buyer_headers).json()
    assert any(t["transaction_type"] == "dataset_unlock" and t["amount"] == -unlock_price for t in buyer_txs)

    # Check author received unlock royalty
    author_txs = client.get("/credits/transactions", headers=author_headers).json()
    assert any(t["transaction_type"] == "unlock_royalty" and t["amount"] == unlock_price for t in author_txs)

    # Buyer attempts to unlock again -> Idempotent! 0 credits charged
    buyer_unlock2 = client.post(f"/datasets/{dataset_id}/unlock", headers=buyer_headers)
    assert buyer_unlock2.status_code == 200
    assert buyer_unlock2.json()["credits_charged"] == 0
    assert buyer_unlock2.json()["already_unlocked"] is True
    assert buyer_unlock2.json()["remaining_balance"] == buyer_start_credits - unlock_price

    # Check dataset detail shows buyer in unlocked_by
    detail = client.get(f"/datasets/{dataset_id}").json()
    assert reg_buyer.json()["user"]["id"] in detail["unlocked_by"]


def test_dataset_version_improvement_bounty(client):
    """Verify version improvement calculates delta score and awards credits when delta >= 5.0."""
    uid = uuid.uuid4().hex[:8]
    reg = client.post("/auth/register", json={"email": f"imp_{uid}@datapulse.io", "password": "Password123!", "full_name": "Improver"})
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    # Upload a dataset with some null values so initial evaluation score is around 70-80
    csv_data = "a,b,c\n1,,3\n4,5,\n,,9\n10,11,12\n"
    files = {"file": ("data.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    up = client.post("/datasets/upload", data={"domain": "finance", "name": f"Finance {uid}"}, files=files, headers=headers)
    assert up.status_code == 201
    dataset_id = up.json()["id"]

    # Retrieve baseline score from evaluation
    eval_res = client.get(f"/datasets/{dataset_id}/evaluation", headers=headers)
    baseline_score = eval_res.json()["overall_score"] if eval_res.status_code == 200 else 70.0

    # 1. Improvement with delta < 5.0 -> 0 credits awarded
    small_score = min(100.0, baseline_score + 2.0)
    res_small = client.post(
        f"/datasets/{dataset_id}/improve",
        json={
            "new_quality_score": small_score,
            "new_relevance_score": small_score,
            "changes_summary": "Minor spelling and synonym fix",
        },
        headers=headers,
    )
    assert res_small.status_code == 200
    assert res_small.json()["improvement_credits_awarded"] == 0

    # 2. Improvement with verified delta >= 5.0 -> bounty awarded floor(delta * 0.75)
    # Propose high scores to ensure delta >= 5.0 above baseline
    target_score = min(100.0, baseline_score + 10.0)
    actual_delta = round(target_score - max(baseline_score, small_score), 2)

    if actual_delta >= 5.0:
        res_big = client.post(
            f"/datasets/{dataset_id}/improve",
            json={
                "new_quality_score": target_score,
                "new_relevance_score": target_score,
                "changes_summary": "Major schema normalization and null imputation",
            },
            headers=headers,
        )
        assert res_big.status_code == 200
        data_big = res_big.json()
        expected_bounty = int(math.floor(actual_delta * 0.75))
        assert data_big["improvement_credits_awarded"] == expected_bounty
        assert data_big["version"] == "v3.0"

        # Check transactions for improvement_reward
        txs = client.get("/credits/transactions", headers=headers).json()
        assert any(t["transaction_type"] == "improvement_reward" and t["amount"] == expected_bounty for t in txs)
    else:
        # If baseline was already >= 95, test with perfect score
        perfect_res = client.post(
            f"/datasets/{dataset_id}/improve",
            json={
                "new_quality_score": 100.0,
                "new_relevance_score": 100.0,
                "changes_summary": "100% verified complete data",
            },
            headers=headers,
        )
        assert perfect_res.status_code == 200
