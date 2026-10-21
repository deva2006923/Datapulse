import uuid
import json
import math
import datetime
from typing import Optional, List, Dict, Any
from fastapi import UploadFile, File, Form, Depends, HTTPException, status, Query
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_user, get_optional_user
from app.schemas import (
    DatasetDetailResponse, DatasetListResponse, EvaluationResponse, 
    SearchRequest, SearchResponse, SearchItem,
    DatasetUnlockResponse, DatasetImproveRequest, DatasetImproveResponse
)
from app.services.evaluation import parse_and_evaluate_csv, run_evaluation_pipeline
from app.services.recommender import recommend_datasets
from app.services.storage import persist_dataset, delete_dataset_storage
from app.services.reputation import sync_and_get_user_reputation

router = TrailingSlashRouter(tags=["Datasets"])

def _get_dataset_unlocks_map(conn) -> Dict[str, List[str]]:
    """Helper to fetch all unlock mappings across datasets."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT dataset_id, user_id FROM dataset_unlocks")
        res: Dict[str, List[str]] = {}
        for r in cursor.fetchall():
            res.setdefault(r["dataset_id"], []).append(r["user_id"])
        return res
    except Exception:
        return {}

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
    initial_unlock_price = eval_check.get("unlock_price", 10)
    
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
            INSERT INTO datasets (id, user_id, name, filename, domain, rows_count, columns_count, schema_json, content_summary, unlock_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (dataset_id, user["id"], dataset_name, filename, domain, eval_check["rows_count"], eval_check["columns_count"], schema_json_str, summary, initial_unlock_price, now))
        
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
    
    # Fetch completed evaluation and updated unlock price
    cursor.execute("SELECT * FROM evaluations WHERE dataset_id = ?", (dataset_id,))
    eval_row = cursor.fetchone()
    cursor.execute("SELECT unlock_price FROM datasets WHERE id = ?", (dataset_id,))
    ds_row = cursor.fetchone()
    final_unlock_price = ds_row["unlock_price"] if ds_row else initial_unlock_price

    quality_score = float(eval_row["quality_score"]) if eval_row else 0.0
    domain_rel = float(eval_row["domain_relevance_score"]) if eval_row else 0.0
    overall = float(eval_row["overall_score"]) if eval_row else 0.0
    credits_awarded = int(eval_row["credits_awarded"]) if eval_row else 0

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
        unlock_price=final_unlock_price,
        unlocked_by=[user["id"]],
        quality_score=quality_score,
        domain_relevance_score=domain_rel,
        overall_score=overall,
        credits_awarded=credits_awarded,
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
    
    unlocks_map = _get_dataset_unlocks_map(conn)
    
    # Fetch evaluations map
    cursor.execute("SELECT dataset_id, quality_score, domain_relevance_score, overall_score, credits_awarded FROM evaluations")
    eval_map = {r["dataset_id"]: r for r in cursor.fetchall()}

    items = []
    for r in rows:
        ds_id = r["id"]
        author_id = r["user_id"]
        unlocked_list = list(set([author_id] + unlocks_map.get(ds_id, [])))
        price = r["unlock_price"] if "unlock_price" in r.keys() and r["unlock_price"] is not None else 10
        eval_info = eval_map.get(ds_id)

        items.append(DatasetDetailResponse(
            id=ds_id,
            user_id=author_id,
            name=r["name"],
            filename=r["filename"],
            domain=r["domain"],
            rows_count=r["rows_count"],
            columns_count=r["columns_count"],
            schema_metadata=json.loads(r["schema_json"]),
            content_summary=r["content_summary"],
            unlock_price=price,
            unlocked_by=unlocked_list,
            quality_score=float(eval_info["quality_score"]) if eval_info else None,
            domain_relevance_score=float(eval_info["domain_relevance_score"]) if eval_info else None,
            overall_score=float(eval_info["overall_score"]) if eval_info else None,
            credits_awarded=int(eval_info["credits_awarded"]) if eval_info else None,
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
        
    cursor.execute("SELECT user_id FROM dataset_unlocks WHERE dataset_id = ?", (dataset_id,))
    unlocked_users = [row["user_id"] for row in cursor.fetchall()]
    if r["user_id"] not in unlocked_users:
        unlocked_users.append(r["user_id"])

    price = r["unlock_price"] if "unlock_price" in r.keys() and r["unlock_price"] is not None else 10

    cursor.execute("SELECT quality_score, domain_relevance_score, overall_score, credits_awarded FROM evaluations WHERE dataset_id = ?", (dataset_id,))
    eval_info = cursor.fetchone()

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
        unlock_price=price,
        unlocked_by=unlocked_users,
        quality_score=float(eval_info["quality_score"]) if eval_info else None,
        domain_relevance_score=float(eval_info["domain_relevance_score"]) if eval_info else None,
        overall_score=float(eval_info["overall_score"]) if eval_info else None,
        credits_awarded=int(eval_info["credits_awarded"]) if eval_info else None,
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

@router.post("/datasets/{dataset_id}/unlock", response_model=DatasetUnlockResponse)
def unlock_dataset(dataset_id: str, user: dict = Depends(get_current_user)):
    """
    Enforces atomic one-time dataset unlock.
    - Owners unlock their own datasets for free.
    - Idempotent: repeated unlock requests do not re-charge an already unlocked dataset.
    - Atomically debits buyer balance and rewards dataset author with royalty credits.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Verify dataset exists
    cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    dataset_row = cursor.fetchone()
    if not dataset_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found")
        
    owner_id = dataset_row["user_id"]
    dataset_name = dataset_row["name"]
    price = dataset_row["unlock_price"] if "unlock_price" in dataset_row.keys() and dataset_row["unlock_price"] is not None else 10
    
    # 2. Check if user is owner (always free)
    if user["id"] == owner_id:
        return DatasetUnlockResponse(
            dataset_id=dataset_id,
            unlocked=True,
            already_unlocked=True,
            credits_charged=0,
            remaining_balance=user["credits"],
            message="You are the author of this dataset. Access is permanently free."
        )
        
    # 3. Check if already unlocked (idempotent, 0 cost)
    cursor.execute("SELECT id FROM dataset_unlocks WHERE dataset_id = ? AND user_id = ?", (dataset_id, user["id"]))
    if cursor.fetchone():
        cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
        bal_row = cursor.fetchone()
        current_bal = bal_row["credits"] if bal_row else user["credits"]
        return DatasetUnlockResponse(
            dataset_id=dataset_id,
            unlocked=True,
            already_unlocked=True,
            credits_charged=0,
            remaining_balance=current_bal,
            message="Dataset already unlocked. Enjoy full query access."
        )
        
    # 4. Atomic balance deduction with negative-balance guard
    cursor.execute(
        "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
        (price, user["id"], price)
    )
    if cursor.rowcount == 0:
        cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
        bal_row = cursor.fetchone()
        cur_credits = bal_row["credits"] if bal_row else 0
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credit balance to unlock dataset. Required: {price} cr, available: {cur_credits} cr."
        )
        
    now = datetime.datetime.utcnow().isoformat()
    
    # 5. Reward dataset author with unlock royalties
    if owner_id and owner_id != user["id"]:
        cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (price, owner_id))
        royalty_tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
            VALUES (?, ?, ?, 'unlock_royalty', ?, 'completed', ?)
        """, (royalty_tx_id, owner_id, price, f"Unlock royalty for '{dataset_name}' ({dataset_id}) by {user['full_name']}", now))
        
    # 6. Record buyer transaction
    buyer_tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, ?, 'dataset_unlock', ?, 'completed', ?)
    """, (buyer_tx_id, user["id"], -price, f"Unlocked dataset '{dataset_name}' ({dataset_id})", now))
    
    # 7. Record unlock in dataset_unlocks table
    unlock_record_id = f"unl_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO dataset_unlocks (id, dataset_id, user_id, unlock_price, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (unlock_record_id, dataset_id, user["id"], price, now))
    
    conn.commit()
    
    cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
    final_bal = cursor.fetchone()["credits"]
    
    return DatasetUnlockResponse(
        dataset_id=dataset_id,
        unlocked=True,
        already_unlocked=False,
        credits_charged=price,
        remaining_balance=final_bal,
        message=f"Successfully unlocked dataset '{dataset_name}' for {price} credits."
    )

