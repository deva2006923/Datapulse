import json
from typing import Optional, List, Any, Dict
from fastapi import HTTPException, status, Depends, Query, Request
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_current_admin_user, log_admin_audit
from app.schemas import (
    AdminOverviewResponse,
    AdminActivityItem,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserDetailResponse,
    AdminUserDatasetItem,
    AdminDatasetItem,
    AdminDatasetListResponse,
    AdminQueryItem,
    AdminQueryListResponse,
    AdminTransactionItem,
    AdminTransactionListResponse,
    AdminAuditLogItem,
    AdminAuditLogListResponse
)

router = TrailingSlashRouter(prefix="/admin", tags=["Admin Dashboard"])


@router.get("/overview", response_model=AdminOverviewResponse)
def get_admin_overview(
    request: Request,
    admin: dict = Depends(get_current_admin_user)
):
    """
    Returns platform-wide summary metrics and recent platform activities.
    Requires verified administrator authorization.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Total registered users
    cursor.execute("SELECT COUNT(*) AS total FROM users")
    total_users = cursor.fetchone()["total"] or 0

    # 2. Total uploaded datasets
    cursor.execute("SELECT COUNT(*) AS total FROM datasets")
    total_datasets = cursor.fetchone()["total"] or 0

    # 3. Total queries, successful vs failed
    cursor.execute("SELECT COUNT(*) AS total FROM queries")
    total_queries = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT COUNT(*) AS total FROM queries WHERE UPPER(status) = 'SUCCESS'")
    total_queries_successful = cursor.fetchone()["total"] or 0
    total_queries_failed = total_queries - total_queries_successful

    # 4. Total credits issued and spent
    cursor.execute("SELECT SUM(amount) AS total FROM credit_transactions WHERE amount > 0")
    total_credits_issued = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT ABS(SUM(amount)) AS total FROM credit_transactions WHERE amount < 0")
    total_credits_spent = cursor.fetchone()["total"] or 0

    # Net credit liability (sum of current user balances)
    cursor.execute("SELECT SUM(credits) AS total FROM users")
    net_credit_liability = cursor.fetchone()["total"] or 0

    # 5. Recent platform activity feed
    activity_items: List[AdminActivityItem] = []

    # Recent user registrations
    cursor.execute("SELECT id, email, full_name, created_at FROM users ORDER BY created_at DESC LIMIT 5")
    for r in cursor.fetchall():
        activity_items.append(AdminActivityItem(
            id=f"act_reg_{r['id']}",
            type="USER_REGISTER",
            description=f"User registered: {r['full_name']}",
            user_id=r["id"],
            user_email=r["email"],
            status="SUCCESS",
            timestamp=r["created_at"]
        ))

    # Recent dataset uploads
    cursor.execute("""
        SELECT d.id, d.name, d.rows_count, d.created_at, u.id AS user_id, u.email AS user_email
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        ORDER BY d.created_at DESC LIMIT 5
    """)
    for r in cursor.fetchall():
        activity_items.append(AdminActivityItem(
            id=f"act_ds_{r['id']}",
            type="DATASET_UPLOAD",
            description=f"Dataset uploaded: '{r['name']}' ({r['rows_count']} rows)",
            user_id=r["user_id"],
            user_email=r["user_email"],
            status="SUCCESS",
            timestamp=r["created_at"]
        ))

    # Recent query executions
    cursor.execute("""
        SELECT q.id, q.query_text, q.dataset_name, q.status, q.created_at, u.id AS user_id, u.email AS user_email
        FROM queries q
        JOIN users u ON q.user_id = u.id
        ORDER BY q.created_at DESC LIMIT 5
    """)
    for r in cursor.fetchall():
        ds_name = r["dataset_name"] or "Cross-Catalog"
        q_snippet = (r["query_text"][:50] + "...") if len(r["query_text"]) > 50 else r["query_text"]
        activity_items.append(AdminActivityItem(
            id=f"act_qry_{r['id']}",
            type="QUERY_EXECUTION",
            description=f"Query on {ds_name}: \"{q_snippet}\"",
            user_id=r["user_id"],
            user_email=r["user_email"],
            status=r["status"] or "SUCCESS",
            timestamp=r["created_at"]
        ))

    # Recent transactions
    cursor.execute("""
        SELECT t.id, t.amount, t.description, t.transaction_type, t.created_at, u.id AS user_id, u.email AS user_email
        FROM credit_transactions t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC LIMIT 5
    """)
    for r in cursor.fetchall():
        impact = f"+{r['amount']}" if r["amount"] > 0 else f"{r['amount']}"
        activity_items.append(AdminActivityItem(
            id=f"act_tx_{r['id']}",
            type="CREDIT_TRANSACTION",
            description=f"{r['description']} ({impact} cr)",
            user_id=r["user_id"],
            user_email=r["user_email"],
            status="SUCCESS",
            timestamp=r["created_at"]
        ))

    # Sort consolidated activity feed newest first
    activity_items.sort(key=lambda a: a.timestamp, reverse=True)
    recent_activity = activity_items[:15]

    # Audit log entry
    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_OVERVIEW",
        details="Platform overview requested",
        ip_address=client_ip
    )

    return AdminOverviewResponse(
        total_users=total_users,
        total_datasets=total_datasets,
        total_queries=total_queries,
        total_queries_successful=total_queries_successful,
        total_queries_failed=total_queries_failed,
        total_credits_issued=total_credits_issued,
        total_credits_spent=total_credits_spent,
        net_credit_liability=net_credit_liability,
        recent_activity=recent_activity
    )


@router.get("/users", response_model=AdminUserListResponse)
def get_admin_users(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by user name or email"),
    role: Optional[str] = Query(None, description="Filter by role: admin, user, all"),
    sort_by: Optional[str] = Query("created_at", description="Sort by: created_at, credits, reputation_score, full_name"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc, desc"),
    admin: dict = Depends(get_current_admin_user)
):
    """
    Searchable, filterable, paginated directory of registered users for administrators.
    Never exposes passwords, tokens, or hashes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(u.full_name) LIKE ? OR LOWER(u.email) LIKE ?)")
        params.extend([term, term])

    if role and role.strip() and role.strip().lower() != "all":
        if role.strip().lower() == "admin":
            conditions.append("u.is_admin = 1")
        elif role.strip().lower() == "user":
            conditions.append("u.is_admin = 0")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Total count
    count_query = f"SELECT COUNT(*) AS total FROM users u {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()["total"] or 0

    # Sort column validation
    valid_sort_cols = {
        "created_at": "u.created_at",
        "credits": "u.credits",
        "reputation_score": "u.reputation_score",
        "full_name": "u.full_name"
    }
    col = valid_sort_cols.get(sort_by or "created_at", "u.created_at")
    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"

    offset = (page - 1) * limit
    data_query = f"""
        SELECT u.id, u.email, u.full_name, u.credits, u.reputation_score, u.is_admin, u.created_at,
               (SELECT COUNT(*) FROM datasets d WHERE d.user_id = u.id) AS datasets_count,
               (SELECT COUNT(*) FROM queries q WHERE q.user_id = u.id) AS queries_count
        FROM users u
        {where_clause}
        ORDER BY {col} {order}, u.id {order}
        LIMIT ? OFFSET ?
    """
    data_params = list(params) + [limit, offset]
    cursor.execute(data_query, data_params)
    rows = cursor.fetchall()

    items = []
    for r in rows:
        items.append(AdminUserItem(
            id=r["id"],
            email=r["email"],
            full_name=r["full_name"],
            credits=r["credits"] or 0,
            reputation_score=r["reputation_score"] if "reputation_score" in r.keys() else 50,
            is_admin=bool(r["is_admin"]) if "is_admin" in r.keys() else False,
            account_status="Admin" if bool(r["is_admin"] if "is_admin" in r.keys() else 0) else "Active",
            datasets_count=r["datasets_count"] or 0,
            queries_count=r["queries_count"] or 0,
            created_at=r["created_at"]
        ))

    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_USERS",
        details=f"Listed users page={page}, limit={limit}, search={search}",
        ip_address=client_ip
    )

    return AdminUserListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def get_admin_user_detail(
    user_id: str,
    request: Request,
    admin: dict = Depends(get_current_admin_user)
):
    """
    Returns complete user profile, uploaded datasets, recent query history,
    and credit transactions for administrative inspection.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, email, full_name, credits, reputation_score, is_admin, created_at
        FROM users
        WHERE id = ?
    """, (user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{user_id}' not found."
        )

    # Aggregates
    cursor.execute("SELECT COUNT(*) AS total FROM datasets WHERE user_id = ?", (user_id,))
    total_datasets = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT COUNT(*) AS total FROM queries WHERE user_id = ?", (user_id,))
    total_queries = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT SUM(amount) AS total FROM credit_transactions WHERE user_id = ? AND amount > 0", (user_id,))
    total_credits_earned = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT ABS(SUM(amount)) AS total FROM credit_transactions WHERE user_id = ? AND amount < 0", (user_id,))
    total_credits_spent = cursor.fetchone()["total"] or 0

    # User's uploaded datasets
    cursor.execute("""
        SELECT d.id, d.name, d.filename, d.domain, d.rows_count, d.columns_count, d.unlock_price, d.created_at,
               e.overall_score AS quality_score
        FROM datasets d
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        WHERE d.user_id = ?
        ORDER BY d.created_at DESC
    """, (user_id,))
    ds_rows = cursor.fetchall()
    datasets = [
        AdminUserDatasetItem(
            id=r["id"],
            name=r["name"],
            filename=r["filename"],
            domain=r["domain"],
            rows_count=r["rows_count"],
            columns_count=r["columns_count"],
            quality_score=round(float(r["quality_score"]), 1) if r["quality_score"] is not None else None,
            unlock_price=r["unlock_price"] or 10,
            created_at=r["created_at"]
        ) for r in ds_rows
    ]

    # Recent queries
    cursor.execute("""
        SELECT id, query_text, dataset_name, generated_sql, status, execution_time_ms,
               result_count, credits_charged, error_message, created_at
        FROM queries
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 20
    """, (user_id,))
    query_rows = cursor.fetchall()
    recent_queries = [
        {
            "id": r["id"],
            "natural_prompt": r["query_text"],
            "dataset_name": r["dataset_name"] or "Cross-Catalog",
            "generated_sql": r["generated_sql"] or "-- No SQL generated",
            "status": r["status"] or "SUCCESS",
            "execution_time_ms": r["execution_time_ms"] or 0,
            "rows_returned": r["result_count"] or 0,
            "credits_charged": r["credits_charged"] or 0,
            "error_message": r["error_message"],
            "timestamp": r["created_at"]
        } for r in query_rows
    ]

    # Recent transactions
    cursor.execute("""
        SELECT id, amount, transaction_type, description, status, created_at
        FROM credit_transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 20
    """, (user_id,))
    tx_rows = cursor.fetchall()
    recent_transactions = [
        {
            "id": r["id"],
            "amount": r["amount"],
            "transaction_type": r["transaction_type"],
            "description": r["description"],
            "status": r["status"],
            "balance_impact": f"+{r['amount']}" if r["amount"] > 0 else f"{r['amount']}",
            "created_at": r["created_at"]
        } for r in tx_rows
    ]

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_USER_DETAIL",
        target_resource=user_id,
        details=f"Viewed user detail for {user_row['email']}",
        ip_address=client_ip
    )

    return AdminUserDetailResponse(
        id=user_row["id"],
        email=user_row["email"],
        full_name=user_row["full_name"],
        credits=user_row["credits"] or 0,
        reputation_score=user_row["reputation_score"] if "reputation_score" in user_row.keys() else 50,
        is_admin=bool(user_row["is_admin"]) if "is_admin" in user_row.keys() else False,
        account_status="Admin" if bool(user_row["is_admin"] if "is_admin" in user_row.keys() else 0) else "Active",
        created_at=user_row["created_at"],
        total_datasets=total_datasets,
        total_queries=total_queries,
        total_credits_earned=total_credits_earned,
        total_credits_spent=total_credits_spent,
        datasets=datasets,
        recent_queries=recent_queries,
        recent_transactions=recent_transactions
    )


