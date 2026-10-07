import uuid
import json
import datetime
from typing import Optional, List
from fastapi import UploadFile, File, Form, Depends, HTTPException, status, Query
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_user, get_optional_user
from app.schemas import (
    DatasetDetailResponse, DatasetListResponse, EvaluationResponse, 
    SearchRequest, SearchResponse, SearchItem
)
from app.services.evaluation import parse_and_evaluate_csv, run_evaluation_pipeline
from app.services.recommender import recommend_datasets
from app.services.storage import persist_dataset, delete_dataset_storage

router = TrailingSlashRouter(tags=["Datasets"])

@router.post("/datasets/upload", response_model=DatasetDetailResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    domain: str = Form("general"),
    name: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files (.csv) are currently supported"
        )
        
    content_bytes = await file.read()
    csv_content = content_bytes.decode("utf-8", errors="replace")
    
    filename = file.filename
    dataset_name = name or filename.rsplit(".", 1)[0]
    
    # Pre-parse CSV & validate
    eval_check = parse_and_evaluate_csv(csv_content, filename, domain)
    if not eval_check["valid"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=eval_check["error"]
        )
        
    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
    evaluation_id = f"eval_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.utcnow().isoformat()
    cleaned_csv = eval_check.get("cleaned_csv") or csv_content
    
    summary = f"Structured dataset with {eval_check['rows_count']} rows across {eval_check['columns_count']} columns in the {domain} domain."
    schema_json_str = json.dumps(eval_check["schema"])
    
    # 1. Persist actual tabular data in DuckDB and disk storage
    try:
        persist_dataset(
            dataset_id=dataset_id,
            user_id=user["id"],
            filename=filename,
            csv_content=cleaned_csv,
            rows_count=eval_check["rows_count"],
            columns_count=eval_check["columns_count"]
        )
    except Exception as e:
        delete_dataset_storage(dataset_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to persist dataset into analytical storage: {str(e)}"
        )
        
    # 2. Insert metadata into SQLite catalog
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO datasets (id, user_id, name, filename, domain, rows_count, columns_count, schema_json, content_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (dataset_id, user["id"], dataset_name, filename, domain, eval_check["rows_count"], eval_check["columns_count"], schema_json_str, summary, now))
        
        cursor.execute("""
            INSERT INTO evaluations (
                id, dataset_id, status, progress, quality_score, schema_fidelity_score,
                completeness_score, domain_relevance_score, overall_score, credits_awarded,
                error_message, created_at, updated_at
            ) VALUES (?, ?, 'pending', 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, NULL, ?, ?)
        """, (evaluation_id, dataset_id, now, now))
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Clean up storage artifacts on database failure
        delete_dataset_storage(dataset_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register dataset metadata: {str(e)}"
        )
    
    # 3. Execute evaluation pipeline (updates evaluation status and awards credits)
    run_evaluation_pipeline(
        evaluation_id=evaluation_id,
        dataset_id=dataset_id,
        csv_content=cleaned_csv,
        filename=filename,
        domain=domain,
        user_id=user["id"]
    )
    
    return DatasetDetailResponse(
        id=dataset_id,
        user_id=user["id"],
        name=dataset_name,
        filename=filename,
        domain=domain,
        rows_count=eval_check["rows_count"],
        columns_count=eval_check["columns_count"],
        schema_metadata=eval_check["schema"],
        content_summary=summary,
        created_at=now
    )

@router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(domain: Optional[str] = Query(None)):
    conn = get_db_connection()
    cursor = conn.cursor()
    if domain:
        cursor.execute("SELECT * FROM datasets WHERE domain = ? ORDER BY created_at DESC", (domain,))
    else:
        cursor.execute("SELECT * FROM datasets ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    items = []
    for r in rows:
        items.append(DatasetDetailResponse(
            id=r["id"],
            user_id=r["user_id"],
            name=r["name"],
            filename=r["filename"],
            domain=r["domain"],
            rows_count=r["rows_count"],
            columns_count=r["columns_count"],
            schema_metadata=json.loads(r["schema_json"]),
            content_summary=r["content_summary"],
            created_at=r["created_at"]
        ))
    return DatasetListResponse(datasets=items, total=len(items))

@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    r = cursor.fetchone()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
        
    return DatasetDetailResponse(
        id=r["id"],
        user_id=r["user_id"],
        name=r["name"],
        filename=r["filename"],
        domain=r["domain"],
        rows_count=r["rows_count"],
        columns_count=r["columns_count"],
        schema_metadata=json.loads(r["schema_json"]),
        content_summary=r["content_summary"],
        created_at=r["created_at"]
    )

@router.get("/datasets/{dataset_id}/evaluation", response_model=EvaluationResponse)
def get_dataset_evaluation(dataset_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM evaluations WHERE dataset_id = ?", (dataset_id,))
    r = cursor.fetchone()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation record not found for dataset")
        
    return EvaluationResponse(
        id=r["id"],
        dataset_id=r["dataset_id"],
        status=r["status"],
        progress=r["progress"],
        quality_score=r["quality_score"],
        schema_fidelity_score=r["schema_fidelity_score"],
        completeness_score=r["completeness_score"],
        domain_relevance_score=r["domain_relevance_score"],
        overall_score=r["overall_score"],
        credits_awarded=r["credits_awarded"],
        error_message=r["error_message"],
        updated_at=r["updated_at"],
        created_at=r["created_at"]
    )

@router.post("/datasets/search", response_model=SearchResponse)
@router.post("/search", response_model=SearchResponse)
def search_datasets(req: SearchRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if req.domain:
        cursor.execute("SELECT * FROM datasets WHERE domain = ?", (req.domain,))
    else:
        cursor.execute("SELECT * FROM datasets")
    all_datasets = [dict(row) for row in cursor.fetchall()]
    
    ranked, method = recommend_datasets(req.query, all_datasets, limit=req.limit)
    
    items = [
        SearchItem(
            dataset_id=d["id"],
            name=d["name"],
            domain=d["domain"],
            score=d["score"],
            summary=d["content_summary"],
            rows_count=d["rows_count"]
        ) for d in ranked
    ]
    return SearchResponse(query=req.query, results=items, total=len(items), method=method)

@router.get("/datasets/search", response_model=SearchResponse)
def search_datasets_get(q: str = Query(..., min_length=1), domain: Optional[str] = Query(None), limit: int = Query(10, ge=1, le=100)):
    req = SearchRequest(query=q, domain=domain, limit=limit)
    return search_datasets(req)
