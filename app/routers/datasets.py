import logging
import threading
import uuid
import json
import math
import datetime
from typing import Optional, List, Dict, Any
from fastapi import UploadFile, File, Form, Depends, HTTPException, status, Query
from app.routers import TrailingSlashRouter
from app.config import settings
from app.database import DB_INTEGRITY_ERRORS, get_db_connection
from app.auth import get_current_user, get_optional_user
from app.services.admin_bootstrap import is_admin_email
from app.schemas import (
    DatasetDetailResponse, DatasetListResponse, EvaluationResponse, 
    SearchRequest, SearchResponse, SearchItem,
    DatasetUnlockResponse, DatasetImproveRequest, DatasetImproveResponse,
    DatasetVisibilityUpdateRequest,
)
from app.services.curated_library import has_packaged_curated_csv
from app.services.evaluation import parse_and_evaluate_csv, run_evaluation_pipeline
from app.services.r2_storage import R2StorageClient, R2StorageError
from app.services.recommender import recommend_datasets
from app.services.storage import (
    persist_dataset,
    delete_dataset_storage,
    get_existing_dataset_ids,
    dataset_table_exists,
)
from app.services.reputation import sync_and_get_user_reputation

logger = logging.getLogger(__name__)
router = TrailingSlashRouter(tags=["Datasets"])
_unlock_lock = threading.Lock()
_upload_lock = threading.Lock()


def _is_verified_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    return bool(user.get("is_admin")) and is_admin_email(user.get("email", ""))


def _normalize_visibility(raw_visibility: Optional[str]) -> str:
    val = (raw_visibility or "public").strip().lower()
    if val not in ("public", "private"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dataset visibility must be 'public' or 'private'.",
        )
    return val


def _can_access_dataset_row(row, user: Optional[dict]) -> bool:
    keys = row.keys()
    vis = (row["visibility"] or "public").strip().lower() if "visibility" in keys else "public"
    if vis != "private":
        return True
    if not user:
        return False
    return row["user_id"] == user["id"] or _is_verified_admin(user)


