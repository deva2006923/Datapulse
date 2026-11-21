"""
TEMPORARY One-Time Production Administrator Activation Endpoint.

Purpose:
  Allows promoting the single existing account matching settings.ADMIN_EMAIL
  to is_admin = 1 on hosting plans without shell access (e.g. Render Free).

Security guarantees:
  - Disabled (HTTP 404) unless ADMIN_BOOTSTRAP_TOKEN (>= 32 chars) is set via env var
    and has not already been consumed.
  - Requires HTTPS (X-Forwarded-Proto: https or https URL scheme) and HTTP POST.
  - Token must be sent in the X-Admin-Bootstrap-Token header (never in URL query params).
  - Constant-time comparison via hmac.compare_digest for token and configured ADMIN_EMAIL.
  - Promotes ONLY the existing account matching ADMIN_EMAIL by setting users.is_admin = 1.
  - Never creates users, resets passwords, changes credits, lists users, or touches other accounts.
  - Strictly one-time and atomic (in-process Lock + SQLite BEGIN IMMEDIATE + single-row PK).
  - Records a minimal audit log entry without ever storing or logging the bootstrap token.

Removal:
  After successful production activation, remove this file, its router registration
  in app/main.py, ADMIN_BOOTSTRAP_TOKEN from app/config.py, and ADMIN_BOOTSTRAP_TOKEN
  from Render Environment Variables.
"""
import datetime
import hmac
import sqlite3
import threading
import uuid
from typing import Optional

from fastapi import Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.database import get_db_connection
from app.routers import TrailingSlashRouter
from app.services.admin_bootstrap import normalize_email

MIN_BOOTSTRAP_TOKEN_LENGTH = 32
_bootstrap_lock = threading.Lock()

router = TrailingSlashRouter(prefix="/admin/bootstrap", tags=["Admin Bootstrap"])


class AdminBootstrapActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(..., min_length=3, max_length=254)


class AdminBootstrapActivateResponse(BaseModel):
    status: str
    email: str
    is_admin: bool
    message: str


def _is_https_request(request: Request) -> bool:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded_proto == "https":
        return True
    return (request.url.scheme or "").lower() == "https"


def _get_configured_token() -> Optional[str]:
    raw = (settings.ADMIN_BOOTSTRAP_TOKEN or "").strip()
    if len(raw) < MIN_BOOTSTRAP_TOKEN_LENGTH:
        return None
    return raw


def _open_atomic_connection():
    """
    Opens a dedicated autocommit SQLite connection so BEGIN IMMEDIATE
    strictly serializes concurrent activation attempts at the database level.
    """
    db_path = settings.DATABASE_PATH
    if not db_path or db_path == ":memory:":
        return get_db_connection(), False
    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=15000;")
    except sqlite3.DatabaseError:
        pass
    return conn, True


def _is_bootstrap_consumed(conn: sqlite3.Connection) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT consumed FROM admin_bootstrap_state WHERE id = 1")
    row = cur.fetchone()
    return bool(row and row["consumed"] == 1)


