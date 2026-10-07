import hashlib
import secrets
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, status, Depends
from app.database import get_db_connection

def hash_password(password: str) -> str:
    salt = "datapulse_salt_v1"
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

def create_access_token(user_id: str) -> str:
    token = secrets.token_hex(32)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tokens (token, user_id) VALUES (?, ?)",
        (token, user_id)
    )
    conn.commit()
    return token

def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = parts[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT u.id, u.email, u.full_name, u.credits, u.created_at FROM tokens t JOIN users u ON t.user_id = u.id WHERE t.token = ?",
        (token,)
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return dict(row)

def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    if not authorization:
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None