def _assert_dataset_readable(row, user: Optional[dict]) -> None:
    if _can_access_dataset_row(row, user):
        return
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access a private dataset.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: this dataset is private and only accessible to its owner or a platform administrator.",
    )

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
    visibility: str = Form("public"),
    user: dict = Depends(get_current_user)
):
    clean_visibility = _normalize_visibility(visibility)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files (.csv) are currently supported"
        )

    content_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(content_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"CSV file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
        )
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
    content_hash = eval_check.get("content_hash") or ""
    initial_unlock_price = eval_check.get("unlock_price", 10)
    
    summary = f"Structured dataset with {eval_check['rows_count']} rows across {eval_check['columns_count']} columns in the {domain} domain."
    schema_json_str = json.dumps(eval_check["schema"])

    # Prevent duplicate upload reward farming by the same user
    with _upload_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        if content_hash:
            cursor.execute(
                "SELECT id, name FROM datasets WHERE user_id = ? AND content_hash = ? LIMIT 1",
                (user["id"], content_hash),
            )
            dup = cursor.fetchone()
            if dup:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Duplicate dataset detected: you have already uploaded identical CSV content.",
                )

        # 1. Persist actual tabular data in DuckDB and disk storage
        r2_meta: Optional[Dict[str, Any]] = None
        r2_client = R2StorageClient()
        cleaned_csv_bytes = cleaned_csv.encode("utf-8")

        if settings.is_production and getattr(settings, "R2_REQUIRED_IN_PRODUCTION", True) and not r2_client.is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Community dataset uploads are unavailable in this production deployment because permanent "
                    "file storage is not configured. Curated public datasets remain available to query."
                ),
            )

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
            logger.exception("Failed to persist dataset %s to analytical storage", dataset_id)
            delete_dataset_storage(dataset_id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Failed to persist dataset into analytical storage. Please verify CSV formatting."
            )

        # 1b. Persist uploaded community CSV to Cloudflare R2 when configured (never silently lose files)
        if getattr(settings, "R2_PERSIST_COMMUNITY_UPLOADS", True) and r2_client.is_configured:
            try:
                r2_meta = r2_client.upload_community_csv(
                    dataset_id=dataset_id,
                    csv_bytes=cleaned_csv_bytes,
                )
            except (R2StorageError, ValueError) as e:
                logger.error("Cloudflare R2 upload failed for community dataset %s: %s", dataset_id, e)
                delete_dataset_storage(dataset_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to persist uploaded dataset to permanent cloud storage. Please try again.",
                )

        # 2. Insert metadata into relational catalog (SQLite locally, PostgreSQL in production)
        try:
            cursor.execute("""
                INSERT INTO datasets (
                    id, user_id, name, filename, domain, rows_count, columns_count,
                    schema_json, content_summary, unlock_price, content_hash, visibility,
                    object_storage_key, sha256_checksum, csv_bytes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dataset_id, user["id"], dataset_name, filename, domain,
                eval_check["rows_count"], eval_check["columns_count"],
                schema_json_str, summary, initial_unlock_price, content_hash, clean_visibility,
                r2_meta["object_storage_key"] if r2_meta else None,
                r2_meta["sha256_checksum"] if r2_meta else None,
                r2_meta["csv_bytes"] if r2_meta else len(cleaned_csv_bytes),
                now
            ))

            cursor.execute("""
                INSERT INTO evaluations (
                    id, dataset_id, status, progress, quality_score, schema_fidelity_score,
                    completeness_score, domain_relevance_score, overall_score, credits_awarded,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, 'pending', 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, NULL, ?, ?)
            """, (evaluation_id, dataset_id, now, now))
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Failed to register metadata for dataset %s", dataset_id)
            delete_dataset_storage(dataset_id)
            if r2_meta:
                try:
                    r2_client.delete_object(r2_meta["object_storage_key"])
                except Exception:
                    logger.warning("Failed to clean up R2 object %s after DB rollback.", r2_meta["object_storage_key"])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to register dataset metadata."
            )
    
    # 3. Execute evaluation pipeline (updates evaluation status and awards credits only on success)
    try:
        run_evaluation_pipeline(
            evaluation_id=evaluation_id,
            dataset_id=dataset_id,
            csv_content=cleaned_csv,
            filename=filename,
            domain=domain,
            user_id=user["id"]
        )
    except Exception:
        logger.exception("Evaluation pipeline failed unexpectedly for dataset %s; rolling back upload", dataset_id)
        try:
            conn.rollback()
            cursor.execute("DELETE FROM evaluations WHERE dataset_id = ?", (dataset_id,))
            cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
            conn.commit()
        except Exception:
            conn.rollback()
        delete_dataset_storage(dataset_id)
        if r2_meta:
            try:
                r2_client.delete_object(r2_meta["object_storage_key"])
            except Exception:
                logger.warning("Failed to clean up R2 object %s after evaluation rollback.", r2_meta["object_storage_key"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dataset evaluation failed; upload rolled back with 0 credits awarded."
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
        visibility=clean_visibility,
        created_at=now
    )

def _resolve_dataset_availability(row, table_exists: bool) -> tuple[bool, str]:
    """Resolve storage_available and human-readable availability for community & curated datasets."""
    keys = row.keys()
    is_curated = bool(row["is_curated"]) if "is_curated" in keys else False
    if table_exists:
        return True, "Available"
    ds_id = str(row["id"] or "").strip() if "id" in keys else ""
    obj_key = (row["object_storage_key"] or "").strip() if "object_storage_key" in keys else ""
    checksum = (row["sha256_checksum"] or "").strip() if "sha256_checksum" in keys else ""
    if is_curated:
        ing_status = (row["ingestion_status"] or "").strip().lower() if "ingestion_status" in keys else ""
        if ing_status == "ingested" and checksum:
            if has_packaged_curated_csv(ds_id) or obj_key:
                return True, "On-Demand Ready"
            return False, "Missing Packaged File"
        if ing_status == "pending_ingestion":
            return False, "Pending Ingestion"
    elif obj_key and checksum:
        return True, "Cloud-Backed Ready"
    return False, "Unavailable"


def _row_to_dataset_detail(row, unlocked_list: List[str], eval_info, table_exists: bool) -> DatasetDetailResponse:
    keys = row.keys()
    is_curated = bool(row["is_curated"]) if "is_curated" in keys else False
    dataset_type = (row["dataset_type"] if "dataset_type" in keys and row["dataset_type"] else None) or (
        "curated" if is_curated else "community"
    )
    price = 0 if is_curated else (row["unlock_price"] if "unlock_price" in keys and row["unlock_price"] is not None else 10)
    is_avail, availability_label = _resolve_dataset_availability(row, table_exists)

    return DatasetDetailResponse(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        filename=row["filename"],
        domain=row["domain"],
        rows_count=row["rows_count"],
        columns_count=row["columns_count"],
        schema_metadata=json.loads(row["schema_json"]) if row["schema_json"] else {},
        content_summary=row["content_summary"],
        unlock_price=price,
        unlocked_by=unlocked_list,
        storage_available=is_avail,
        availability=availability_label,
        quality_score=float(eval_info["quality_score"]) if eval_info else None,
        domain_relevance_score=float(eval_info["domain_relevance_score"]) if eval_info else None,
        overall_score=float(eval_info["overall_score"]) if eval_info else None,
        credits_awarded=int(eval_info["credits_awarded"]) if eval_info else None,
        created_at=row["created_at"],
        is_curated=is_curated,
        dataset_type=dataset_type,
        source_name=row["source_name"] if "source_name" in keys else None,
        source_url=row["source_url"] if "source_url" in keys else None,
        license=row["license"] if "license" in keys else None,
        license_url=row["license_url"] if "license_url" in keys else None,
        retrieved_at=row["retrieved_at"] if "retrieved_at" in keys else None,
        ingestion_status=(row["ingestion_status"] if "ingestion_status" in keys and row["ingestion_status"] else "ready"),
        sha256_checksum=row["sha256_checksum"] if "sha256_checksum" in keys else None,
        source_version=row["source_version"] if "source_version" in keys else None,
        visibility=(row["visibility"] if "visibility" in keys and row["visibility"] else "public"),
    )


@router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(
    domain: Optional[str] = Query(None, description="Optional case-insensitive domain filter"),
    source: Optional[str] = Query(None, description="Optional library source filter: all, mine, curated, community"),
    include_pending: bool = Query(False, description="Include un-ingested pending curated metadata entries"),
    user: Optional[dict] = Depends(get_optional_user),
):
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions: List[str] = []
    params: List[Any] = []

    # Never surface un-ingested pending curated entries as queryable catalog items by default
    if not include_pending:
        conditions.append(
            "NOT (COALESCE(is_curated, 0) = 1 AND LOWER(COALESCE(ingestion_status, 'ready')) != 'ingested')"
        )

    # Enforce private dataset visibility in the backend
    if not _is_verified_admin(user):
        if user:
            conditions.append("(LOWER(COALESCE(visibility, 'public')) != 'private' OR user_id = ?)")
            params.append(user["id"])
        else:
            conditions.append("LOWER(COALESCE(visibility, 'public')) != 'private'")

    if domain and domain.strip() and domain.strip().lower() != "all":
        conditions.append("LOWER(domain) = LOWER(?)")
        params.append(domain.strip())
    if source and source.strip():
        src = source.strip().lower()
        if src == "curated":
            conditions.append("COALESCE(is_curated, 0) = 1")
        elif src == "community":
            conditions.append("COALESCE(is_curated, 0) = 0 AND LOWER(COALESCE(visibility, 'public')) != 'private'")
        elif src == "mine":
            if not user:
                return DatasetListResponse(datasets=[], total=0)
            conditions.append("user_id = ? AND COALESCE(is_curated, 0) = 0")
            params.append(user["id"])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor.execute(f"SELECT * FROM datasets {where_clause} ORDER BY created_at DESC", params)
    rows = cursor.fetchall()

    unlocks_map = _get_dataset_unlocks_map(conn)
    existing_tables = get_existing_dataset_ids()

    # Fetch evaluations map (ordered oldest -> newest so dict keeps latest evaluation per dataset)
    cursor.execute(
        "SELECT dataset_id, quality_score, domain_relevance_score, overall_score, credits_awarded FROM evaluations ORDER BY created_at ASC"
    )
    eval_map = {r["dataset_id"]: r for r in cursor.fetchall()}

    items = []
    for r in rows:
        ds_id = r["id"]
        author_id = r["user_id"]
        unlocked_list = list(set([author_id] + unlocks_map.get(ds_id, [])))
        eval_info = eval_map.get(ds_id)
        table_exists = ds_id in existing_tables
        items.append(_row_to_dataset_detail(r, unlocked_list, eval_info, table_exists))
    return DatasetListResponse(datasets=items, total=len(items))

@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: str, user: Optional[dict] = Depends(get_optional_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    r = cursor.fetchone()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    _assert_dataset_readable(r, user)

    cursor.execute("SELECT user_id FROM dataset_unlocks WHERE dataset_id = ?", (dataset_id,))
    unlocked_users = [row["user_id"] for row in cursor.fetchall()]
    if r["user_id"] not in unlocked_users:
        unlocked_users.append(r["user_id"])

    cursor.execute("SELECT quality_score, domain_relevance_score, overall_score, credits_awarded FROM evaluations WHERE dataset_id = ?", (dataset_id,))
    eval_info = cursor.fetchone()
    try:
        table_exists = dataset_table_exists(dataset_id)
    except ValueError:
        table_exists = False

    return _row_to_dataset_detail(r, unlocked_users, eval_info, table_exists)

@router.get("/datasets/{dataset_id}/evaluation", response_model=EvaluationResponse)
def get_dataset_evaluation(dataset_id: str, user: Optional[dict] = Depends(get_optional_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    ds_row = cursor.fetchone()
    if ds_row:
        _assert_dataset_readable(ds_row, user)
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


@router.patch("/datasets/{dataset_id}/visibility", response_model=DatasetDetailResponse)
def update_dataset_visibility(
    dataset_id: str,
    req: DatasetVisibilityUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """Toggle a dataset's visibility between 'public' and 'private' (owner or admin only)."""
    new_vis = _normalize_visibility(req.visibility)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    ds_row = cursor.fetchone()
    if not ds_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found")
    if ds_row["user_id"] != user["id"] and not _is_verified_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dataset owner or a platform administrator may change visibility.",
        )
    if bool(ds_row["is_curated"]) and new_vis == "private":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Curated Public Library datasets must remain publicly accessible.",
        )

    cursor.execute("UPDATE datasets SET visibility = ? WHERE id = ?", (new_vis, dataset_id))
    conn.commit()
    return get_dataset(dataset_id, user=user)

