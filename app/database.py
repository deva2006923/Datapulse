import os
import re
import sqlite3
import json
import logging
import threading
from typing import Optional, Dict, Any, List, Sequence, Tuple
from app.config import settings

logger = logging.getLogger("datapulse.database")
_local = threading.local()

_EXTRA_INTEGRITY_ERRORS: List[type] = []
try:
    import psycopg  # type: ignore
    _EXTRA_INTEGRITY_ERRORS.append(psycopg.IntegrityError)
except Exception:
    psycopg = None  # type: ignore

try:
    import psycopg2  # type: ignore
    _EXTRA_INTEGRITY_ERRORS.append(psycopg2.IntegrityError)
except Exception:
    psycopg2 = None  # type: ignore

DB_INTEGRITY_ERRORS: Tuple[type, ...] = (sqlite3.IntegrityError, *_EXTRA_INTEGRITY_ERRORS)


def get_db_backend() -> str:
    """Return active metadata database backend ('postgresql' or 'sqlite')."""
    return "postgresql" if settings.is_postgres_configured else "sqlite"


def is_postgres_backend() -> bool:
    """Return True when PostgreSQL (DATABASE_URL) is the active metadata backend."""
    return get_db_backend() == "postgresql"


def _translate_qmark_to_pyformat(sql: str) -> str:
    """
    Convert SQLite '?' parameter placeholders to PostgreSQL '%s' placeholders
    while escaping literal '%' signs and preserving '?' inside quoted literals.
    """
    out: List[str] = []
    in_single = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            out.append(ch)
            if in_single and i + 1 < n and sql[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            in_single = not in_single
        elif ch == "%" and not in_single:
            out.append("%%")
        elif ch == "%" and in_single:
            out.append("%%")
        elif ch == "?" and not in_single:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _split_sql_script(script: str) -> List[str]:
    """Split a semicolon-delimited DDL script into individual executable statements."""
    statements: List[str] = []
    buf: List[str] = []
    in_single = False
    i = 0
    n = len(script)
    while i < n:
        ch = script[i]
        if ch == "'":
            buf.append(ch)
            if in_single and i + 1 < n and script[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            in_single = not in_single
        elif ch == ";" and not in_single:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


class _CompatRow:
    """sqlite3.Row-compatible mapping supporting dict(row), row['col'], row[0], and row.keys()."""

    def __init__(self, columns: List[str], values: Sequence[Any]):
        self._columns = columns
        self._values = tuple(values)
        self._map = dict(zip(columns, self._values))

    def keys(self) -> List[str]:
        return list(self._columns)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._map[key]

    def __contains__(self, key) -> bool:
        return key in self._map

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        return self._map.get(key, default)


class _PostgresCursorAdapter:
    """Wraps a psycopg/psycopg2 cursor to match DataPulse's sqlite3 cursor contract."""

    def __init__(self, raw_cursor):
        self._cursor = raw_cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def execute(self, sql: str, params: Any = None):
        translated = _translate_qmark_to_pyformat(sql)
        if params is None:
            self._cursor.execute(translated)
        else:
            self._cursor.execute(translated, tuple(params))
        return self

    def executemany(self, sql: str, seq_of_params: Sequence[Any]):
        translated = _translate_qmark_to_pyformat(sql)
        self._cursor.executemany(translated, [tuple(p) for p in seq_of_params])
        return self

    def executescript(self, script: str):
        for stmt in _split_sql_script(script):
            self._cursor.execute(stmt)
        return self

    def _wrap_row(self, raw_row):
        if raw_row is None:
            return None
        cols = [desc[0] for desc in (self._cursor.description or [])]
        return _CompatRow(cols, raw_row)

    def fetchone(self):
        return self._wrap_row(self._cursor.fetchone())

    def fetchall(self):
        rows = self._cursor.fetchall()
        cols = [desc[0] for desc in (self._cursor.description or [])]
        return [_CompatRow(cols, r) for r in rows]

    def close(self):
        self._cursor.close()


class _PostgresConnectionAdapter:
    """Wraps a psycopg/psycopg2 connection with transactional ACID commit/rollback semantics."""

    def __init__(self, raw_conn):
        self._conn = raw_conn
        self.backend = "postgresql"

    def cursor(self) -> _PostgresCursorAdapter:
        return _PostgresCursorAdapter(self._conn.cursor())

    def execute(self, sql: str, params: Any = None) -> _PostgresCursorAdapter:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def redact_database_url(url: Optional[str]) -> str:
    """Redact credentials from a database URL or libpq connection string before logging/reporting."""
    raw = (url or "").strip()
    if not raw:
        return "<unset>"
    # Redact scheme://user:password@host -> scheme://***:***@host
    redacted = re.sub(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/@\s]+@)", r"\1***:***@", raw)
    # Redact key=value password tokens (libpq style)
    redacted = re.sub(r"(?i)(password\s*=\s*)([^\s'\"&]+)", r"\1***", redacted)
    return redacted


def _open_postgres_connection() -> _PostgresConnectionAdapter:
    url = (settings.DATABASE_URL or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    safe_target = redact_database_url(url)
    if psycopg is not None:
        try:
            raw_conn = psycopg.connect(url, autocommit=False)
            return _PostgresConnectionAdapter(raw_conn)
        except Exception as exc:
            logger.error("Failed to connect to PostgreSQL metadata database (%s).", safe_target)
            raise RuntimeError(
                f"PostgreSQL metadata database connection failed ({safe_target}): {redact_database_url(str(exc))}"
            ) from None
    if psycopg2 is not None:
        try:
            raw_conn = psycopg2.connect(url)
            raw_conn.autocommit = False
            return _PostgresConnectionAdapter(raw_conn)
        except Exception as exc:
            logger.error("Failed to connect to PostgreSQL metadata database (%s).", safe_target)
            raise RuntimeError(
                f"PostgreSQL metadata database connection failed ({safe_target}): {redact_database_url(str(exc))}"
            ) from None
    raise RuntimeError(
        "DATABASE_URL is set for PostgreSQL, but neither 'psycopg' nor 'psycopg2' is installed. "
        "Install with: pip install 'psycopg[binary]>=3.2.0'"
    )


def _open_sqlite_connection() -> sqlite3.Connection:
    db_path = settings.DATABASE_PATH
    if db_path and db_path != ":memory:":
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
    except sqlite3.DatabaseError:
        pass
    return conn


def reset_db_connection() -> None:
    """Close and reset thread-local metadata database connection (for tests and backend switches)."""
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
    _local.conn = None
    _local.backend = None
    _local.target = None


def get_db_connection():
    """Return a thread-local metadata database connection (PostgreSQL if DATABASE_URL is set, else SQLite)."""
    desired_backend = get_db_backend()
    desired_target = (settings.DATABASE_URL or "").strip() if desired_backend == "postgresql" else settings.DATABASE_PATH

    if (
        not hasattr(_local, "conn")
        or _local.conn is None
        or getattr(_local, "backend", None) != desired_backend
        or getattr(_local, "target", None) != desired_target
    ):
        reset_db_connection()
        if desired_backend == "postgresql":
            _local.conn = _open_postgres_connection()
        else:
            _local.conn = _open_sqlite_connection()
        _local.backend = desired_backend
        _local.target = desired_target
    else:
        try:
            _local.conn.cursor()
        except Exception:
            reset_db_connection()
            if desired_backend == "postgresql":
                _local.conn = _open_postgres_connection()
            else:
                _local.conn = _open_sqlite_connection()
            _local.backend = desired_backend
            _local.target = desired_target
    return _local.conn


def _get_table_columns(conn, table_name: str) -> List[str]:
    cursor = conn.cursor()
    if getattr(conn, "backend", "sqlite") == "postgresql":
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = ?",
            (table_name,),
        )
        return [r["column_name"] for r in cursor.fetchall()]
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [r[1] for r in cursor.fetchall()]


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    is_pg = getattr(conn, "backend", "sqlite") == "postgresql"
    ts_type = "TEXT" if is_pg else "TIMESTAMP"
    ts_default = "CURRENT_TIMESTAMP::TEXT" if is_pg else "CURRENT_TIMESTAMP"

    cursor.executescript(f"""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        credits INTEGER NOT NULL DEFAULT 100,
        is_admin INTEGER NOT NULL DEFAULT 0,
        created_at {ts_type} DEFAULT {ts_default}
    );

    CREATE TABLE IF NOT EXISTS tokens (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        expires_at {ts_type},
        created_at {ts_type} DEFAULT {ts_default},
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS datasets (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        filename TEXT NOT NULL,
        domain TEXT NOT NULL,
        rows_count INTEGER NOT NULL,
        columns_count INTEGER NOT NULL,
        schema_json TEXT NOT NULL,
        content_summary TEXT NOT NULL,
        content_hash TEXT,
        created_at {ts_type} DEFAULT {ts_default},
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS evaluations (
        id TEXT PRIMARY KEY,
        dataset_id TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        quality_score REAL NOT NULL DEFAULT 0.0,
        schema_fidelity_score REAL NOT NULL DEFAULT 0.0,
        completeness_score REAL NOT NULL DEFAULT 0.0,
        domain_relevance_score REAL NOT NULL DEFAULT 0.0,
        overall_score REAL NOT NULL DEFAULT 0.0,
        credits_awarded INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        created_at {ts_type} DEFAULT {ts_default},
        updated_at {ts_type} DEFAULT {ts_default},
        FOREIGN KEY(dataset_id) REFERENCES datasets(id)
    );

    CREATE TABLE IF NOT EXISTS credit_transactions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        amount INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'completed',
        created_at {ts_type} DEFAULT {ts_default},
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS queries (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        query_text TEXT NOT NULL,
        results_json TEXT NOT NULL,
        dataset_id TEXT,
        dataset_name TEXT,
        generated_sql TEXT,
        execution_time_ms INTEGER DEFAULT 0,
        result_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'SUCCESS',
        credits_charged INTEGER DEFAULT 0,
        error_message TEXT,
        created_at {ts_type} DEFAULT {ts_default},
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS dataset_unlocks (
        id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        unlock_price INTEGER NOT NULL,
        created_at {ts_type} DEFAULT {ts_default},
        UNIQUE(dataset_id, user_id),
        FOREIGN KEY(dataset_id) REFERENCES datasets(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS dataset_versions (
        id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL,
        version TEXT NOT NULL,
        user_id TEXT NOT NULL,
        quality_score REAL NOT NULL,
        relevance_score REAL NOT NULL,
        overall_score REAL NOT NULL,
        delta_score REAL NOT NULL,
        credits_awarded INTEGER NOT NULL,
        changes_summary TEXT NOT NULL,
        created_at {ts_type} DEFAULT {ts_default},
        FOREIGN KEY(dataset_id) REFERENCES datasets(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS admin_audit_logs (
        id TEXT PRIMARY KEY,
        admin_user_id TEXT NOT NULL,
        admin_email TEXT NOT NULL,
        action TEXT NOT NULL,
        target_resource TEXT,
        details TEXT,
        ip_address TEXT,
        created_at {ts_type} DEFAULT {ts_default},
        FOREIGN KEY(admin_user_id) REFERENCES users(id)
    );
    """)

    # Safe column migrations on existing tables
    _run_safe_migrations(conn)
    conn.commit()


def _run_safe_migrations(conn):
    cursor = conn.cursor()
    ts_type = "TEXT" if getattr(conn, "backend", "sqlite") == "postgresql" else "TIMESTAMP"

    # Check users table for reputation_score and is_admin
    user_cols = _get_table_columns(conn, "users")
    if "reputation_score" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN reputation_score INTEGER NOT NULL DEFAULT 50")
    if "is_admin" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    # Check tokens table for expires_at
    token_cols = _get_table_columns(conn, "tokens")
    if "expires_at" not in token_cols:
        cursor.execute(f"ALTER TABLE tokens ADD COLUMN expires_at {ts_type}")

    # Check datasets table for unlock_price, content_hash, visibility, and R2/curated provenance columns
    dataset_cols = _get_table_columns(conn, "datasets")
    if "unlock_price" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN unlock_price INTEGER NOT NULL DEFAULT 10")
    if "content_hash" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN content_hash TEXT")
    if "is_curated" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN is_curated INTEGER NOT NULL DEFAULT 0")
    if "dataset_type" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN dataset_type TEXT NOT NULL DEFAULT 'community'")
    if "source_name" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN source_name TEXT")
    if "source_url" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN source_url TEXT")
    if "license" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN license TEXT")
    if "license_url" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN license_url TEXT")
    if "retrieved_at" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN retrieved_at TEXT")
    if "object_storage_key" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN object_storage_key TEXT")
    if "sha256_checksum" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN sha256_checksum TEXT")
    if "ingestion_status" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN ingestion_status TEXT NOT NULL DEFAULT 'ready'")
    if "source_version" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN source_version TEXT")
    if "csv_bytes" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN csv_bytes INTEGER NOT NULL DEFAULT 0")
    if "visibility" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'")

    # Performance & security indexes (idempotent, non-destructive)
    cursor.executescript("""
        CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_tokens_expires_at ON tokens(expires_at);
        CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON datasets(user_id);
        CREATE INDEX IF NOT EXISTS idx_datasets_user_hash ON datasets(user_id, content_hash);
        CREATE INDEX IF NOT EXISTS idx_datasets_curated_domain ON datasets(is_curated, domain);
        CREATE INDEX IF NOT EXISTS idx_datasets_type ON datasets(dataset_type);
        CREATE INDEX IF NOT EXISTS idx_datasets_visibility ON datasets(visibility);
        CREATE INDEX IF NOT EXISTS idx_queries_user_created ON queries(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_queries_dataset_id ON queries(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_credit_tx_user_created ON credit_transactions(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_logs(created_at);
    """)

    # Check queries table for user-specific query history columns
    query_cols = _get_table_columns(conn, "queries")
    if "dataset_id" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN dataset_id TEXT")
    if "dataset_name" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN dataset_name TEXT")
    if "generated_sql" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN generated_sql TEXT")
    if "execution_time_ms" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN execution_time_ms INTEGER DEFAULT 0")
    if "result_count" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN result_count INTEGER DEFAULT 0")
    if "status" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN status TEXT DEFAULT 'SUCCESS'")
    if "credits_charged" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN credits_charged INTEGER DEFAULT 0")
    if "error_message" not in query_cols:
        cursor.execute("ALTER TABLE queries ADD COLUMN error_message TEXT")

    # Safe backfill for existing queries where generated_sql or dataset_name is NULL
    cursor.execute("SELECT id, results_json, query_text FROM queries WHERE generated_sql IS NULL OR dataset_name IS NULL")
    existing_unmigrated = cursor.fetchall()
    for row in existing_unmigrated:
        qid = row[0]
        r_json_str = row[1]
        sql_val = None
        count_val = 0
        ds_id_val = None
        ds_name_val = "Cross-Catalog"
        status_val = "SUCCESS"
        err_msg = None
        if r_json_str:
            try:
                parsed = json.loads(r_json_str)
                sql_val = parsed.get("sql_query")
                count_val = parsed.get("results_count", 0)
                if "error" in parsed:
                    status_val = parsed.get("status", "SQL_REJECTED")
                    err_msg = parsed.get("error")
                answer_text = parsed.get("answer", "")
                if "Top match: '" in answer_text:
                    try:
                        ds_name_val = answer_text.split("Top match: '")[1].split("'")[0]
                    except Exception:
                        pass
                if sql_val and "dataset_ds_" in sql_val:
                    try:
                        ds_id_val = "ds_" + sql_val.split("dataset_ds_")[1].split(" ")[0].split(";")[0]
                    except Exception:
                        pass
            except Exception:
                pass

        if ds_id_val and ds_name_val == "Cross-Catalog":
            cursor.execute("SELECT name FROM datasets WHERE id = ?", (ds_id_val,))
            ds_row = cursor.fetchone()
            if ds_row:
                ds_name_val = ds_row[0]

        cursor.execute("""
            UPDATE queries
            SET dataset_id = COALESCE(dataset_id, ?),
                dataset_name = COALESCE(dataset_name, ?),
                generated_sql = COALESCE(generated_sql, ?),
                result_count = COALESCE(result_count, ?),
                status = COALESCE(status, ?),
                error_message = COALESCE(error_message, ?)
            WHERE id = ?
        """, (ds_id_val, ds_name_val, sql_val or "-- No SQL generated", count_val, status_val, err_msg, qid))
