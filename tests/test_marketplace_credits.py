import uuid
import pytest
from app.config import settings
from app.services.nl_query import set_ai_generator, AIProviderError
from app.services.storage import get_dataset_table_name
from app.database import get_db_connection


@pytest.fixture
def owner_user(client):
    """Fixture to create Dataset Owner user."""
    unique_email = f"owner_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post("/auth/register", json={
        "email": unique_email,
        "password": "Password123!",
        "full_name": "Dataset Owner"
    })
    assert res.status_code == 201
    data = res.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "user_id": data["user"]["id"],
        "email": unique_email
    }


@pytest.fixture
def buyer_user(client):
    """Fixture to create Querying Buyer user."""
    unique_email = f"buyer_{uuid.uuid4().hex[:8]}@datapulse.test"
    res = client.post("/auth/register", json={
        "email": unique_email,
        "password": "Password123!",
        "full_name": "Querying Buyer"
    })
    assert res.status_code == 201
    data = res.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "user_id": data["user"]["id"],
        "email": unique_email
    }


@pytest.fixture
def marketplace_dataset(client, owner_user):
    """Fixture to upload a dataset owned by owner_user."""
    csv_data = (
        "plan,subscribers,monthly_revenue\n"
        "Basic,1200,12000\n"
        "Pro,450,13500\n"
        "Enterprise,80,16000\n"
    )
    files = {"file": ("saas_metrics.csv", csv_data, "text/csv")}
    res = client.post(
        "/datasets/upload",
        headers=owner_user["headers"],
        files=files,
        data={"domain": "finance", "name": "SaaS Subscription Metrics"}
    )
    assert res.status_code == 201
    dataset = res.json()
    dataset_id = dataset["id"]
    table_name = get_dataset_table_name(dataset_id)
    return {
        "dataset_id": dataset_id,
        "name": dataset["name"],
        "table_name": table_name,
        "owner_id": owner_user["user_id"]
    }


@pytest.fixture(autouse=True)
def cleanup():
    """Ensure mock AI generator and settings are reset after each test."""
    yield
    set_ai_generator(None)
    settings.QUERY_COST = 1
    settings.DATASET_OWNER_REWARD = 1


def get_user_credits(user_id: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    return row["credits"] if row else 0


def set_user_credits(user_id: str, credits: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET credits = ? WHERE id = ?", (credits, user_id))
    conn.commit()


# 1. Successful query deducts credits from querying user
def test_successful_query_deducts_credits(client, buyer_user, marketplace_dataset):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT plan, monthly_revenue FROM {table}")

    buyer_id = buyer_user["user_id"]
    initial_credits = get_user_credits(buyer_id)
    assert initial_credits == 100

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "What are the subscription plans and revenues?",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 3
    assert data["credits_charged"] == settings.QUERY_COST

    new_credits = get_user_credits(buyer_id)
    assert new_credits == initial_credits - settings.QUERY_COST


# 2. Dataset owner receives reward on successful query
def test_dataset_owner_receives_reward(client, buyer_user, marketplace_dataset, owner_user):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT plan, subscribers FROM {table}")

    owner_id = owner_user["user_id"]
    initial_owner_credits = get_user_credits(owner_id)

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "How many subscribers for each plan?",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 200

    new_owner_credits = get_user_credits(owner_id)
    assert new_owner_credits == initial_owner_credits + settings.DATASET_OWNER_REWARD


# 3. Insufficient credits blocks query
def test_insufficient_credits_blocks_query(client, buyer_user, marketplace_dataset, owner_user):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table}")

    buyer_id = buyer_user["user_id"]
    owner_id = owner_user["user_id"]
    set_user_credits(buyer_id, 0)
    initial_owner_credits = get_user_credits(owner_id)

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "Show all SaaS metrics",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 402
    assert "insufficient credit balance" in res.json()["detail"].lower()

    # Verify no credit changes
    assert get_user_credits(buyer_id) == 0
    assert get_user_credits(owner_id) == initial_owner_credits


# 4. Failed SQL generation does not deduct credits
def test_failed_sql_generation_does_not_deduct_credits(client, buyer_user, marketplace_dataset, owner_user):
    def failing_ai(q, t, cols):
        raise AIProviderError("Gemini quota exceeded / connection error")

    set_ai_generator(failing_ai)

    buyer_id = buyer_user["user_id"]
    owner_id = owner_user["user_id"]
    initial_buyer_credits = get_user_credits(buyer_id)
    initial_owner_credits = get_user_credits(owner_id)

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "Show plans",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 503

    assert get_user_credits(buyer_id) == initial_buyer_credits
    assert get_user_credits(owner_id) == initial_owner_credits


# 5. Invalid SQL does not deduct credits
def test_invalid_sql_does_not_deduct_credits(client, buyer_user, marketplace_dataset, owner_user):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"DROP TABLE {table}")

    buyer_id = buyer_user["user_id"]
    owner_id = owner_user["user_id"]
    initial_buyer_credits = get_user_credits(buyer_id)
    initial_owner_credits = get_user_credits(owner_id)

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "Drop the metrics table",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 422

    assert get_user_credits(buyer_id) == initial_buyer_credits
    assert get_user_credits(owner_id) == initial_owner_credits


# 6. DuckDB execution failure does not deduct credits
def test_duckdb_execution_failure_does_not_deduct_credits(client, buyer_user, marketplace_dataset, owner_user):
    table = marketplace_dataset["table_name"]
    # Cast invalid text to numeric in DuckDB to trigger execution failure
    set_ai_generator(lambda q, t, cols: f"SELECT CAST(plan AS INTEGER) FROM {table}")

    buyer_id = buyer_user["user_id"]
    owner_id = owner_user["user_id"]
    initial_buyer_credits = get_user_credits(buyer_id)
    initial_owner_credits = get_user_credits(owner_id)

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "Convert plan to int",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 422

    assert get_user_credits(buyer_id) == initial_buyer_credits
    assert get_user_credits(owner_id) == initial_owner_credits


