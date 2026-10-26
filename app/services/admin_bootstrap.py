import uuid
import datetime
from typing import Optional, Dict, Any
from app.config import settings
from app.database import get_db_connection
from app.auth import hash_password
from app.services.reputation import DEFAULT_INITIAL_REPUTATION


def normalize_email(email: str) -> str:
    """Normalize email address by trimming whitespace and converting to lowercase."""
    return (email or "").strip().lower()


def is_admin_email(email: str) -> bool:
    """Checks if the given email matches the configured administrative email."""
    configured_admin = normalize_email(getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com"))
    return normalize_email(email) == configured_admin


def promote_user_to_admin(email: str, conn=None) -> bool:
    """
    Promotes an existing user to administrative status if their email matches
    the configured administrative email.
    """
    norm_email = normalize_email(email)
    if not is_admin_email(norm_email):
        return False

    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = False

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (norm_email,))
    row = cursor.fetchone()
    if not row:
        return False

    user_id = row["id"]
    cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
    conn.commit()
    return True


def create_or_promote_admin(
    email: Optional[str] = None,
    password: Optional[str] = None,
    full_name: str = "Platform Administrator",
    conn=None
) -> Dict[str, Any]:
    """
    Securely initializes or promotes the designated administrator account.
    Never hardcodes passwords. Requires a strong password if creating a new admin.
    """
    target_email = normalize_email(email or getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com"))
    if not is_admin_email(target_email):
        raise ValueError(
            f"Cannot initialize admin account for '{target_email}'. Email does not match configured ADMIN_EMAIL ({settings.ADMIN_EMAIL})."
        )

    if conn is None:
        conn = get_db_connection()

    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, credits, is_admin FROM users WHERE LOWER(email) = ?", (target_email,))
    existing = cursor.fetchone()

    now = datetime.datetime.utcnow().isoformat()

    if existing:
        user_id = existing["id"]
        # If user exists, promote to admin and update password if one is supplied
        if password:
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters long.")
            new_hash = hash_password(password)
            cursor.execute(
                "UPDATE users SET is_admin = 1, password_hash = ? WHERE id = ?",
                (new_hash, user_id)
            )
        else:
            cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        conn.commit()
        return {
            "id": user_id,
            "email": target_email,
            "full_name": existing["full_name"],
            "is_admin": True,
            "action": "promoted"
        }
    else:
        # Create new admin user
        if not password or len(password) < 8:
            raise ValueError("A secure password with at least 8 characters is required to initialize a new admin account.")

        user_id = f"usr_admin_{uuid.uuid4().hex[:8]}"
        pwd_hash = hash_password(password)
        initial_credits = 500
        initial_rep = DEFAULT_INITIAL_REPUTATION

        cursor.execute("""
            INSERT INTO users (id, email, password_hash, full_name, credits, reputation_score, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (user_id, target_email, pwd_hash, full_name, initial_credits, initial_rep, now))

        # Welcome bonus transaction
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
            VALUES (?, ?, ?, 'bonus', 'Administrator bootstrap credits', 'completed', ?)
        """, (tx_id, user_id, initial_credits, now))

        conn.commit()
        return {
            "id": user_id,
            "email": target_email,
            "full_name": full_name,
            "is_admin": True,
            "action": "created"
        }
