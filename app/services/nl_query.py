import re
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
import sqlparse
import duckdb

from app.config import settings
from app.services.storage import (
    get_dataset_table_name,
    get_duckdb_connection,
    dataset_table_exists,
    get_dataset_columns,
    get_dataset_row_count
)

logger = logging.getLogger(__name__)


# Custom Domain Exceptions
class EmptyQueryError(Exception):
    """Raised when the natural language query is empty."""
    pass


class DatasetNotFoundError(Exception):
    """Raised when the specified dataset is not found."""
    pass


class DatasetEmptyError(Exception):
    """Raised when the dataset has no records to query."""
    pass


class AIProviderError(Exception):
    """Raised when the AI provider is unavailable or fails."""
    pass


class SQLValidationError(Exception):
    """Raised when generated SQL fails syntax, column, or structural validation."""
    pass


class SQLSecurityError(SQLValidationError):
    """Raised when generated SQL attempts unauthorized or destructive operations."""
    pass


class SQLExecutionError(Exception):
    """Raised when DuckDB execution fails."""
    pass


# Optional custom AI generator hook (primarily for testing and mocking)
_mock_ai_generator: Optional[Callable[[str, str, List[Tuple[str, str]]], str]] = None


def set_ai_generator(generator: Optional[Callable[[str, str, List[Tuple[str, str]]], str]]) -> None:
    """Set or clear a custom AI generator hook."""
    global _mock_ai_generator
    _mock_ai_generator = generator


# Forbidden keywords, DDL/DML operations, and dangerous built-ins
FORBIDDEN_OPERATIONS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH",
    "COPY", "INSTALL", "LOAD", "PRAGMA", "EXPORT", "CALL", "EXEC", "EXECUTE",
    "TRUNCATE", "REPLACE", "MERGE", "GRANT", "REVOKE", "VACUUM", "CHECKPOINT",
    "FORCE"
]

FORBIDDEN_FUNCTIONS = [
    "read_csv", "read_parquet", "read_json", "read_ndjson", "scan_parquet",
    "glob", "httpfs", "postgres_scan", "sqlite_scan", "mysql_scan",
    "duckdb_tables", "duckdb_views", "duckdb_schemas", "sqlite_master",
    "sqlite_schema", "information_schema"
]


def clean_markdown_sql(raw_sql: str) -> str:
    """Strip markdown codeblock wrappers and trailing whitespace from LLM output."""
    if not raw_sql:
        return ""
    text = raw_sql.strip()
    # Remove ```sql ... ``` or ``` ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
        elif len(lines) >= 1:
            text = "\n".join(lines[1:]).rstrip("`").strip()
    return text.strip()


