import os
import re
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple
import duckdb
from app.config import settings

logger = logging.getLogger(__name__)

_duckdb_lock = threading.Lock()
_duckdb_connection: Optional[duckdb.DuckDBPyConnection] = None

DATASET_ID_REGEX = re.compile(r"^ds_[a-zA-Z0-9_-]+$")


def get_dataset_table_name(dataset_id: str) -> str:
    """
    Derive a safe SQL table identifier from a validated dataset_id.
    Ensures no user-controlled characters can be used as raw table names.
    """
    if not dataset_id or not DATASET_ID_REGEX.match(dataset_id):
        raise ValueError(f"Invalid dataset_id format: {dataset_id}")
    safe_suffix = re.sub(r"[^a-zA-Z0-9_]", "_", dataset_id)
    return f"dataset_{safe_suffix}"


def _get_raw_connection() -> duckdb.DuckDBPyConnection:
    """Internal helper to get or initialize the underlying DuckDB connection (must be called with _duckdb_lock)."""
    global _duckdb_connection
    if _duckdb_connection is None:
        db_path = os.path.abspath(settings.DUCKDB_PATH)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _duckdb_connection = duckdb.connect(database=db_path, read_only=False)
        # Initialize internal registry table
        _duckdb_connection.execute("""
            CREATE TABLE IF NOT EXISTS _dataset_registry (
                dataset_id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                table_name VARCHAR NOT NULL,
                filename VARCHAR NOT NULL,
                storage_path VARCHAR NOT NULL,
                rows_count BIGINT NOT NULL,
                columns_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    return _duckdb_connection


def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    """Thread-safe access to a DuckDB cursor for querying."""
    with _duckdb_lock:
        conn = _get_raw_connection()
        return conn.cursor()


def reset_storage_connection() -> None:
    """Close and reset connection (primarily for testing/cleanup)."""
    global _duckdb_connection
    with _duckdb_lock:
        if _duckdb_connection is not None:
            try:
                _duckdb_connection.close()
            except Exception as e:
                logger.warning("Error closing DuckDB connection: %s", e)
            _duckdb_connection = None


def init_storage() -> None:
    """Initialize storage directories and DuckDB registry."""
    os.makedirs(os.path.abspath(settings.DATASETS_STORAGE_DIR), exist_ok=True)
    with _duckdb_lock:
        _get_raw_connection()
    logger.info("Dataset analytical storage initialized at %s", settings.DUCKDB_PATH)


def sanitize_headers(headers: List[str]) -> List[str]:
    """
    Sanitize and deduplicate CSV column headers.
    - Trims whitespace
    - Replaces unsafe characters with underscores
    - Fills empty column names with column_{i+1}
    - Resolves duplicates by appending _{k}
    """
    seen: Dict[str, int] = {}
    cleaned: List[str] = []
    for i, col in enumerate(headers):
        name = col.strip() if col else ""
        if not name:
            name = f"column_{i+1}"
        # Keep alphanumeric, spaces, and underscores; replace others with _
        clean_name = re.sub(r"[^\w\s]", "_", name).strip()
        clean_name = re.sub(r"\s+", "_", clean_name)
        clean_name = re.sub(r"_+", "_", clean_name).strip("_")
        if not clean_name:
            clean_name = f"column_{i+1}"
        lower = clean_name.lower()
        if lower in seen:
            seen[lower] += 1
            unique_name = f"{clean_name}_{seen[lower]}"
        else:
            seen[lower] = 0
            unique_name = clean_name
        cleaned.append(unique_name)
    return cleaned


def persist_dataset(
    dataset_id: str,
    user_id: str,
    filename: str,
    csv_content: str,
    rows_count: int,
    columns_count: int
) -> Dict[str, Any]:
    """
    Persistently store CSV rows to both physical file storage and DuckDB analytical table.
    Atomic and transactional: on any error, cleans up created artifacts.
    """
    table_name = get_dataset_table_name(dataset_id)
    storage_dir = os.path.abspath(settings.DATASETS_STORAGE_DIR)
    os.makedirs(storage_dir, exist_ok=True)
    file_path = os.path.join(storage_dir, f"{dataset_id}.csv")

    # 1. Write CSV content to disk
    try:
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)
    except Exception as e:
        logger.error("Failed to write CSV file for dataset %s: %s", dataset_id, e)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        raise RuntimeError(f"Failed to persist dataset file: {str(e)}")

    # 2. Ingest into DuckDB
    with _duckdb_lock:
        try:
            conn = _get_raw_connection()
            # Drop existing table if re-uploading with same ID (idempotency)
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            # Ingest from the stored CSV
            conn.execute(
                f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto(?, header=True)",
                [file_path]
            )
            # Verify row count in DuckDB
            actual_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            # Record in registry
            conn.execute("DELETE FROM _dataset_registry WHERE dataset_id = ?", [dataset_id])
            conn.execute("""
                INSERT INTO _dataset_registry (dataset_id, user_id, table_name, filename, storage_path, rows_count, columns_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [dataset_id, user_id, table_name, filename, file_path, actual_count, columns_count])

            logger.info("Persisted dataset %s (%d rows) to table %s", dataset_id, actual_count, table_name)
            return {
                "dataset_id": dataset_id,
                "table_name": table_name,
                "rows_count": actual_count,
                "columns_count": columns_count,
                "storage_path": file_path
            }
        except Exception as e:
            logger.error("Failed to ingest dataset %s into DuckDB: %s", dataset_id, e)
            # Cleanup on failure
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
            try:
                conn = _get_raw_connection()
                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                conn.execute("DELETE FROM _dataset_registry WHERE dataset_id = ?", [dataset_id])
            except Exception:
                pass
            raise RuntimeError(f"Analytical storage ingestion failed: {str(e)}")


def delete_dataset_storage(dataset_id: str) -> None:
    """Delete dataset from DuckDB and disk storage."""
    try:
        table_name = get_dataset_table_name(dataset_id)
    except ValueError:
        return

    storage_dir = os.path.abspath(settings.DATASETS_STORAGE_DIR)
    file_path = os.path.join(storage_dir, f"{dataset_id}.csv")

    with _duckdb_lock:
        try:
            conn = _get_raw_connection()
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.execute("DELETE FROM _dataset_registry WHERE dataset_id = ?", [dataset_id])
        except Exception as e:
            logger.warning("Error dropping DuckDB table for %s: %s", dataset_id, e)

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning("Error deleting file %s: %s", file_path, e)


def get_dataset_row_count(dataset_id: str) -> int:
    """Retrieve row count directly from the DuckDB analytical table."""
    table_name = get_dataset_table_name(dataset_id)
    with _duckdb_lock:
        conn = _get_raw_connection()
        res = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(res[0]) if res else 0


def get_dataset_columns(dataset_id: str) -> List[Tuple[str, str]]:
    """Retrieve column names and DuckDB types for a dataset."""
    table_name = get_dataset_table_name(dataset_id)
    with _duckdb_lock:
        conn = _get_raw_connection()
        rows = conn.execute(f"DESCRIBE {table_name}").fetchall()
        return [(str(r[0]), str(r[1])) for r in rows]


def dataset_table_exists(dataset_id: str) -> bool:
    """Check if the DuckDB table exists for a dataset."""
    table_name = get_dataset_table_name(dataset_id)
    with _duckdb_lock:
        conn = _get_raw_connection()
        res = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name]
        ).fetchone()
        return bool(res and res[0] > 0)


def get_dataset_rows(dataset_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Safe parameterized query to fetch rows from a dataset table."""
    table_name = get_dataset_table_name(dataset_id)
    with _duckdb_lock:
        conn = _get_raw_connection()
        cols = [r[0] for r in conn.execute(f"DESCRIBE {table_name}").fetchall()]
        rows = conn.execute(f"SELECT * FROM {table_name} LIMIT ? OFFSET ?", [limit, offset]).fetchall()
        return [dict(zip(cols, row)) for row in rows]
