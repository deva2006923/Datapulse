import uuid
import datetime
import hashlib
import hmac
import secrets
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, status, Depends
from app.database import get_db_connection
from app.config import settings

PBKDF2_SCHEME = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 310000
LEGACY_SALT = "datapulse_salt_v1"


def hash_password(password: str) -> str:
    """Hash password with per-user random salt using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{PBKDF2_SCHEME}${PBKDF2_ITERATIONS}${salt}${dk}"


def needs_password_rehash(hashed_password: str) -> bool:
    """Returns True if a stored hash uses the legacy unsalted-per-user SHA-256 scheme."""
    if not hashed_password or not hashed_password.startswith(f"{PBKDF2_SCHEME}$"):
        return True
    parts = hashed_password.split("$")
    if len(parts) != 4:
        return True
    try:
        return int(parts[1]) < PBKDF2_ITERATIONS
    except ValueError:
        return True


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time verification supporting PBKDF2-HMAC-SHA256 and legacy SHA-256 hashes."""
    if not plain_password or not hashed_password:
        return False

    if hashed_password.startswith(f"{PBKDF2_SCHEME}$"):
        parts = hashed_password.split("$")
        if len(parts) != 4:
            return False
        _, iter_str, salt_hex, expected_dk = parts
        try:
            iterations = int(iter_str)
            salt_bytes = bytes.fromhex(salt_hex)
        except ValueError:
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt_bytes,
            iterations,
        ).hex()
        return hmac.compare_digest(computed, expected_dk)

    # Backward-compatible verification for legacy SHA-256 hashes (upgraded transparently on login)
    legacy_hash = hashlib.sha256(f"{LEGACY_SALT}{plain_password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, hashed_password)


def _parse_utc_timestamp(ts: Optional[str]) -> Optional[datetime.datetime]:
    if not ts:
        return None
    normalized = ts.strip().replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1]
    try:
        return datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def create_access_token(user_id: str) -> str:
    token = secrets.token_hex(32)
    now = datetime.datetime.utcnow()
    ttl_hours = max(1, int(getattr(settings, "TOKEN_TTL_HOURS", 24)))
    expires_at = (now + datetime.timedelta(hours=ttl_hours)).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tokens (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token, user_id, expires_at, now.isoformat()),
    )
    conn.commit()
    return token


def revoke_access_token(token: str) -> bool:
    """Revokes a bearer session token server-side."""
    if not token:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tokens WHERE token = ?", (token,))
    deleted = cursor.rowcount > 0
    conn.commit()
    return deleted


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
        """
        SELECT u.id, u.email, u.full_name, u.credits, u.created_at, u.is_admin,
               t.expires_at AS token_expires_at, t.created_at AS token_created_at
        FROM tokens t
        JOIN users u ON t.user_id = u.id
        WHERE t.token = ?
        """,
        (token,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce session expiration (explicit expires_at or fallback created_at + TOKEN_TTL_HOURS)
    now = datetime.datetime.utcnow()
    expires_dt = _parse_utc_timestamp(row["token_expires_at"])
    if expires_dt is None:
        created_dt = _parse_utc_timestamp(row["token_created_at"])
        if created_dt is not None:
            ttl_hours = max(1, int(getattr(settings, "TOKEN_TTL_HOURS", 24)))
            expires_dt = created_dt + datetime.timedelta(hours=ttl_hours)

    if expires_dt is not None and now >= expires_dt:
        cursor.execute("DELETE FROM tokens WHERE token = ?", (token,))
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_dict = {
        "id": row["id"],
        "email": row["email"],
        "full_name": row["full_name"],
        "credits": row["credits"],
        "created_at": row["created_at"],
        "is_admin": row["is_admin"],
    }
    return user_dict

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