@router.get("/datasets", response_model=AdminDatasetListResponse)
def get_admin_datasets(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by dataset title, filename, domain, or owner"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    owner_id: Optional[str] = Query(None, description="Filter by owner user ID"),
    sort_by: Optional[str] = Query("created_at", description="Sort by: created_at, rows_count, quality_score, name"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc, desc"),
    admin: dict = Depends(get_current_admin_user)
):
    """
    Returns platform-wide dataset registry with ownership, quality evaluations,
    and storage availability. Avoids unrestricted raw file data dumps.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(d.name) LIKE ? OR LOWER(d.filename) LIKE ? OR LOWER(d.domain) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(u.full_name) LIKE ?)")
        params.extend([term, term, term, term, term])

    if domain and domain.strip() and domain.strip().lower() != "all":
        conditions.append("LOWER(d.domain) = ?")
        params.append(domain.strip().lower())

    if owner_id and owner_id.strip():
        conditions.append("d.user_id = ?")
        params.append(owner_id.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Total count
    count_query = f"""
        SELECT COUNT(*) AS total
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        {where_clause}
    """
    cursor.execute(count_query, params)
    total = cursor.fetchone()["total"] or 0

    valid_sort_cols = {
        "created_at": "d.created_at",
        "rows_count": "d.rows_count",
        "quality_score": "e.overall_score",
        "name": "d.name"
    }
    col = valid_sort_cols.get(sort_by or "created_at", "d.created_at")
    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"

    offset = (page - 1) * limit
    data_query = f"""
        SELECT d.id, d.name, d.filename, d.domain, d.rows_count, d.columns_count,
               d.content_summary, d.unlock_price, d.created_at,
               u.id AS owner_id, u.full_name AS owner_name, u.email AS owner_email,
               e.quality_score, e.domain_relevance_score, e.overall_score,
               e.status AS evaluation_status, e.credits_awarded,
               (SELECT COUNT(*) FROM dataset_unlocks du WHERE du.dataset_id = d.id) AS unlock_count
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        {where_clause}
        ORDER BY {col} {order}, d.id {order}
        LIMIT ? OFFSET ?
    """
    data_params = list(params) + [limit, offset]
    cursor.execute(data_query, data_params)
    rows = cursor.fetchall()

    items = []
    for r in rows:
        items.append(AdminDatasetItem(
            id=r["id"],
            title=r["name"],
            name=r["name"],
            filename=r["filename"],
            owner_id=r["owner_id"],
            owner_name=r["owner_name"],
            owner_email=r["owner_email"],
            domain=r["domain"],
            rows_count=r["rows_count"],
            columns_count=r["columns_count"],
            quality_score=round(float(r["quality_score"]), 1) if r["quality_score"] is not None else None,
            domain_relevance_score=round(float(r["domain_relevance_score"]), 1) if r["domain_relevance_score"] is not None else None,
            overall_score=round(float(r["overall_score"]), 1) if r["overall_score"] is not None else None,
            evaluation_status=r["evaluation_status"] or "pending",
            credits_awarded=r["credits_awarded"],
            unlock_price=r["unlock_price"] or 10,
            unlock_count=r["unlock_count"] or 0,
            availability="Available",
            content_summary=r["content_summary"] or "",
            created_at=r["created_at"]
        ))

    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_DATASETS",
        details=f"Listed datasets page={page}, limit={limit}",
        ip_address=client_ip
    )

    return AdminDatasetListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more
    )


@router.get("/queries", response_model=AdminQueryListResponse)
def get_admin_queries(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search prompt, SQL, dataset name, or user email"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    dataset_id: Optional[str] = Query(None, description="Filter by dataset ID"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, SQL_REJECTED, etc.)"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    admin: dict = Depends(get_current_admin_user)
):
    """
    Global query execution audit log across all users.
    Exposes prompt and generated SQL to administrators, but keeps individual user views isolated.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(q.query_text) LIKE ? OR LOWER(COALESCE(q.generated_sql, '')) LIKE ? OR LOWER(COALESCE(q.dataset_name, '')) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(u.full_name) LIKE ?)")
        params.extend([term, term, term, term, term])

    if user_id and user_id.strip():
        conditions.append("q.user_id = ?")
        params.append(user_id.strip())

    if dataset_id and dataset_id.strip():
        conditions.append("q.dataset_id = ?")
        params.append(dataset_id.strip())

    if status and status.strip() and status.strip().upper() != "ALL":
        conditions.append("UPPER(q.status) = ?")
        params.append(status.strip().upper())

    if start_date and start_date.strip():
        conditions.append("q.created_at >= ?")
        params.append(start_date.strip())

    if end_date and end_date.strip():
        # Include full end date up to end of day if YYYY-MM-DD format
        ed = end_date.strip()
        if len(ed) == 10:
            ed = f"{ed}T23:59:59"
        conditions.append("q.created_at <= ?")
        params.append(ed)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Total count
    count_query = f"""
        SELECT COUNT(*) AS total
        FROM queries q
        JOIN users u ON q.user_id = u.id
        {where_clause}
    """
    cursor.execute(count_query, params)
    total = cursor.fetchone()["total"] or 0

    offset = (page - 1) * limit
    data_query = f"""
        SELECT q.id, q.user_id, q.dataset_id, q.dataset_name, q.query_text, q.generated_sql,
               q.execution_time_ms, q.result_count, q.status, q.credits_charged, q.error_message, q.created_at,
               u.email AS user_email, u.full_name AS user_name
        FROM queries q
        JOIN users u ON q.user_id = u.id
        {where_clause}
        ORDER BY q.created_at DESC, q.id DESC
        LIMIT ? OFFSET ?
    """
    data_params = list(params) + [limit, offset]
    cursor.execute(data_query, data_params)
    rows = cursor.fetchall()

    items = []
    for r in rows:
        items.append(AdminQueryItem(
            id=r["id"],
            user_id=r["user_id"],
            user_email=r["user_email"],
            user_name=r["user_name"],
            natural_prompt=r["query_text"],
            dataset_id=r["dataset_id"],
            dataset_name=r["dataset_name"] or "Cross-Catalog",
            generated_sql=r["generated_sql"] or "-- No SQL generated",
            execution_status=r["status"] or "SUCCESS",
            execution_time_ms=r["execution_time_ms"] or 0,
            rows_returned=r["result_count"] or 0,
            credits_charged=r["credits_charged"] or 0,
            error_message=r["error_message"],
            timestamp=r["created_at"]
        ))

    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_QUERIES",
        details=f"Listed queries page={page}, limit={limit}",
        ip_address=client_ip
    )

    return AdminQueryListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more
    )


