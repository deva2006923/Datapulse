import logging
import sqlite3
import uuid
import datetime
from typing import Optional, Dict, Any
from app.config import settings
from app.database import get_db_connection
from app.auth import hash_password
from app.services.reputation import DEFAULT_INITIAL_REPUTATION

logger = logging.getLogger("datapulse.admin")
MIN_ADMIN_PASSWORD_LENGTH = 8


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


def ensure_default_admin(
    email: Optional[str] = None,
    password: Optional[str] = None,
    full_name: str = "Platform Administrator",
    conn=None,
) -> Dict[str, Any]:
    """
    Idempotent startup provisioning for the permanent default platform administrator.

    Rules:
      - Uses configured settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD by default.
      - If the configured admin account already exists:
          ensures users.is_admin = 1 WITHOUT modifying password_hash, credits,
          full_name, reputation_score, or any other user account.
      - If the configured admin account does not exist:
          creates it with a securely hashed password and is_admin = 1 (requires
          ADMIN_PASSWORD >= 8 chars; never hardcodes a fallback password).
      - Never creates duplicate administrator accounts (handles race via UNIQUE email).
      - Never logs or returns plaintext passwords or password hashes.
    """
    target_email = normalize_email(
        email if email is not None else getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com")
    )
    if not target_email or not is_admin_email(target_email):
        logger.warning("Default admin provisioning skipped: target email does not match configured ADMIN_EMAIL.")
        return {"status": "skipped_invalid_email", "email": target_email, "is_admin": False}

    raw_password = password if password is not None else getattr(settings, "ADMIN_PASSWORD", None)
    clean_password = raw_password.strip() if isinstance(raw_password, str) else ""

    if conn is None:
        conn = get_db_connection()

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, email, full_name, credits, is_admin FROM users WHERE LOWER(email) = ?",
        (target_email,),
    )
    existing = cursor.fetchone()

    if existing:
        user_id = existing["id"]
        if bool(existing["is_admin"]):
            logger.info("Default administrator account verified (%s): already active.", target_email)
            return {
                "status": "unchanged",
                "id": user_id,
                "email": target_email,
                "is_admin": True,
            }

        # Promote existing account strictly by flipping is_admin = 1; preserve password, credits, and profile
        cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ? AND LOWER(email) = ?", (user_id, target_email))
        conn.commit()
        logger.info("Default administrator account promoted (%s): is_admin set to 1.", target_email)
        return {
            "status": "promoted",
            "id": user_id,
            "email": target_email,
            "is_admin": True,
        }

    # Account does not exist yet: require ADMIN_PASSWORD from environment (never hardcode)
    if not clean_password:
        logger.warning(
            "Default administrator account (%s) does not exist and ADMIN_PASSWORD is not set; skipping automatic creation.",
            target_email,
        )
        return {
            "status": "skipped_missing_password",
            "email": target_email,
            "is_admin": False,
        }

    if len(clean_password) < MIN_ADMIN_PASSWORD_LENGTH:
        logger.warning(
            "Default administrator provisioning skipped (%s): ADMIN_PASSWORD must be at least %d characters.",
            target_email,
            MIN_ADMIN_PASSWORD_LENGTH,
        )
        return {
            "status": "skipped_weak_password",
            "email": target_email,
            "is_admin": False,
        }

    now = datetime.datetime.utcnow().isoformat()
    user_id = f"usr_admin_{uuid.uuid4().hex[:8]}"
    pwd_hash = hash_password(clean_password)
    initial_credits = 500
    initial_rep = DEFAULT_INITIAL_REPUTATION

    try:
        cursor.execute(
            """
            INSERT INTO users (id, email, password_hash, full_name, credits, reputation_score, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (user_id, target_email, pwd_hash, full_name, initial_credits, initial_rep, now),
        )
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        cursor.execute(
            """
            INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
            VALUES (?, ?, ?, 'bonus', 'Administrator bootstrap credits', 'completed', ?)
            """,
            (tx_id, user_id, initial_credits, now),
        )
        conn.commit()
        logger.info("Default administrator account provisioned (%s).", target_email)
        return {
            "status": "created",
            "id": user_id,
            "email": target_email,
            "is_admin": True,
        }
    except sqlite3.IntegrityError:
        # Concurrent startup race: row was created by another startup sequence; ensure is_admin = 1 only
        conn.rollback()
        cursor.execute(
            "SELECT id, is_admin FROM users WHERE LOWER(email) = ?",
            (target_email,),
        )
        race_row = cursor.fetchone()
        if race_row:
            if not bool(race_row["is_admin"]):
                cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (race_row["id"],))
                conn.commit()
                return {"status": "promoted", "id": race_row["id"], "email": target_email, "is_admin": True}
            return {"status": "unchanged", "id": race_row["id"], "email": target_email, "is_admin": True}
        raise