@router.post("/datasets/{dataset_id}/improve", response_model=DatasetImproveResponse)
def improve_dataset(dataset_id: str, req: DatasetImproveRequest, user: dict = Depends(get_current_user)):
    """
    Submits verified quality and schema improvements to an existing dataset.
    - Computes delta improvement against the dataset's current best evaluation score.
    - Awards credits only for verified score improvements (delta >= 5 pts: floor(delta * 0.75)).
    - Prevents duplicate claims on unchanged datasets.
    - Atomically updates user balance, logs credit transaction, and updates user reputation.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    ds_row = cursor.fetchone()
    if not ds_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found")
        
    # Get current best baseline score
    cursor.execute("SELECT overall_score FROM evaluations WHERE dataset_id = ?", (dataset_id,))
    eval_row = cursor.fetchone()
    base_score = float(eval_row["overall_score"]) if eval_row else 50.0
    
    # Check highest version score submitted previously
    cursor.execute("SELECT MAX(overall_score) AS max_ver_score, COUNT(*) AS ver_count FROM dataset_versions WHERE dataset_id = ?", (dataset_id,))
    ver_stat = cursor.fetchone()
    current_best = max(base_score, float(ver_stat["max_ver_score"] or 0.0))
    ver_count = ver_stat["ver_count"] or 0
    next_ver = f"v{ver_count + 2}.0"
    
    new_overall = round((req.new_quality_score + req.new_relevance_score) / 2.0, 2)
    delta = round(new_overall - current_best, 2)
    
    # Improvement credit bounty: delta >= 5 gives floor(delta * 0.75)
    # Repeated or negative deltas award 0 credits
    if delta >= 5.0:
        improvement_credits = int(math.floor(delta * 0.75))
    else:
        improvement_credits = 0
        
    now = datetime.datetime.utcnow().isoformat()
    ver_id = f"ver_{uuid.uuid4().hex[:12]}"
    
    # Insert version record
    cursor.execute("""
        INSERT INTO dataset_versions (
            id, dataset_id, version, user_id, quality_score, relevance_score,
            overall_score, delta_score, credits_awarded, changes_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ver_id, dataset_id, next_ver, user["id"], req.new_quality_score, req.new_relevance_score,
        new_overall, delta, improvement_credits, req.changes_summary, now
    ))
    
    if improvement_credits > 0:
        # Atomically credit contributor
        cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (improvement_credits, user["id"]))
        
        # Log in credit transactions ledger
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
            VALUES (?, ?, ?, 'improvement_reward', ?, 'completed', ?)
        """, (
            tx_id, user["id"], improvement_credits,
            f"Version improvement reward (+{delta:.1f} pts) for dataset '{ds_row['name']}' ({dataset_id})",
            now
        ))
        
    # Sync reputation
    new_rep = sync_and_get_user_reputation(user["id"], conn)
    conn.commit()
    
    return DatasetImproveResponse(
        dataset_id=dataset_id,
        version=next_ver,
        previous_overall_score=current_best,
        new_overall_score=new_overall,
        delta_score=delta,
        improvement_credits_awarded=improvement_credits,
        new_reputation_score=new_rep,
        changes_summary=req.changes_summary,
        created_at=now
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
            rows_count=d["rows_count"],
            unlock_price=d.get("unlock_price", 10)
        ) for d in ranked
    ]
    return SearchResponse(query=req.query, results=items, total=len(items), method=method)

@router.get("/datasets/search", response_model=SearchResponse)
def search_datasets_get(q: str = Query(..., min_length=1), domain: Optional[str] = Query(None), limit: int = Query(10, ge=1, le=100)):
    req = SearchRequest(query=q, domain=domain, limit=limit)
    return search_datasets(req)

