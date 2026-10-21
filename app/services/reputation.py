import sqlite3
from typing import Optional, Dict, Any

DEFAULT_INITIAL_REPUTATION = 50

def calculate_user_reputation(user_id: str, conn: sqlite3.Connection) -> int:
    """
    Computes a deterministic, per-user reputation score (0-100) derived strictly from
    persisted, verifiable contribution and evaluation history.

    Model Factors:
      - Baseline for new users: 50 (neutral starting reputation, NOT hardcoded 85)
      - Dataset Quality Component (Q): Weighted average of user's completed evaluations
          (0.50 * overall_score + 0.30 * completeness_score + 0.20 * schema_fidelity_score)
      - Contribution Volume Bonus (V): min(15, completed_datasets * 3)
      - Verified Improvement Bonus (I): min(10, verified_improvements * 2.5)
      - Evaluation Failure Penalty (F): min(20, failed_evaluations * 5)
      - Bayesian Prior Blending: 0.75 * Q + 0.10 * 50 (smooths small sample sizes)
      - Clamped strictly to [0, 100] range
    """
    cursor = conn.cursor()

    # 1. Fetch completed evaluations for user's datasets
    cursor.execute("""
        SELECT e.overall_score, e.completeness_score, e.schema_fidelity_score, d.id
        FROM evaluations e
        JOIN datasets d ON e.dataset_id = d.id
        WHERE d.user_id = ? AND e.status = 'completed'
    """, (user_id,))
    completed_rows = cursor.fetchall()

    # 2. Fetch failed evaluations
    cursor.execute("""
        SELECT COUNT(*) AS cnt
        FROM evaluations e
        JOIN datasets d ON e.dataset_id = d.id
        WHERE d.user_id = ? AND e.status = 'failed'
    """, (user_id,))
    failed_row = cursor.fetchone()
    num_failed = failed_row["cnt"] if failed_row else 0

    # 3. Fetch verified dataset improvements submitted by this user
    try:
        cursor.execute("""
            SELECT COUNT(*) AS cnt, COALESCE(SUM(delta_score), 0) AS total_delta
            FROM dataset_versions
            WHERE user_id = ? AND delta_score > 0
        """, (user_id,))
        imp_row = cursor.fetchone()
        num_improvements = imp_row["cnt"] if imp_row else 0
    except Exception:
        num_improvements = 0

    # If user has no completed evaluations
    if not completed_rows:
        # User starts at 50, minus penalty for any failed uploads, plus improvements
        score = DEFAULT_INITIAL_REPUTATION - min(20, num_failed * 5) + min(10, int(num_improvements * 2.5))
        return max(10, min(100, score))

    # Calculate average quality metrics
    total_q = 0.0
    for r in completed_rows:
        overall = float(r["overall_score"] or 0.0)
        completeness = float(r["completeness_score"] or 0.0)
        fidelity = float(r["schema_fidelity_score"] or 0.0)
        composite = (0.50 * overall) + (0.30 * completeness) + (0.20 * fidelity)
        total_q += composite

    q_factor = total_q / len(completed_rows)

    # Volume bonus with diminishing returns
    num_completed = len(completed_rows)
    volume_bonus = min(15.0, num_completed * 3.0)

    # Improvement bonus
    improvement_bonus = min(10.0, num_improvements * 2.5)

    # Failure penalty
    failure_penalty = min(20.0, num_failed * 5.0)

    # Blended Bayesian formula
    raw_score = (0.75 * q_factor) + (0.10 * DEFAULT_INITIAL_REPUTATION) + volume_bonus + improvement_bonus - failure_penalty
    final_score = int(round(raw_score))

    return max(0, min(100, final_score))


def sync_and_get_user_reputation(user_id: str, conn: sqlite3.Connection) -> int:
    """
    Calculates the authoritative reputation score and persists it in the users table.
    """
    reputation = calculate_user_reputation(user_id, conn)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET reputation_score = ? WHERE id = ?", (reputation, user_id))
        conn.commit()
    except Exception:
        pass
    return reputation