@router.get("/transactions", response_model=AdminTransactionListResponse)
def get_admin_transactions(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search description or user email"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    transaction_type: Optional[str] = Query(None, description="Filter by transaction type"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    admin: dict = Depends(get_current_admin_user)
):
    """
    Platform-wide credit ledger and financial audit history.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(t.description) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(u.full_name) LIKE ?)")
        params.extend([term, term, term])

    if user_id and user_id.strip():
        conditions.append("t.user_id = ?")
        params.append(user_id.strip())

    if transaction_type and transaction_type.strip() and transaction_type.strip().lower() != "all":
        conditions.append("LOWER(t.transaction_type) = ?")
        params.append(transaction_type.strip().lower())

    if start_date and start_date.strip():
        conditions.append("t.created_at >= ?")
        params.append(start_date.strip())

    if end_date and end_date.strip():
        ed = end_date.strip()
        if len(ed) == 10:
            ed = f"{ed}T23:59:59"
        conditions.append("t.created_at <= ?")
        params.append(ed)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Total count
    count_query = f"""
        SELECT COUNT(*) AS total
        FROM credit_transactions t
        JOIN users u ON t.user_id = u.id
        {where_clause}
    """
    cursor.execute(count_query, params)
    total = cursor.fetchone()["total"] or 0

    offset = (page - 1) * limit
    data_query = f"""
        SELECT t.id, t.user_id, t.amount, t.transaction_type, t.description, t.status, t.created_at,
               u.email AS user_email, u.full_name AS user_name
        FROM credit_transactions t
        JOIN users u ON t.user_id = u.id
        {where_clause}
        ORDER BY t.created_at DESC, t.id DESC
        LIMIT ? OFFSET ?
    """
    data_params = list(params) + [limit, offset]
    cursor.execute(data_query, data_params)
    rows = cursor.fetchall()

    items = []
    for r in rows:
        amount = r["amount"]
        impact = f"+{amount}" if amount > 0 else f"{amount}"
        
        # Infer associated resource from description when available
        desc = r["description"] or ""
        assoc = None
        if "dataset" in desc.lower():
            assoc = "Dataset Asset"
        elif "query" in desc.lower():
            assoc = "Query Engine"
        elif "redeem" in desc.lower():
            assoc = "Payout Destination"

        items.append(AdminTransactionItem(
            id=r["id"],
            user_id=r["user_id"],
            user_email=r["user_email"],
            user_name=r["user_name"],
            transaction_type=r["transaction_type"],
            amount=amount,
            balance_impact=impact,
            associated_resource=assoc,
            description=desc,
            status=r["status"] or "completed",
            timestamp=r["created_at"]
        ))

    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_TRANSACTIONS",
        details=f"Listed credit transactions page={page}, limit={limit}",
        ip_address=client_ip
    )

    return AdminTransactionListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more
    )


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def get_admin_audit_logs(
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    admin: dict = Depends(get_current_admin_user)
):
    """
    Returns administrative access and governance audit logs.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if action and action.strip() and action.strip().upper() != "ALL":
        conditions.append("UPPER(action) = ?")
        params.append(action.strip().upper())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor.execute(f"SELECT COUNT(*) AS total FROM admin_audit_logs {where_clause}", params)
    total = cursor.fetchone()["total"] or 0

    offset = (page - 1) * limit
    data_query = f"""
        SELECT id, admin_user_id, admin_email, action, target_resource, details, ip_address, created_at
        FROM admin_audit_logs
        {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(data_query, list(params) + [limit, offset])
    rows = cursor.fetchall()

    items = [
        AdminAuditLogItem(
            id=r["id"],
            admin_user_id=r["admin_user_id"],
            admin_email=r["admin_email"],
            action=r["action"],
            target_resource=r["target_resource"],
            details=r["details"],
            ip_address=r["ip_address"],
            timestamp=r["created_at"]
        ) for r in rows
    ]

    return AdminAuditLogListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(items)) < total
    )