def validate_sql(
    sql: str,
    allowed_table: str,
    allowed_columns: Optional[List[str]] = None
) -> str:
    """
    Validate and sanitize generated SQL query.
    Enforces:
    - Single statement only
    - No comments (-- or /* */)
    - SELECT or WITH ... SELECT only
    - No destructive or administrative operations
    - No filesystem, external, or internal functions
    - Strict table whitelist: only allowed_table may be referenced
    - Schema column validation via DuckDB EXPLAIN
    """
    cleaned = clean_markdown_sql(sql)
    if not cleaned:
        raise SQLValidationError("Generated SQL query is empty")

    # 1. Reject SQL comments (prevent validation evasion)
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLSecurityError("SQL comments are not permitted in queries")

    # 2. Reject multiple statements
    stripped_end = cleaned.rstrip().rstrip(";")
    if ";" in stripped_end:
        raise SQLSecurityError("Multiple SQL statements are not permitted")

    parsed = sqlparse.parse(cleaned)
    if len(parsed) != 1:
        raise SQLSecurityError("Multiple SQL statements are not permitted")

    # 3. Must start with SELECT or WITH
    first_token = None
    for token in parsed[0].tokens:
        if not token.is_whitespace:
            first_token = token.value.upper()
            break

    if first_token not in ("SELECT", "WITH"):
        raise SQLSecurityError("Only SELECT or WITH ... SELECT queries are permitted")

    # 4. Keyword and Operation Blacklist
    for op in FORBIDDEN_OPERATIONS:
        pattern = rf"\b{re.escape(op)}\b"
        if re.search(pattern, cleaned, re.IGNORECASE):
            raise SQLSecurityError(f"Forbidden SQL operation or keyword detected: {op}")

    # 5. Dangerous functions and internal tables
    for fn in FORBIDDEN_FUNCTIONS:
        pattern = rf"\b{re.escape(fn)}\b"
        if re.search(pattern, cleaned, re.IGNORECASE):
            raise SQLSecurityError(f"Forbidden function or table access detected: {fn}")

    # 6. Strict Table Whitelist: must ONLY reference allowed_table
    # Extract table names from FROM and JOIN clauses
    table_patterns = [
        r"\bFROM\s+([a-zA-Z0-9_\"]+)",
        r"\bJOIN\s+([a-zA-Z0-9_\"]+)"
    ]
    referenced_tables = set()
    for pat in table_patterns:
        for match in re.finditer(pat, cleaned, re.IGNORECASE):
            tbl = match.group(1).strip("\"'`")
            referenced_tables.add(tbl.lower())

    # Check for multiple comma-separated tables in FROM clause
    # e.g., FROM table1, table2
    from_match = re.search(r"\bFROM\s+([a-zA-Z0-9_\",\s]+?)(?:\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)", cleaned, re.IGNORECASE)
    if from_match:
        from_part = from_match.group(1)
        for part in from_part.split(","):
            tbl_candidate = part.strip().split()[0].strip("\"'`") if part.strip() else ""
            if tbl_candidate and tbl_candidate.upper() not in ("SELECT", "WHERE", "JOIN"):
                referenced_tables.add(tbl_candidate.lower())

    if not referenced_tables:
        raise SQLSecurityError(f"Query must reference table '{allowed_table}'")

    for tbl in referenced_tables:
        if tbl != allowed_table.lower():
            raise SQLSecurityError(f"Query references unauthorized table '{tbl}'. Only '{allowed_table}' is permitted.")

    # 7. Semantic & Binder Validation using DuckDB EXPLAIN
    try:
        conn = get_duckdb_connection()
        conn.execute(f"EXPLAIN {cleaned}")
    except duckdb.BinderException as e:
        err_msg = str(e)
        if "Referenced column" in err_msg or "Column" in err_msg:
            raise SQLValidationError(f"Unknown or invalid column in query: {err_msg}")
        raise SQLValidationError(f"Semantic validation error: {err_msg}")
    except duckdb.CatalogException as e:
        raise SQLSecurityError(f"Unknown or unauthorized catalog reference: {str(e)}")
    except duckdb.ParserException as e:
        raise SQLValidationError(f"Invalid SQL syntax: {str(e)}")
    except Exception as e:
        raise SQLValidationError(f"SQL validation failed: {str(e)}")

    return cleaned


def fallback_rule_sql_generator(
    question: str,
    table_name: str,
    columns_with_types: List[Tuple[str, str]]
) -> Optional[str]:
    """Lightweight fallback generator for basic questions when no AI API key is configured."""
    q = question.lower().strip()
    if any(w in q for w in ("how many", "count", "number of rows", "total rows")):
        return f"SELECT COUNT(*) AS total_count FROM {table_name}"
    if any(w in q for w in ("what items", "show items", "list items", "catalog", "items in")):
        return f"SELECT * FROM {table_name} LIMIT 10"
    return None


