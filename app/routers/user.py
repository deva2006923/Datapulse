from fastapi import Depends
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_user
from app.schemas import UserStatsResponse, TransactionItem

router = TrailingSlashRouter(tags=["User Statistics"])

@router.get("/me/stats", response_model=UserStatsResponse)
def get_user_stats(user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Refresh current user credit balance
    cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
    u_row = cursor.fetchone()
    current_credits = u_row["credits"] if u_row else user["credits"]
    
    # Datasets uploaded count
    cursor.execute("SELECT COUNT(*) AS cnt FROM datasets WHERE user_id = ?", (user["id"],))
    ds_count = cursor.fetchone()["cnt"]
    
    # Completed evaluations and average score
    cursor.execute("""
        SELECT COUNT(*) AS cnt, AVG(e.overall_score) AS avg_score
        FROM evaluations e
        JOIN datasets d ON e.dataset_id = d.id
        WHERE d.user_id = ? AND e.status = 'completed'
    """, (user["id"],))
    eval_row = cursor.fetchone()
    eval_count = eval_row["cnt"] or 0
    avg_score = round(float(eval_row["avg_score"] or 0.0), 2)
    
    # Recent transactions
    cursor.execute("""
        SELECT id, user_id, amount, transaction_type, description, status, created_at
        FROM credit_transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (user["id"],))
    tx_rows = cursor.fetchall()
    
    transactions = [
        TransactionItem(
            id=r["id"],
            user_id=r["user_id"],
            amount=r["amount"],
            transaction_type=r["transaction_type"],
            description=r["description"],
            status=r["status"],
            created_at=r["created_at"]
        ) for r in tx_rows
    ]
    
    return UserStatsResponse(
        user_id=user["id"],
        email=user["email"],
        credits_balance=current_credits,
        datasets_uploaded=ds_count,
        total_evaluations_completed=eval_count,
        average_quality_score=avg_score,
        recent_transactions=transactions
    )