@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, user: dict = Depends(get_current_user)):
    """
    Safely deletes a dataset from DuckDB, disk storage, and catalog metadata.
    Strictly restricted to the dataset owner or a verified platform administrator.
    Preserves immutable credit_transactions and queries audit history.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, name FROM datasets WHERE id = ?", (dataset_id,))
    ds_row = cursor.fetchone()
    if not ds_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found")

    if ds_row["user_id"] != user["id"] and not _is_verified_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dataset owner or a platform administrator may delete this dataset.",
        )

    try:
        cursor.execute("DELETE FROM dataset_unlocks WHERE dataset_id = ?", (dataset_id,))
        cursor.execute("DELETE FROM dataset_versions WHERE dataset_id = ?", (dataset_id,))
        cursor.execute("DELETE FROM evaluations WHERE dataset_id = ?", (dataset_id,))
        cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to delete dataset metadata for %s", dataset_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete dataset.",
        )

    delete_dataset_storage(dataset_id)
    return {"deleted": True, "dataset_id": dataset_id}


@router.post("/datasets/{dataset_id}/unlock", response_model=DatasetUnlockResponse)
def unlock_dataset(dataset_id: str, user: dict = Depends(get_current_user)):
    """
    Enforces atomic one-time dataset unlock serialized against concurrent requests.
    - Owners unlock their own datasets for free.
    - Idempotent: repeated or concurrent unlock requests never double-charge or double-pay royalties.
    - Atomically debits buyer balance and rewards dataset author with royalty credits.
    """
    with _unlock_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Verify dataset exists and caller is authorized to view it
        cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
        dataset_row = cursor.fetchone()
        if not dataset_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found")
        _assert_dataset_readable(dataset_row, user)

        owner_id = dataset_row["user_id"]
        dataset_name = dataset_row["name"]
        is_curated = bool(dataset_row["is_curated"]) if "is_curated" in dataset_row.keys() else False
        price = 0 if is_curated else (dataset_row["unlock_price"] if "unlock_price" in dataset_row.keys() and dataset_row["unlock_price"] is not None else 10)

        # 2a. Curated public datasets are permanently free for all authenticated users (0 credits, 0 transactions)
        if is_curated:
            cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
            bal_row = cursor.fetchone()
            return DatasetUnlockResponse(
                dataset_id=dataset_id,
                unlocked=True,
                already_unlocked=True,
                credits_charged=0,
                remaining_balance=int(bal_row["credits"]) if bal_row else user["credits"],
                message="Curated Public Library datasets are free to access for all authenticated users."
            )

        # 2b. Check if user is owner (always free)
        if user["id"] == owner_id:
            cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
            bal_row = cursor.fetchone()
            return DatasetUnlockResponse(
                dataset_id=dataset_id,
                unlocked=True,
                already_unlocked=True,
                credits_charged=0,
                remaining_balance=int(bal_row["credits"]) if bal_row else user["credits"],
                message="You are the author of this dataset. Access is permanently free."
            )

        now = datetime.datetime.utcnow().isoformat()
        unlock_record_id = f"unl_{uuid.uuid4().hex[:12]}"

        # 3. Claim unlock slot first via UNIQUE(dataset_id, user_id) for true concurrency idempotency
        try:
            cursor.execute("""
                INSERT INTO dataset_unlocks (id, dataset_id, user_id, unlock_price, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (unlock_record_id, dataset_id, user["id"], price, now))
        except DB_INTEGRITY_ERRORS:
            conn.rollback()
            cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
            bal_row = cursor.fetchone()
            current_bal = int(bal_row["credits"]) if bal_row else user["credits"]
            return DatasetUnlockResponse(
                dataset_id=dataset_id,
                unlocked=True,
                already_unlocked=True,
                credits_charged=0,
                remaining_balance=current_bal,
                message="Dataset already unlocked. Enjoy full query access."
            )

        # 4. Atomic balance deduction with negative-balance guard (rolls back unlock slot if insufficient)
        cursor.execute(
            "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
            (price, user["id"], price)
        )
        if cursor.rowcount == 0:
            conn.rollback()
            cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
            bal_row = cursor.fetchone()
            cur_credits = int(bal_row["credits"]) if bal_row else 0
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient credit balance to unlock dataset. Required: {price} cr, available: {cur_credits} cr."
            )

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

        conn.commit()

        cursor.execute("SELECT credits FROM users WHERE id = ?", (user["id"],))
        final_bal = int(cursor.fetchone()["credits"])

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
    - Restricted to the dataset owner or a verified platform administrator.
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

    if ds_row["user_id"] != user["id"] and not _is_verified_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dataset owner or a platform administrator may submit improvements for this dataset.",
        )
        
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
def search_datasets(req: SearchRequest, user: Optional[dict] = Depends(get_optional_user)):
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions: List[str] = [
        "NOT (COALESCE(is_curated, 0) = 1 AND LOWER(COALESCE(ingestion_status, 'ready')) != 'ingested')"
    ]
    params: List[Any] = []
    if not _is_verified_admin(user):
        if user:
            conditions.append("(LOWER(COALESCE(visibility, 'public')) != 'private' OR user_id = ?)")
            params.append(user["id"])
        else:
            conditions.append("LOWER(COALESCE(visibility, 'public')) != 'private'")

    if req.domain and req.domain.strip() and req.domain.strip().lower() != "all":
        conditions.append("LOWER(domain) = LOWER(?)")
        params.append(req.domain.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT * FROM datasets {where_clause}", params)
    all_datasets = [dict(row) for row in cursor.fetchall()]

    ranked, method = recommend_datasets(req.query, all_datasets, limit=req.limit)

    unlocks_map = _get_dataset_unlocks_map(conn)
    existing_tables = get_existing_dataset_ids()
    cursor.execute(
        "SELECT dataset_id, quality_score, domain_relevance_score, overall_score, credits_awarded FROM evaluations ORDER BY created_at ASC"
    )
    eval_map = {r["dataset_id"]: r for r in cursor.fetchall()}

    items = []
    for d in ranked:
        ds_id = d["id"]
        author_id = d.get("user_id")
        is_curated = bool(d.get("is_curated"))
        dataset_type = d.get("dataset_type") or ("curated" if is_curated else "community")
        raw_unlock = d.get("unlock_price")
        price = 0 if is_curated else (int(raw_unlock) if raw_unlock is not None else 10)
        eval_info = eval_map.get(ds_id)
        unlocked_list = list(set(([author_id] if author_id else []) + unlocks_map.get(ds_id, [])))
        is_avail, availability_label = _resolve_dataset_availability(d, ds_id in existing_tables)
        items.append(
            SearchItem(
                dataset_id=ds_id,
                user_id=author_id,
                name=d["name"],
                filename=d.get("filename"),
                domain=d["domain"],
                score=d["score"],
                summary=d["content_summary"],
                rows_count=d["rows_count"],
                columns_count=d.get("columns_count"),
                unlock_price=price,
                unlocked_by=unlocked_list,
                quality_score=float(eval_info["quality_score"]) if eval_info else None,
                domain_relevance_score=float(eval_info["domain_relevance_score"]) if eval_info else None,
                overall_score=float(eval_info["overall_score"]) if eval_info else None,
                storage_available=is_avail,
                availability=availability_label,
                is_curated=is_curated,
                dataset_type=dataset_type,
                visibility=d.get("visibility") or "public",
                license=d.get("license"),
                source_name=d.get("source_name"),
                created_at=d.get("created_at"),
            )
        )
    return SearchResponse(query=req.query, results=items, total=len(items), method=method)

@router.get("/datasets/search", response_model=SearchResponse)
def search_datasets_get(
    q: str = Query(..., min_length=1),
    domain: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    user: Optional[dict] = Depends(get_optional_user),
):
    req = SearchRequest(query=q, domain=domain, limit=limit)
    return search_datasets(req, user=user)
