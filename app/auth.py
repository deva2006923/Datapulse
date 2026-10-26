import uuid
import datetime
import hashlib
import secrets
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, status, Depends
from app.database import get_db_connection
from app.config import settings

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
        "SELECT u.id, u.email, u.full_name, u.credits, u.created_at, u.is_admin FROM tokens t JOIN users u ON t.user_id = u.id WHERE t.token = ?",
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

def get_current_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Dedicated authorization dependency for all administrator endpoints.
    Verifies that:
      1. The user is authenticated (handled by get_current_user -> 401 if missing/invalid token).
      2. The user's normalized email strictly matches configured settings.ADMIN_EMAIL.
      3. The user's record in the database has is_admin = 1.
    Raises HTTP 403 Forbidden for any authenticated non-admin user.
    """
    admin_email = getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com").strip().lower()
    user_email = (current_user.get("email") or "").strip().lower()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE id = ?", (current_user["id"],))
    row = cursor.fetchone()
    is_admin_flag = bool(row["is_admin"]) if row and "is_admin" in row.keys() else False

    if user_email != admin_email or not is_admin_flag:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required. Access denied."
        )

    admin_copy = dict(current_user)
    admin_copy["is_admin"] = True
    return admin_copy

def log_admin_audit(
    admin_user_id: str,
    admin_email: str,
    action: str,
    target_resource: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None
) -> None:
    """Safely logs an administrative action or sensitive view access to admin_audit_logs."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        log_id = f"audit_{uuid.uuid4().hex[:12]}"
        now = datetime.datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO admin_audit_logs (id, admin_user_id, admin_email, action, target_resource, details, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, admin_user_id, admin_email, action, target_resource, details, ip_address, now))
        conn.commit()
    except Exception:
        # Never break an admin operation due to audit logging failure
        pass