@router.post(
    "/activate",
    response_model=AdminBootstrapActivateResponse,
    include_in_schema=False,
)
def activate_admin_account(
    payload: AdminBootstrapActivateRequest,
    request: Request,
    x_admin_bootstrap_token: Optional[str] = Header(default=None, alias="X-Admin-Bootstrap-Token"),
):
    # 1. Endpoint is disabled unless a strong (>= 32 char) env token is configured
    configured_token = _get_configured_token()
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )

    # 2. Never accept tokens or parameters via URL query strings
    if request.query_params:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden.",
        )

    # 3. Require HTTPS
    if not _is_https_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HTTPS is required.",
        )

    # 4. Constant-time token & email verification (generic error on any mismatch)
    supplied_token = (x_admin_bootstrap_token or "").strip()
    token_valid = bool(supplied_token) and hmac.compare_digest(
        supplied_token.encode("utf-8"),
        configured_token.encode("utf-8"),
    )

    configured_email = normalize_email(getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com"))
    supplied_email = normalize_email(str(payload.email))
    email_valid = bool(configured_email) and hmac.compare_digest(
        supplied_email.encode("utf-8"),
        configured_email.encode("utf-8"),
    )

    if not (token_valid and email_valid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden.",
        )

    # 5. One-time, atomic promotion under process lock + SQLite BEGIN IMMEDIATE
    with _bootstrap_lock:
        conn, should_close = _open_atomic_connection()
        in_tx = False
        try:
            if should_close:
                conn.execute("BEGIN IMMEDIATE")
                in_tx = True

            # Endpoint becomes disabled permanently once consumed
            if _is_bootstrap_consumed(conn):
                if in_tx:
                    conn.execute("ROLLBACK")
                    in_tx = False
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Not found.",
                )

            cur = conn.cursor()
            cur.execute(
                "SELECT id, email, is_admin FROM users WHERE LOWER(email) = ?",
                (configured_email,),
            )
            user_row = cur.fetchone()
            if not user_row:
                if in_tx:
                    conn.execute("ROLLBACK")
                    in_tx = False
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target administrator account does not exist.",
                )

            user_id = user_row["id"]
            now = datetime.datetime.utcnow().isoformat()

            if bool(user_row["is_admin"]):
                # Account is already admin; mark bootstrap consumed so endpoint disables itself
                cur.execute(
                    """
                    INSERT OR REPLACE INTO admin_bootstrap_state (id, consumed, consumed_by_user_id, consumed_at)
                    VALUES (1, 1, ?, ?)
                    """,
                    (user_id, now),
                )
                if in_tx:
                    conn.execute("COMMIT")
                    in_tx = False
                else:
                    conn.commit()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Administrator account is already active.",
                )

            # Promote ONLY users.is_admin = 1 on the exact existing account
            cur.execute(
                "UPDATE users SET is_admin = 1 WHERE id = ? AND LOWER(email) = ? AND is_admin = 0",
                (user_id, configured_email),
            )
            if cur.rowcount != 1:
                if in_tx:
                    conn.execute("ROLLBACK")
                    in_tx = False
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Activation could not be completed.",
                )

            # Record one-time consumption (PK CHECK (id = 1) enforces single execution at DB level)
            cur.execute(
                """
                INSERT INTO admin_bootstrap_state (id, consumed, consumed_by_user_id, consumed_at)
                VALUES (1, 1, ?, ?)
                """,
                (user_id, now),
            )

            # Record minimal audit event without ever recording the bootstrap token
            client_ip = request.client.host if request.client else None
            audit_id = f"audit_{uuid.uuid4().hex[:12]}"
            cur.execute(
                """
                INSERT INTO admin_audit_logs
                    (id, admin_user_id, admin_email, action, target_resource, details, ip_address, created_at)
                VALUES (?, ?, ?, 'ADMIN_BOOTSTRAP_ACTIVATE', ?, 'One-time administrator promotion completed', ?, ?)
                """,
                (audit_id, user_id, configured_email, user_id, client_ip, now),
            )

            if in_tx:
                conn.execute("COMMIT")
                in_tx = False
            else:
                conn.commit()

            return AdminBootstrapActivateResponse(
                status="activated",
                email=configured_email,
                is_admin=True,
                message="Administrator privileges activated. Remove ADMIN_BOOTSTRAP_TOKEN from your environment and remove the temporary bootstrap endpoint.",
            )
        except sqlite3.IntegrityError:
            if in_tx:
                conn.execute("ROLLBACK")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not found.",
            )
        except HTTPException:
            if in_tx:
                conn.execute("ROLLBACK")
            raise
        except Exception:
            if in_tx:
                conn.execute("ROLLBACK")
            raise
        finally:
            if should_close:
                conn.close()
