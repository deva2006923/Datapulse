import uuid
import datetime
from fastapi import HTTPException, status, Depends
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.schemas import UserRegisterRequest, UserLoginRequest, AuthTokenResponse, UserResponse
from app.auth import hash_password, verify_password, create_access_token, get_current_user

router = TrailingSlashRouter(tags=["Authentication"])

@router.post("/auth/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: UserRegisterRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check existing user
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists"
        )
        
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    pwd_hash = hash_password(req.password)
    now = datetime.datetime.utcnow().isoformat()
    initial_credits = 100
    
    cursor.execute("""
        INSERT INTO users (id, email, password_hash, full_name, credits, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, req.email, pwd_hash, req.full_name, initial_credits, now))
    
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
            email=req.email,
            full_name=req.full_name,
            credits=initial_credits,
            created_at=now
        )
    )

@router.post("/auth/login", response_model=AuthTokenResponse)
def login(req: UserLoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, email, password_hash, full_name, credits, created_at FROM users WHERE email = ?", (req.email,))
    row = cursor.fetchone()
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    user_id = row["id"]
    token = create_access_token(user_id)
    
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            email=row["email"],
            full_name=row["full_name"],
            credits=row["credits"],
            created_at=row["created_at"]
        )
    )

@router.get("/auth/me", response_model=UserResponse)
@router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        credits=user["credits"],
        created_at=user["created_at"]
    )
