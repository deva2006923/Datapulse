import uuid
import json
import datetime
from fastapi import HTTPException, status, Depends
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_user
from app.schemas import QueryRequest, QueryResponse
from app.services.relevance import compute_relevance
from app.config import settings
from app.services.marketplace import (
    check_query_permission_and_cost,
    apply_query_marketplace_transaction,
    InsufficientCreditsError
)
from app.services.storage import (
    get_dataset_table_name,
    dataset_table_exists,
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
    SQLValidationError,
    SQLSecurityError,
    SQLExecutionError
)

router = TrailingSlashRouter(tags=["Query & Analysis"])


@router.post("/query", response_model=QueryResponse)
def execute_query(req: QueryRequest, user: dict = Depends(get_current_user)):
    # 1. Validate query is not empty
    if not req.query or not req.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty"
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    # 2. Dataset Resolution
    if req.dataset_id:
        cursor.execute("SELECT * FROM datasets WHERE id = ?", (req.dataset_id,))
        dataset_row = cursor.fetchone()
        if not dataset_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset '{req.dataset_id}' not found"
            )
        target_dataset = dict(dataset_row)
        matching_names = [target_dataset["name"]]
        relevance_score = 1.0
        datasets = [target_dataset]
    else:
        cursor.execute("SELECT * FROM datasets ORDER BY created_at DESC LIMIT 10")
        datasets = [dict(r) for r in cursor.fetchall()]
        if not datasets:
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
    domain = target_dataset.get("domain", "general")
    owner_id = target_dataset.get("user_id")

    # 3. Credit Verification & Marketplace Cost Determination
    try:
        query_cost, owner_reward, is_own_dataset = check_query_permission_and_cost(
            user_id=user["id"],
            dataset_owner_id=owner_id,
            conn=conn
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e)
        )

    # 4. Verify DuckDB table and schema
    if not dataset_table_exists(dataset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analytical storage table for dataset '{dataset_id}' does not exist"
        )

    columns_with_types = get_dataset_columns(dataset_id)
    if not columns_with_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Schema for dataset '{dataset_id}' is unavailable"
        )

    table_row_count = get_dataset_row_count(dataset_id)
    if table_row_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dataset '{dataset_id}' contains no data rows"
        )

    table_name = get_dataset_table_name(dataset_id)

    # 5. Natural Language -> SQL Generation
    try:
        raw_sql = generate_sql(
            question=req.query,
            table_name=table_name,
            columns_with_types=columns_with_types,
            domain=domain
        )
    except EmptyQueryError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except AIProviderError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"AI SQL generation failed: {str(e)}")

    # 6. SQL Validation & Security Enforcement
    try:
        col_names = [c[0] for c in columns_with_types]
        validated_sql = validate_sql(
            sql=raw_sql,
            allowed_table=table_name,
            allowed_columns=col_names
        )
    except SQLSecurityError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"SQL Security Error: {str(e)}")
    except SQLValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"SQL Validation Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"SQL Validation Error: {str(e)}")

    # 7. Execute validated SQL against DuckDB
    try:
        columns, results, records_analyzed = execute_sql(
            sql=validated_sql,
            dataset_id=dataset_id,
            limit=100
        )
    except SQLExecutionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Database execution error: {str(e)}")

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
            now=now
        )
        cursor.execute("""
            INSERT INTO queries (id, user_id, query_text, results_json, created_at)
            VALUES (?, ?, ?, ?, ?)
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
            now
        ))
        conn.commit()
    except InsufficientCreditsError as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e)
        )
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record marketplace query transaction: {str(e)}"
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
        credits_charged=query_cost
    )
