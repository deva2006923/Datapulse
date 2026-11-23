import uuid
import json
import time
import logging
import datetime
from typing import Optional, List, Any
from fastapi import HTTPException, status, Depends, Query
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_user
from app.services.admin_bootstrap import is_admin_email
from app.schemas import (
    QueryRequest,
    QueryResponse,
    QueryHistoryItem,
    QueryHistoryResponse
)
from app.services.relevance import compute_relevance
from app.config import settings
from app.services.marketplace import (
    check_query_permission_and_cost,
    apply_query_marketplace_transaction,
    InsufficientCreditsError
)
from app.services.curated_library import (
    ensure_curated_dataset_hydrated,
    ensure_community_dataset_hydrated,
    has_packaged_curated_csv,
    CuratedHydrationError,
)
from app.services.storage import (
    get_dataset_table_name,
    dataset_table_exists,
    get_existing_dataset_ids,
    get_dataset_columns,
    get_dataset_row_count
)
from app.services.nl_query import (
    generate_sql,
    validate_sql,
    execute_sql,
    synthesize_answer,
    EmptyQueryError,
    DatasetNotFoundError,
    DatasetEmptyError,
    AIProviderError,
    AIProviderRateLimitError,
    AI_QUOTA_USER_MESSAGE,
    AI_UNAVAILABLE_USER_MESSAGE,
    SQLValidationError,
    SQLSecurityError,
    SQLExecutionError,
    _redact_secrets,
)

logger = logging.getLogger("datapulse.query")
router = TrailingSlashRouter(tags=["Query & Analysis"])


def _log_query_record(
    conn,
    user_id: str,
    query_text: str,
    dataset_id: Optional[str],
    dataset_name: Optional[str],
    generated_sql: Optional[str],
    execution_time_ms: int,
    result_count: int,
    status_str: str,
    credits_charged: int,
    results_json_dict: dict,
    error_message: Optional[str] = None
) -> str:
    """Safely logs a query execution (successful or failed) associated with the authenticated user."""
    query_id = f"qry_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.utcnow().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO queries (
            id, user_id, query_text, results_json, dataset_id, dataset_name,
            generated_sql, execution_time_ms, result_count, status,
            credits_charged, error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        query_id,
        user_id,
        query_text,
        json.dumps(results_json_dict),
        dataset_id,
        dataset_name,
        generated_sql,
        execution_time_ms,
        result_count,
        status_str,
        credits_charged,
        error_message,
        now
    ))
    return query_id


