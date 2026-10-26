import uuid
import datetime
from fastapi import HTTPException, status, Depends
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.schemas import UserRegisterRequest, UserLoginRequest, AuthTokenResponse, UserResponse
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.services.reputation import sync_and_get_user_reputation, DEFAULT_INITIAL_REPUTATION

router = TrailingSlashRouter(tags=["Authentication"])

@router.post("/auth/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: UserRegisterRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    norm_email = req.email.strip().lower()
    
    # Check existing user
    cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (norm_email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists"
        )
        
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    pwd_hash = hash_password(req.password)
    now = datetime.datetime.utcnow().isoformat()
    initial_credits = 100
    initial_reputation = DEFAULT_INITIAL_REPUTATION
    
    cursor.execute("""
        INSERT INTO users (id, email, password_hash, full_name, credits, reputation_score, is_admin, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
    """, (user_id, norm_email, pwd_hash, req.full_name, initial_credits, initial_reputation, now))
    
    # Welcome bonus transaction
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, ?, 'bonus', 'Welcome bonus credits', 'completed', ?)
    """, (tx_id, user_id, initial_credits, now))
    
    conn.commit()
    
    token = create_access_token(user_id)
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            email=norm_email,
            full_name=req.full_name,
            credits=initial_credits,
            reputation_score=initial_reputation,
            is_admin=False,
            created_at=now
        )
    )

@router.post("/auth/login", response_model=AuthTokenResponse)
def login(req: UserLoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    norm_email = req.email.strip().lower()
    
    cursor.execute("SELECT id, email, password_hash, full_name, credits, created_at, is_admin FROM users WHERE LOWER(email) = ?", (norm_email,))
    row = cursor.fetchone()
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    user_id = row["id"]
    token = create_access_token(user_id)
    rep_score = sync_and_get_user_reputation(user_id, conn)

    from app.config import settings
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com").strip().lower()
    is_admin_flag = bool(row["is_admin"]) if "is_admin" in row.keys() else False
    is_admin = (row["email"].strip().lower() == admin_email and is_admin_flag)
    
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            email=row["email"],
            full_name=row["full_name"],
            credits=row["credits"],
            reputation_score=rep_score,
            is_admin=is_admin,
            created_at=row["created_at"]
        )
    )

@router.get("/auth/me", response_model=UserResponse)
@router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    rep_score = sync_and_get_user_reputation(user["id"], conn)
    # Refresh current user credit balance and is_admin from database
    cursor = conn.cursor()
    cursor.execute("SELECT credits, is_admin FROM users WHERE id = ?", (user["id"],))
    u_row = cursor.fetchone()
    current_credits = u_row["credits"] if u_row else user["credits"]
    
    from app.config import settings
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com").strip().lower()
    is_admin_flag = bool(u_row["is_admin"]) if (u_row and "is_admin" in u_row.keys()) else bool(user.get("is_admin", 0))
    is_admin = (user["email"].strip().lower() == admin_email and is_admin_flag)

    return UserResponse(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        credits=current_credits,
        reputation_score=rep_score,
        is_admin=is_admin,
        created_at=user["created_at"]
    )

