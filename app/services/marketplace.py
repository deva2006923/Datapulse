import uuid
import datetime
import sqlite3
from typing import Dict, Any, Optional, Tuple
from app.config import settings


class InsufficientCreditsError(Exception):
    """Raised when a user does not have enough credits to perform a query."""
    def __init__(self, current_balance: int, required_credits: int):
        self.current_balance = current_balance
        self.required_credits = required_credits
        super().__init__(
            f"Insufficient credit balance to execute query. Required: {required_credits}, available: {current_balance}."
        )


def get_user_balance(user_id: str, conn: sqlite3.Connection) -> int:
    """Fetch current real-time credit balance for a user from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return 0
    return row["credits"]


def check_query_permission_and_cost(
    user_id: str,
    dataset_owner_id: Optional[str],
    conn: sqlite3.Connection
) -> Tuple[int, int, bool]:
    """
    Determines query cost and dataset owner reward based on ownership rules.

    RULE: Querying Own Dataset:
      - query_cost = 0 (free self-service querying for dataset owners)
      - owner_reward = 0 (prevents self-reward gaming and artificial credit inflation)
      - is_own_dataset = True
      - Creators can query their own datasets without being blocked even with 0 credits.

    RULE: Querying Another User's Dataset:
      - query_cost = max(0, settings.QUERY_COST)
      - owner_reward = max(0, settings.DATASET_OWNER_REWARD)
      - is_own_dataset = False
      - User balance must be >= query_cost; raises InsufficientCreditsError if balance is too low.
    """
    is_own_dataset = bool(dataset_owner_id and user_id == dataset_owner_id)
    if is_own_dataset:
        return 0, 0, True

    cost = max(0, settings.QUERY_COST)
    reward = max(0, settings.DATASET_OWNER_REWARD)

    current_balance = get_user_balance(user_id, conn)
    if current_balance < cost:
        raise InsufficientCreditsError(current_balance, cost)

    return cost, reward, False


def apply_query_marketplace_transaction(
    conn: sqlite3.Connection,
    querying_user_id: str,
    dataset_owner_id: Optional[str],
    dataset_id: str,
    dataset_name: str,
    query_id: str,
    query_cost: int,
    owner_reward: int,
    is_own_dataset: bool,
    now: Optional[str] = None
) -> Dict[str, Any]:
    """
    Atomically performs:
      1. Credit deduction from querying user (with atomic balance guard).
      2. Credit reward to dataset owner (if different user and reward > 0).
      3. Credit transaction recording in credit_transactions for auditability.

    Raises InsufficientCreditsError if balance check fails during the atomic update.
    """
    if is_own_dataset or query_cost == 0:
        return {
            "charged": 0,
            "rewarded": 0,
            "is_own_dataset": True,
            "fee_transaction_id": None,
            "reward_transaction_id": None
        }

    if not now:
        now = datetime.datetime.utcnow().isoformat()

    cursor = conn.cursor()

    # 1. Atomic deduction with negative-balance guard
    cursor.execute(
        "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
        (query_cost, querying_user_id, query_cost)
    )
    if cursor.rowcount == 0:
        balance = get_user_balance(querying_user_id, conn)
        raise InsufficientCreditsError(balance, query_cost)

    # 2. Record fee transaction for querying user
    fee_tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    fee_desc = f"Query execution fee for query {query_id} on dataset '{dataset_name}' ({dataset_id})"
    cursor.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, ?, 'query_fee', ?, 'completed', ?)
    """, (fee_tx_id, querying_user_id, -query_cost, fee_desc, now))

    # 3. Reward dataset owner if owner exists and reward > 0
    reward_tx_id = None
    rewarded_amount = 0
    if dataset_owner_id and owner_reward > 0 and dataset_owner_id != querying_user_id:
        cursor.execute("SELECT id FROM users WHERE id = ?", (dataset_owner_id,))
        if cursor.fetchone():
            cursor.execute(
                "UPDATE users SET credits = credits + ? WHERE id = ?",
                (owner_reward, dataset_owner_id)
            )
            reward_tx_id = f"tx_{uuid.uuid4().hex[:12]}"
            reward_desc = f"Query reward for query {query_id} on dataset '{dataset_name}' ({dataset_id})"
            cursor.execute("""
                INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
                VALUES (?, ?, ?, 'query_reward', ?, 'completed', ?)
            """, (reward_tx_id, dataset_owner_id, owner_reward, reward_desc, now))
            rewarded_amount = owner_reward

    return {
        "charged": query_cost,
        "rewarded": rewarded_amount,
        "is_own_dataset": False,
        "fee_transaction_id": fee_tx_id,
        "reward_transaction_id": reward_tx_id
    }
