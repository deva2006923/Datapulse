import uuid
import datetime
from fastapi import HTTPException, status, Depends
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_user
from app.schemas import RedeemRequest, RedeemResponse, TransactionItem
from typing import List

router = TrailingSlashRouter(tags=["Credits & Rewards"])

@router.post("/credits/redeem", response_model=RedeemResponse)
@router.post("/redeem", response_model=RedeemResponse)
def redeem_credits(req: RedeemRequest, user: dict = Depends(get_current_user)):
    """
    Redeem accumulated credits for payout.
    Validates minimum balance and raises 422 if balance is insufficient or invalid.
    """
    if req.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Redeem amount must be greater than 0"
        )
        
    current_balance = user["credits"]
    if current_balance < req.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient credit balance. You currently have {current_balance} credits, but requested {req.amount}."
        )
        
    new_balance = current_balance - req.amount
    # 100 credits = $10.00 USD
    cash_value = round((req.amount / 100.0) * 10.0, 2)
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.utcnow().isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Deduct credits
    cursor.execute("UPDATE users SET credits = ? WHERE id = ?", (new_balance, user["id"]))
    
    # Insert transaction
    desc = f"Redeemed {req.amount} credits via {req.payout_method} to {req.destination}"
    cursor.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, ?, 'redeem', ?, 'completed', ?)
    """, (tx_id, user["id"], -req.amount, desc, now))
    
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