@router.post("/query", response_model=QueryResponse)
def execute_query(req: QueryRequest, user: dict = Depends(get_current_user)):
    start_time = time.perf_counter()

    # 1. Validate query is not empty
    if not req.query or not req.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty"
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    target_dataset = None
    target_dataset_id = req.dataset_id
    target_dataset_name = "Cross-Catalog"

    # 2. Dataset Resolution
    if req.dataset_id:
        cursor.execute("SELECT * FROM datasets WHERE id = ?", (req.dataset_id,))
        dataset_row = cursor.fetchone()
        if not dataset_row:
            exec_ms = int((time.perf_counter() - start_time) * 1000)
            _log_query_record(
                conn=conn,
                user_id=user["id"],
                query_text=req.query,
                dataset_id=req.dataset_id,
                dataset_name="Unknown Dataset",
                generated_sql="-- Failed: Dataset not found",
                execution_time_ms=exec_ms,
                result_count=0,
                status_str="SQL_REJECTED",
                credits_charged=0,
                results_json_dict={"error": f"Dataset '{req.dataset_id}' not found", "status": "SQL_REJECTED"},
                error_message=f"Dataset '{req.dataset_id}' not found"
            )
            conn.commit()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset '{req.dataset_id}' not found"
            )
        target_dataset = dict(dataset_row)
        ds_visibility = (target_dataset.get("visibility") or "public").strip().lower()
        is_verified_admin = bool(user.get("is_admin")) and is_admin_email(user.get("email", ""))
        if ds_visibility == "private" and target_dataset.get("user_id") != user["id"] and not is_verified_admin:
            exec_ms = int((time.perf_counter() - start_time) * 1000)
            _log_query_record(
                conn=conn,
                user_id=user["id"],
                query_text=req.query,
                dataset_id=req.dataset_id,
                dataset_name="Private Dataset",
                generated_sql="-- Failed: Private dataset access denied",
                execution_time_ms=exec_ms,
                result_count=0,
                status_str="SQL_REJECTED",
                credits_charged=0,
                results_json_dict={"error": "Access denied to private dataset", "status": "FORBIDDEN"},
                error_message="Access denied to private dataset",
            )
            conn.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: this dataset is private and only accessible to its owner or a platform administrator.",
            )
        matching_names = [target_dataset["name"]]
        relevance_score = 1.0
        datasets = [target_dataset]
    else:
        is_verified_admin = bool(user.get("is_admin")) and is_admin_email(user.get("email", ""))
        if is_verified_admin:
            cursor.execute(
                """
                SELECT * FROM datasets
                WHERE NOT (COALESCE(is_curated, 0) = 1 AND LOWER(COALESCE(ingestion_status, 'ready')) != 'ingested')
                ORDER BY created_at DESC
                """
            )
        else:
            cursor.execute(
                """
                SELECT * FROM datasets
                WHERE NOT (COALESCE(is_curated, 0) = 1 AND LOWER(COALESCE(ingestion_status, 'ready')) != 'ingested')
                  AND (LOWER(COALESCE(visibility, 'public')) != 'private' OR user_id = ?)
                ORDER BY created_at DESC
                """,
                (user["id"],),
            )
        all_datasets = [dict(r) for r in cursor.fetchall()]
        existing_tables = get_existing_dataset_ids()
        available_datasets = [
            d for d in all_datasets
            if d["id"] in existing_tables
            or (
                bool(d.get("is_curated"))
                and str(d.get("ingestion_status") or "").strip().lower() == "ingested"
                and bool((d.get("sha256_checksum") or "").strip())
                and (has_packaged_curated_csv(d["id"]) or bool((d.get("object_storage_key") or "").strip()))
            )
            or (
                not bool(d.get("is_curated"))
                and bool((d.get("object_storage_key") or "").strip())
                and bool((d.get("sha256_checksum") or "").strip())
            )
        ]
        datasets = available_datasets if available_datasets else all_datasets
        if not datasets:
            exec_ms = int((time.perf_counter() - start_time) * 1000)
            _log_query_record(
                conn=conn,
                user_id=user["id"],
                query_text=req.query,
                dataset_id=None,
                dataset_name="Cross-Catalog",
                generated_sql="-- No datasets in catalog",
                execution_time_ms=exec_ms,
                result_count=0,
                status_str="SUCCESS",
                credits_charged=0,
                results_json_dict={"answer": "No relevant datasets found in the catalog.", "score": 0.0}
            )
            conn.commit()
            return QueryResponse(
                query=req.query,
                answer="No relevant datasets found in the catalog to answer your query. Upload structured datasets to start querying.",
                matching_datasets=[],
                records_analyzed=0,
                relevance_score=0.0,
                method="rule_fallback" if not settings.EMBEDDINGS_ENABLED else "embeddings",
                sql_query=None,
                columns=None,
                results=None
            )

        best_dataset = None
        best_score = -1.0
        matching_names = []

        for d in datasets:
            matching_names.append(d["name"])
            doc_text = f"{d['name']} {d['domain']} {d['content_summary']} {d['schema_json']}"
            score = compute_relevance(req.query, doc_text, domain=d["domain"])
            if score > best_score:
                best_score = score
                best_dataset = d

        relevance_score = round(max(0.0, min(1.0, best_score)), 4)
        target_dataset = best_dataset

    dataset_id = target_dataset["id"]
    target_dataset_id = dataset_id
    target_dataset_name = target_dataset.get("name", "Unknown Dataset")
    domain = target_dataset.get("domain", "general")
    owner_id = target_dataset.get("user_id")
    is_curated = bool(target_dataset.get("is_curated"))

    # 3. Credit Verification & Marketplace Cost Determination
    try:
        query_cost, owner_reward, is_own_dataset = check_query_permission_and_cost(
            user_id=user["id"],
            dataset_owner_id=owner_id,
            conn=conn,
            is_curated=is_curated,
        )
    except InsufficientCreditsError as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql="-- Failed: Insufficient credits",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="INSUFFICIENT_CREDITS",
            credits_charged=0,
            results_json_dict={"error": str(e), "status": "INSUFFICIENT_CREDITS"},
            error_message=str(e)
        )
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e)
        )

    # 3b. On-Demand DuckDB Hydration for Curated Public Datasets (verifies SHA-256 & LRU cache)
    #     and automatic R2 restoration for cloud-backed Community datasets after ephemeral restarts
    if is_curated:
        try:
            ensure_curated_dataset_hydrated(target_dataset)
        except CuratedHydrationError as e:
            exec_ms = int((time.perf_counter() - start_time) * 1000)
            _log_query_record(
                conn=conn,
                user_id=user["id"],
                query_text=req.query,
                dataset_id=dataset_id,
                dataset_name=target_dataset_name,
                generated_sql="-- Failed: Curated dataset hydration unavailable",
                execution_time_ms=exec_ms,
                result_count=0,
                status_str="SQL_REJECTED",
                credits_charged=0,
                results_json_dict={"error": str(e), "status": "HYDRATION_FAILED"},
                error_message=str(e)
            )
            conn.commit()
            raise HTTPException(
                status_code=e.status_code,
                detail=str(e)
            )
    elif (
        not dataset_table_exists(dataset_id)
        and target_dataset.get("object_storage_key")
        and target_dataset.get("sha256_checksum")
    ):
        try:
            ensure_community_dataset_hydrated(target_dataset)
        except CuratedHydrationError as e:
            exec_ms = int((time.perf_counter() - start_time) * 1000)
            _log_query_record(
                conn=conn,
                user_id=user["id"],
                query_text=req.query,
                dataset_id=dataset_id,
                dataset_name=target_dataset_name,
                generated_sql="-- Failed: Community dataset cloud restoration unavailable",
                execution_time_ms=exec_ms,
                result_count=0,
                status_str="SQL_REJECTED",
                credits_charged=0,
                results_json_dict={"error": str(e), "status": "HYDRATION_FAILED"},
                error_message=str(e)
            )
            conn.commit()
            raise HTTPException(
                status_code=e.status_code,
                detail=str(e)
            )

    # 4. Verify DuckDB table and schema
    if not dataset_table_exists(dataset_id):
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql="-- Failed: Analytical storage table missing",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": f"Analytical storage table for dataset '{dataset_id}' does not exist"},
            error_message=f"Analytical storage table for dataset '{dataset_id}' does not exist"
        )
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analytical storage table for dataset '{dataset_id}' does not exist"
        )

    columns_with_types = get_dataset_columns(dataset_id)
    if not columns_with_types:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql="-- Failed: Schema unavailable",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": f"Schema for dataset '{dataset_id}' is unavailable"},
            error_message=f"Schema for dataset '{dataset_id}' is unavailable"
        )
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Schema for dataset '{dataset_id}' is unavailable"
        )

    table_row_count = get_dataset_row_count(dataset_id)
    if table_row_count == 0:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql="-- Failed: Dataset contains no data rows",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": f"Dataset '{dataset_id}' contains no data rows"},
            error_message=f"Dataset '{dataset_id}' contains no data rows"
        )
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dataset '{dataset_id}' contains no data rows"
        )

    table_name = get_dataset_table_name(dataset_id)

    # 5. Natural Language -> SQL Generation
    raw_sql = None
    try:
        raw_sql = generate_sql(
            question=req.query,
            table_name=table_name,
            columns_with_types=columns_with_types,
            domain=domain
        )
    except EmptyQueryError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except AIProviderRateLimitError as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        safe_detail = e.user_message or AI_QUOTA_USER_MESSAGE
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql="-- Failed: AI Provider Rate Limit",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": safe_detail, "status": "AI_PROVIDER_RATE_LIMITED"},
            error_message=safe_detail,
        )
        conn.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=safe_detail)
    except AIProviderError as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        safe_detail = getattr(e, "user_message", None) or str(e)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql="-- Failed: AI Provider Error",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": safe_detail, "status": "SQL_REJECTED"},
            error_message=safe_detail,
        )
        conn.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=safe_detail)
    except Exception as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(
            "Unexpected AI SQL generation failure for dataset=%s user=%s: %s",
            dataset_id,
            user["id"],
            _redact_secrets(str(e)),
        )
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql="-- Failed: AI SQL generation error",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": AI_UNAVAILABLE_USER_MESSAGE, "status": "SQL_REJECTED"},
            error_message=AI_UNAVAILABLE_USER_MESSAGE,
        )
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=AI_UNAVAILABLE_USER_MESSAGE,
        )

    # 6. SQL Validation & Security Enforcement
    try:
        col_names = [c[0] for c in columns_with_types]
        validated_sql = validate_sql(
            sql=raw_sql,
            allowed_table=table_name,
            allowed_columns=col_names
        )
    except SQLSecurityError as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql=raw_sql or "-- Rejected SQL",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": str(e), "status": "SQL_REJECTED", "sql_query": raw_sql},
            error_message=str(e)
        )
        conn.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"SQL Security Error: {str(e)}")
    except SQLValidationError as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql=raw_sql or "-- Rejected SQL",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": str(e), "status": "SQL_REJECTED", "sql_query": raw_sql},
            error_message=str(e)
        )
        conn.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"SQL Validation Error: {str(e)}")
    except Exception as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql=raw_sql or "-- Rejected SQL",
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": str(e), "status": "SQL_REJECTED", "sql_query": raw_sql},
            error_message=str(e)
        )
        conn.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"SQL Validation Error: {str(e)}")

    # 7. Execute validated SQL against DuckDB
    try:
        columns, results, records_analyzed = execute_sql(
            sql=validated_sql,
            dataset_id=dataset_id,
            limit=100
        )
    except (SQLExecutionError, Exception) as e:
        exec_ms = int((time.perf_counter() - start_time) * 1000)
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset_name,
            generated_sql=validated_sql,
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="SQL_REJECTED",
            credits_charged=0,
            results_json_dict={"error": str(e), "status": "SQL_REJECTED", "sql_query": validated_sql},
            error_message=str(e)
        )
        conn.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    # 8. Generate human-readable answer grounded in actual results
    answer = synthesize_answer(
        question=req.query,
        sql=validated_sql,
        columns=columns,
        results=results,
        dataset_name=target_dataset["name"]
    )

    # 9. Atomically process marketplace credit transaction and log query in catalog
    query_id = f"qry_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.utcnow().isoformat()
    exec_ms = int((time.perf_counter() - start_time) * 1000)

    try:
        apply_query_marketplace_transaction(
            conn=conn,
            querying_user_id=user["id"],
            dataset_owner_id=owner_id,
            dataset_id=dataset_id,
            dataset_name=target_dataset["name"],
            query_id=query_id,
            query_cost=query_cost,
            owner_reward=owner_reward,
            is_own_dataset=is_own_dataset,
            now=now,
            is_curated=is_curated,
        )
        cursor.execute("""
            INSERT INTO queries (
                id, user_id, query_text, results_json, dataset_id, dataset_name,
                generated_sql, execution_time_ms, result_count, status,
                credits_charged, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            query_id,
            user["id"],
            req.query,
            json.dumps({
                "answer": answer,
                "sql_query": validated_sql,
                "results_count": len(results),
                "score": relevance_score
            }),
            dataset_id,
            target_dataset["name"],
            validated_sql,
            exec_ms,
            len(results),
            "SUCCESS",
            query_cost,
            None,
            now
        ))
        conn.commit()
    except InsufficientCreditsError as e:
        conn.rollback()
        _log_query_record(
            conn=conn,
            user_id=user["id"],
            query_text=req.query,
            dataset_id=dataset_id,
            dataset_name=target_dataset["name"],
            generated_sql=validated_sql,
            execution_time_ms=exec_ms,
            result_count=0,
            status_str="INSUFFICIENT_CREDITS",
            credits_charged=0,
            results_json_dict={"error": str(e), "status": "INSUFFICIENT_CREDITS"},
            error_message=str(e)
        )
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e)
        )
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record marketplace query transaction."
        )

    return QueryResponse(
        query=req.query,
        answer=answer,
        matching_datasets=matching_names[:3],
        records_analyzed=records_analyzed,
        relevance_score=relevance_score,
        method="nl_to_sql",
        sql_query=validated_sql,
        columns=columns,
        results=results,
        credits_charged=query_cost,
        dataset_id=dataset_id,
        dataset_name=target_dataset["name"]
    )


@router.get("/query/history", response_model=QueryHistoryResponse)
@router.get("/queries/history", response_model=QueryHistoryResponse, include_in_schema=False)
@router.get("/history", response_model=QueryHistoryResponse, include_in_schema=False)
def get_query_history(
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, SQL_REJECTED, INSUFFICIENT_CREDITS, All)"),
    search: Optional[str] = Query(None, description="Search term for prompt, dataset name, or SQL"),
    user_id: Optional[str] = Query(None, description="Ignored: caller cannot access another user's history"),
    user: dict = Depends(get_current_user)
):
    """
    Returns the authenticated user's isolated query history.
    Strictly filters records by the backend authenticated user ID.
    Supports search, status filtering, pagination, and orders newest queries first.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # CRITICAL: Always use authenticated user's ID from get_current_user. Never trust user_id query parameter.
    authenticated_user_id = user["id"]

    base_query = "FROM queries WHERE user_id = ?"
    params: List[Any] = [authenticated_user_id]

    if status and status.strip() and status.strip().upper() != "ALL":
        base_query += " AND UPPER(status) = ?"
        params.append(status.strip().upper())

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        base_query += " AND (LOWER(query_text) LIKE ? OR LOWER(COALESCE(generated_sql, '')) LIKE ? OR LOWER(COALESCE(dataset_name, '')) LIKE ?)"
        params.extend([term, term, term])

    # Count total matching queries for this authenticated user
    cursor.execute(f"SELECT COUNT(*) AS total {base_query}", params)
    count_row = cursor.fetchone()
    total = count_row["total"] if count_row else 0

    # Retrieve paginated items, newest first
    offset = (page - 1) * limit
    data_query = f"""
        SELECT id, user_id, dataset_id, dataset_name, query_text, generated_sql,
               execution_time_ms, result_count, status, credits_charged, error_message, created_at
        {base_query}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
    """
    data_params = list(params) + [limit, offset]
    cursor.execute(data_query, data_params)
    rows = cursor.fetchall()

    items = []
    for r in rows:
        items.append(QueryHistoryItem(
            id=r["id"],
            user_id=r["user_id"],
            dataset_id=r["dataset_id"],
            dataset_name=r["dataset_name"] or "Cross-Catalog",
            natural_prompt=r["query_text"],
            generated_sql=r["generated_sql"] or "-- No SQL generated",
            rows_returned=r["result_count"] or 0,
            execution_time_ms=r["execution_time_ms"] or 0,
            status=r["status"] or "SUCCESS",
            credits_charged=r["credits_charged"] or 0,
            timestamp=r["created_at"],
            error_message=r["error_message"]
        ))

    has_more = (offset + len(items)) < total

    return QueryHistoryResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more
    )
