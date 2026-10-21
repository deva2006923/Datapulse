import sqlite3
import json
import threading
from typing import Optional, Dict, Any, List
from app.config import settings

_local = threading.local()

def get_db_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(settings.DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    else:
        try:
            _local.conn.cursor()
        except sqlite3.ProgrammingError:
            conn = sqlite3.connect(settings.DATABASE_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _local.conn = conn
    return _local.conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        credits INTEGER NOT NULL DEFAULT 100,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tokens (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dataset_id) REFERENCES datasets(id)
    );

    CREATE TABLE IF NOT EXISTS credit_transactions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        amount INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'completed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS dataset_unlocks (
        id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        unlock_price INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dataset_id) REFERENCES datasets(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # Safe column migrations on existing tables
    _run_safe_migrations(conn)
    conn.commit()

def _run_safe_migrations(conn: sqlite3.Connection):
    cursor = conn.cursor()
    # Check users table for reputation_score
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [r[1] for r in cursor.fetchall()]
    if "reputation_score" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN reputation_score INTEGER NOT NULL DEFAULT 50")

    # Check datasets table for unlock_price
    cursor.execute("PRAGMA table_info(datasets)")
    dataset_cols = [r[1] for r in cursor.fetchall()]
    if "unlock_price" not in dataset_cols:
        cursor.execute("ALTER TABLE datasets ADD COLUMN unlock_price INTEGER NOT NULL DEFAULT 10")

    # Check queries table for user-specific query history columns
    cursor.execute("PRAGMA table_info(queries)")
    query_cols = [r[1] for r in cursor.fetchall()]
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

