import threading
import uuid
import datetime
from fastapi import HTTPException, status, Depends
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_user
from app.schemas import RedeemRequest, RedeemResponse, TransactionItem
from typing import List

router = TrailingSlashRouter(tags=["Credits & Rewards"])
_redeem_lock = threading.Lock()


@router.post("/credits/redeem", response_model=RedeemResponse)
@router.post("/redeem", response_model=RedeemResponse)
def redeem_credits(req: RedeemRequest, user: dict = Depends(get_current_user)):
    """
    Redeem accumulated credits for payout.
    Uses atomic guarded SQL deduction under lock to prevent concurrent double-spend or negative balances.
    """
    if req.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Redeem amount must be greater than 0"
        )

    # 100 credits = $10.00 USD
    cash_value = round((req.amount / 100.0) * 10.0, 2)
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.utcnow().isoformat()
    desc = f"Redeemed {req.amount} credits via {req.payout_method} to {req.destination}"

    with _redeem_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Atomic negative-balance-safe deduction
        cursor.execute(
            "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
            (req.amount, user["id"], req.amount),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
            bal_row = cursor.fetchone()
            current_balance = int(bal_row["credits"]) if bal_row else 0
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient credit balance. You currently have {current_balance} credits, but requested {req.amount}."
            )

        cursor.execute("""
            INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
            VALUES (?, ?, ?, 'redeem', ?, 'completed', ?)
        """, (tx_id, user["id"], -req.amount, desc, now))

        cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
        bal_after_row = cursor.fetchone()
        new_balance = int(bal_after_row["credits"]) if bal_after_row else 0
        conn.commit()

    return RedeemResponse(
        success=True,
        redeemed_credits=req.amount,
        cash_value_usd=cash_value,
        remaining_balance=new_balance,
        transaction_id=tx_id,
        message=f"Successfully redeemed {req.amount} credits for ${cash_value:.2f} USD."
    )

@router.get("/credits/transactions", response_model=List[TransactionItem])
def get_user_transactions(user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, amount, transaction_type, description, status, created_at FROM credit_transactions WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],)
    )
    rows = cursor.fetchall()
    return [
        TransactionItem(
            id=r["id"],
            user_id=r["user_id"],
            amount=r["amount"],
            transaction_type=r["transaction_type"],
            description=r["description"],
            status=r["status"],
            created_at=r["created_at"]
        ) for r in rows
    ]