# 7. Balance cannot become negative
def test_balance_cannot_become_negative(client, buyer_user, marketplace_dataset):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table}")

    buyer_id = buyer_user["user_id"]
    set_user_credits(buyer_id, 2)
    settings.QUERY_COST = 5

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "What are all metrics?",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 402
    assert "insufficient credit balance" in res.json()["detail"].lower()
    assert get_user_credits(buyer_id) == 2


# 8. Transaction records are created correctly
def test_transaction_records_created_correctly(client, buyer_user, marketplace_dataset, owner_user):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT plan, monthly_revenue FROM {table}")

    buyer_id = buyer_user["user_id"]
    owner_id = owner_user["user_id"]

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "Show revenue per plan",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 200

    # Verify Buyer Transaction
    buyer_txs_res = client.get("/credits/transactions", headers=buyer_user["headers"])
    assert buyer_txs_res.status_code == 200
    buyer_txs = buyer_txs_res.json()
    fee_tx = next((tx for tx in buyer_txs if tx["transaction_type"] == "query_fee"), None)
    assert fee_tx is not None
    assert fee_tx["amount"] == -settings.QUERY_COST
    assert fee_tx["user_id"] == buyer_id
    assert fee_tx["status"] == "completed"
    assert marketplace_dataset["name"] in fee_tx["description"]

    # Verify Owner Transaction
    owner_txs_res = client.get("/credits/transactions", headers=owner_user["headers"])
    assert owner_txs_res.status_code == 200
    owner_txs = owner_txs_res.json()
    reward_tx = next((tx for tx in owner_txs if tx["transaction_type"] == "query_reward"), None)
    assert reward_tx is not None
    assert reward_tx["amount"] == settings.DATASET_OWNER_REWARD
    assert reward_tx["user_id"] == owner_id
    assert reward_tx["status"] == "completed"
    assert marketplace_dataset["name"] in reward_tx["description"]


# 9. Querying own dataset follows the defined rule (free of charge, no reward gaming)
def test_querying_own_dataset_follows_defined_rule(client, owner_user, marketplace_dataset):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT plan, subscribers FROM {table}")

    owner_id = owner_user["user_id"]
    credits_before = get_user_credits(owner_id)

    # 1. Self query with normal balance
    res = client.post("/query", headers=owner_user["headers"], json={
        "query": "View my own dataset plans",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 200
    assert res.json()["credits_charged"] == 0
    assert get_user_credits(owner_id) == credits_before

    # Verify no fee or reward transactions generated
    txs_res = client.get("/credits/transactions", headers=owner_user["headers"])
    tx_types = [tx["transaction_type"] for tx in txs_res.json()]
    assert "query_fee" not in tx_types
    assert "query_reward" not in tx_types

    # 2. Self query with 0 balance succeeds (creators can explore their own data freely)
    set_user_credits(owner_id, 0)
    res_zero = client.post("/query", headers=owner_user["headers"], json={
        "query": "View my own dataset plans with 0 credits",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res_zero.status_code == 200
    assert res_zero.json()["credits_charged"] == 0
    assert get_user_credits(owner_id) == 0


# 10. Configurable query cost and owner reward
def test_configurable_query_cost_and_owner_reward(client, buyer_user, marketplace_dataset, owner_user):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table}")

    settings.QUERY_COST = 10
    settings.DATASET_OWNER_REWARD = 7

    buyer_id = buyer_user["user_id"]
    owner_id = owner_user["user_id"]
    buyer_credits_before = get_user_credits(buyer_id)
    owner_credits_before = get_user_credits(owner_id)

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "Retrieve SaaS table with custom rates",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 200
    assert res.json()["credits_charged"] == 10

    assert get_user_credits(buyer_id) == buyer_credits_before - 10
    assert get_user_credits(owner_id) == owner_credits_before + 7


# 11. Unauthenticated query is rejected with 401
def test_unauthenticated_query_rejected(client, marketplace_dataset):
    res = client.post("/query", json={
        "query": "Show subscribers",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 401


# 12. Atomic rollback on transaction failure
def test_query_atomic_rollback_on_transaction_failure(client, monkeypatch, buyer_user, marketplace_dataset, owner_user):
    table = marketplace_dataset["table_name"]
    set_ai_generator(lambda q, t, cols: f"SELECT * FROM {table}")

    buyer_id = buyer_user["user_id"]
    owner_id = owner_user["user_id"]
    buyer_credits_before = get_user_credits(buyer_id)
    owner_credits_before = get_user_credits(owner_id)

    # Monkeypatch apply_query_marketplace_transaction to raise an unexpected database exception
    import app.routers.query as query_module
    def failing_tx(*args, **kwargs):
        raise RuntimeError("Simulated unexpected SQLite I/O failure during credit commit")

    monkeypatch.setattr(query_module, "apply_query_marketplace_transaction", failing_tx)

    res = client.post("/query", headers=buyer_user["headers"], json={
        "query": "Show all SaaS metrics",
        "dataset_id": marketplace_dataset["dataset_id"]
    })
    assert res.status_code == 500
    assert "failed to record marketplace query transaction" in res.json()["detail"].lower()

    # Verify atomic rollback: neither buyer was charged nor owner was rewarded
    assert get_user_credits(buyer_id) == buyer_credits_before
    assert get_user_credits(owner_id) == owner_credits_before