def generate_sql(
    question: str,
    table_name: str,
    columns_with_types: List[Tuple[str, str]],
    domain: str = "general"
) -> str:
    """
    Generate DuckDB SQL from natural language using the configured AI provider.
    Supports Google Gemini (via google-genai) and fallback/mock generators.
    """
    if not question or not question.strip():
        raise EmptyQueryError("Natural language question cannot be empty")

    # If mock generator is set (in tests), use it directly
    if _mock_ai_generator is not None:
        return _mock_ai_generator(question, table_name, columns_with_types)

    provider = (settings.AI_PROVIDER or "gemini").lower()
    columns_desc = "\n".join([f"- {col}: {col_type}" for col, col_type in columns_with_types])

    system_prompt = (
        f"You are a DuckDB SQL generator for the DataPulse analytical engine.\n"
        f"Your task is to translate the user's natural language question into exactly one read-only DuckDB SQL query.\n\n"
        f"TARGET DATABASE: DuckDB\n"
        f"DATASET DOMAIN: {domain}\n"
        f"ALLOWED TABLE: {table_name}\n"
        f"AVAILABLE COLUMNS AND TYPES:\n{columns_desc}\n\n"
        f"STRICT RULES:\n"
        f"1. Generate exactly ONE read-only SELECT statement (or WITH ... SELECT).\n"
        f"2. You may ONLY query the table '{table_name}'. Do NOT query any other table or file.\n"
        f"3. You may ONLY use the columns listed above. Do not invent columns.\n"
        f"4. For string matching, use ILIKE for case-insensitive matching.\n"
        f"5. For aggregations and rankings, use standard SQL functions: COUNT(), SUM(), AVG(), MIN(), MAX(), ORDER BY, LIMIT.\n"
        f"6. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, ATTACH, DETACH, COPY, INSTALL, LOAD, PRAGMA, EXPORT, or CALL.\n"
        f"7. Return ONLY the raw SQL string without markdown codeblocks or commentary."
    )

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            fallback = fallback_rule_sql_generator(question, table_name, columns_with_types)
            if fallback:
                return fallback
            raise AIProviderError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in environment variables."
            )
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            model_name = settings.GEMINI_MODEL or "gemini-2.5-flash"
            prompt = f"{system_prompt}\n\nUSER QUESTION: {question}\n\nSQL:"
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            raw_sql = response.text if response and hasattr(response, "text") else ""
            if not raw_sql:
                raise AIProviderError("AI provider returned an empty response")
            return clean_markdown_sql(raw_sql)
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            logger.error("Error invoking Gemini model: %s", e)
            raise AIProviderError(f"AI provider generation failed: {str(e)}")

    raise AIProviderError(f"Unsupported AI provider: '{provider}'")


def execute_sql(sql: str, dataset_id: str, limit: int = 100) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """
    Execute validated SQL query against DuckDB and return column names, row dictionaries, and records analyzed.
    """
    # Enforce default safety limit if query has no LIMIT clause
    executable_sql = sql
    if not re.search(r"\bLIMIT\s+\d+\b", executable_sql, re.IGNORECASE):
        executable_sql = f"{executable_sql} LIMIT {limit}"

    try:
        conn = get_duckdb_connection()
        res = conn.execute(executable_sql)
        columns = [desc[0] for desc in res.description] if res.description else []
        rows = res.fetchall()

        # Convert values to JSON-serializable types
        clean_rows = []
        for row in rows[:limit]:
            clean_row = {}
            for col_name, val in zip(columns, row):
                if hasattr(val, "isoformat"):
                    clean_row[col_name] = val.isoformat()
                elif hasattr(val, "__float__") and not isinstance(val, (int, float, bool)):
                    clean_row[col_name] = float(val)
                else:
                    clean_row[col_name] = val
            clean_rows.append(clean_row)

        records_analyzed = get_dataset_row_count(dataset_id)
        return columns, clean_rows, records_analyzed
    except Exception as e:
        logger.error("DuckDB execution failure: %s", e)
        raise SQLExecutionError(f"Database execution failed: {str(e)}")


def synthesize_answer(
    question: str,
    sql: str,
    columns: List[str],
    results: List[Dict[str, Any]],
    dataset_name: str
) -> str:
    """
    Generate a human-readable answer strictly grounded in actual SQL results.
    Never invents values.
    """
    if not results:
        return f"The query yielded no matching records in dataset '{dataset_name}'."

    num_rows = len(results)

    # Case 1: Single scalar value (e.g. COUNT, SUM, AVG, MIN, MAX)
    if num_rows == 1 and len(columns) == 1:
        col = columns[0]
        val = results[0][col]
        formatted_val = f"{val:,}" if isinstance(val, (int, float)) and not isinstance(val, bool) else str(val)
        return f"For query '{question}', the calculated {col} is {formatted_val}."

    # Case 2: Single row with 2-3 columns (e.g., top product and its sales)
    if num_rows == 1:
        details = ", ".join([f"{c}: {results[0][c]}" for c in columns])
        return f"Result for '{question}': {details}."

    # Case 3: Multiple rows (e.g., top N items)
    first_item_summary = ", ".join([f"{c}: {results[0][c]}" for c in columns[:2]])
    return (
        f"Found {num_rows} record(s) for '{question}'. "
        f"Top result: {first_item_summary}."
    )
