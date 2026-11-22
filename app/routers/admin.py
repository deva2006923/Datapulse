import json
import logging
import os
import re
import datetime
import threading
import uuid
from typing import Optional, List, Any, Dict, Tuple, Set
from fastapi import HTTPException, status, Depends, Query, Request, UploadFile, File, Form
from app.routers import TrailingSlashRouter
from app.config import settings
from app.database import get_db_connection
from app.auth import get_current_admin_user, log_admin_audit
from app.services.evaluation import parse_and_evaluate_csv
from app.services.storage import (
    DATASET_ID_REGEX,
    get_existing_dataset_ids,
    persist_dataset,
    delete_dataset_storage,
    dataset_table_exists,
    get_dataset_row_count,
    get_dataset_columns,
    get_dataset_table_name,
)
from app.schemas import (
    AdminOverviewResponse,
    AdminActivityItem,
    AdminAnalyticsResponse,
    AdminAnalyticsKpis,
    AdminTrendPoint,
    AdminQueryTrendPoint,
    AdminCreditTrendPoint,
    AdminActiveUserRank,
    AdminContributorRank,
    AdminQueriedDatasetRank,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserDetailResponse,
    AdminUserDatasetItem,
    AdminDatasetItem,
    AdminDatasetListResponse,
    AdminDatasetDetailResponse,
    AdminDatasetImportResponse,
    AdminQueryItem,
    AdminQueryListResponse,
    AdminTransactionItem,
    AdminTransactionListResponse,
    AdminAuditLogItem,
    AdminAuditLogListResponse,
    AdminTimelineItem,
    AdminTimelineResponse,
)

logger = logging.getLogger(__name__)
router = TrailingSlashRouter(prefix="/admin", tags=["Admin Dashboard"])
_dataset_import_lock = threading.Lock()
_VALID_EVAL_STATUSES = {"completed", "pending", "processing", "failed"}

OWNER_EARNING_TYPES = (
    "upload_reward",
    "quality_reward",
    "reward",
    "improvement_reward",
    "query_reward",
    "unlock_royalty",
)

DATASET_ID_RE = re.compile(r"\b(ds_[a-zA-Z0-9_-]+)\b")
QUERY_ID_RE = re.compile(r"\b(qry_[a-zA-Z0-9_-]+)\b")


def _norm_date_sql(col: str) -> str:
    """Normalizes both 'YYYY-MM-DD HH:MM:SS' and 'YYYY-MM-DDTHH:MM:SS' to YYYY-MM-DD for consistent UTC date comparisons."""
    return f"SUBSTR(REPLACE(COALESCE({col}, ''), ' ', 'T'), 1, 10)"


def _norm_ts_sql(col: str) -> str:
    """Normalizes SQLite CURRENT_TIMESTAMP space-separated timestamps to ISO 'T' form for deterministic chronological sorting."""
    return f"REPLACE(COALESCE({col}, ''), ' ', 'T')"


def _bucket_sql(col: str, granularity: str) -> str:
    date_expr = _norm_date_sql(col)
    if granularity == "monthly":
        return f"SUBSTR({date_expr}, 1, 7)"
    if granularity == "weekly":
        return f"strftime('%Y-W%W', {date_expr})"
    return date_expr


def _parse_iso_date(date_str: Optional[str]) -> Optional[datetime.date]:
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()[:10]
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def _resolve_date_window(
    range_key: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Returns (normalized_range, cur_start, cur_end, prev_start, prev_end, comparison_label)
    using UTC dates in YYYY-MM-DD format.
    """
    rk = (range_key or "all").strip().lower()
    today = datetime.datetime.utcnow().date()

    if rk in ("7d", "30d", "90d"):
        days = int(rk[:-1])
        cur_end = today
        cur_start = today - datetime.timedelta(days=days - 1)
        prev_end = cur_start - datetime.timedelta(days=1)
        prev_start = prev_end - datetime.timedelta(days=days - 1)
        return (
            rk,
            cur_start.isoformat(),
            cur_end.isoformat(),
            prev_start.isoformat(),
            prev_end.isoformat(),
            f"vs prior {days} days",
        )

    if rk == "custom" or start_date or end_date:
        s_dt = _parse_iso_date(start_date)
        e_dt = _parse_iso_date(end_date)
        if s_dt and e_dt and s_dt > e_dt:
            s_dt, e_dt = e_dt, s_dt
        if s_dt and e_dt:
            span = (e_dt - s_dt).days + 1
            prev_end = s_dt - datetime.timedelta(days=1)
            prev_start = prev_end - datetime.timedelta(days=span - 1)
            return (
                "custom",
                s_dt.isoformat(),
                e_dt.isoformat(),
                prev_start.isoformat(),
                prev_end.isoformat(),
                f"vs prior {span}d period",
            )
        return (
            "custom",
            s_dt.isoformat() if s_dt else None,
            e_dt.isoformat() if e_dt else None,
            None,
            None,
            None,
        )

    # All-time window: no date restriction on main totals, compare last 30d vs prior 30d for growth indicator
    cur_end_30 = today
    cur_start_30 = today - datetime.timedelta(days=29)
    prev_end_30 = cur_start_30 - datetime.timedelta(days=1)
    prev_start_30 = prev_end_30 - datetime.timedelta(days=29)
    return (
        "all",
        None,
        None,
        prev_start_30.isoformat(),
        prev_end_30.isoformat(),
        "30d momentum",
    )


def _append_date_conditions(
    conditions: List[str],
    params: List[Any],
    col: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> None:
    date_expr = _norm_date_sql(col)
    if start_date and start_date.strip():
        conditions.append(f"{date_expr} >= ?")
        params.append(start_date.strip()[:10])
    if end_date and end_date.strip():
        conditions.append(f"{date_expr} <= ?")
        params.append(end_date.strip()[:10])


def _pct_delta(current: int, previous: int) -> Optional[float]:
    if previous == 0:
        if current == 0:
            return 0.0
        return 100.0
    return round(((current - previous) / previous) * 100.0, 1)


def _extract_resource_ids(description: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extracts (associated_resource_label, dataset_id, query_id) from transaction description."""
    desc = description or ""
    ds_match = DATASET_ID_RE.search(desc)
    q_match = QUERY_ID_RE.search(desc)
    ds_id = ds_match.group(1) if ds_match else None
    q_id = q_match.group(1) if q_match else None

    low = desc.lower()
    if ds_id or "dataset" in low:
        assoc = "Dataset Asset"
    elif q_id or "query" in low:
        assoc = "Query Engine"
    elif "redeem" in low:
        assoc = "Payout Redemption"
    elif "welcome" in low or "bonus" in low:
        assoc = "Account Onboarding"
    elif "refund" in low:
        assoc = "Credit Refund"
    else:
        assoc = "Account Ledger"
    return assoc, ds_id, q_id


def _batch_dataset_names(cursor, dataset_ids: Set[str]) -> Dict[str, str]:
    if not dataset_ids:
        return {}
    placeholders = ",".join("?" for _ in dataset_ids)
    cursor.execute(f"SELECT id, name FROM datasets WHERE id IN ({placeholders})", list(dataset_ids))
    return {r["id"]: r["name"] for r in cursor.fetchall()}


def _batch_dataset_rewards_and_versions(
    cursor,
    dataset_ids: List[str],
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
    """
    Single-pass batch loader (no N+1) for:
      - Per-dataset reward breakdown (basic_upload_reward, quality_reward, improvement_rewards)
      - Per-dataset version history list
      - Per-dataset query usage count
    """
    rewards_map: Dict[str, Dict[str, int]] = {
        ds_id: {"basic": 0, "quality": 0, "improvement": 0} for ds_id in dataset_ids
    }
    versions_map: Dict[str, List[Dict[str, Any]]] = {ds_id: [] for ds_id in dataset_ids}
    query_counts_map: Dict[str, int] = {ds_id: 0 for ds_id in dataset_ids}

    if not dataset_ids:
        return rewards_map, versions_map, query_counts_map

    placeholders = ",".join("?" for _ in dataset_ids)

    # 1. Versions in a single query
    cursor.execute(
        f"""
        SELECT dataset_id, version, quality_score, relevance_score, overall_score,
               delta_score, credits_awarded, changes_summary, created_at
        FROM dataset_versions
        WHERE dataset_id IN ({placeholders})
        ORDER BY {_norm_ts_sql('created_at')} DESC, id DESC
        """,
        dataset_ids,
    )
    for v in cursor.fetchall():
        ds_id = v["dataset_id"]
        v_dict = dict(v)
        versions_map.setdefault(ds_id, []).append(v_dict)
        if ds_id in rewards_map:
            rewards_map[ds_id]["improvement"] += int(v["credits_awarded"] or 0)

    # 2. Query counts in a single grouped query
    cursor.execute(
        f"""
        SELECT dataset_id, COUNT(*) AS cnt
        FROM queries
        WHERE dataset_id IN ({placeholders})
        GROUP BY dataset_id
        """,
        dataset_ids,
    )
    for q in cursor.fetchall():
        query_counts_map[q["dataset_id"]] = int(q["cnt"] or 0)

    # 3. Credit transaction rewards (upload_reward, quality_reward, legacy reward) for these datasets
    cursor.execute(
        f"""
        SELECT DISTINCT d.user_id FROM datasets d WHERE d.id IN ({placeholders})
        """,
        dataset_ids,
    )
    owner_ids = [r["user_id"] for r in cursor.fetchall()]
    if owner_ids:
        owner_ph = ",".join("?" for _ in owner_ids)
        cursor.execute(
            f"""
            SELECT transaction_type, amount, description
            FROM credit_transactions
            WHERE user_id IN ({owner_ph})
              AND LOWER(transaction_type) IN ('upload_reward', 'quality_reward', 'reward')
              AND amount > 0
            """,
            owner_ids,
        )
        ds_set = set(dataset_ids)
        for tx in cursor.fetchall():
            desc = tx["description"] or ""
            m = DATASET_ID_RE.search(desc)
            if not m:
                continue
            ds_id = m.group(1)
            if ds_id not in ds_set:
                continue
            tt = (tx["transaction_type"] or "").lower()
            amt = int(tx["amount"] or 0)
            if tt == "upload_reward":
                rewards_map[ds_id]["basic"] += amt
            elif tt == "quality_reward":
                rewards_map[ds_id]["quality"] += amt
            elif tt == "reward":
                # Legacy combined upload+quality reward (50 base + remainder quality)
                base_part = min(50, amt)
                rewards_map[ds_id]["basic"] += base_part
                rewards_map[ds_id]["quality"] += max(0, amt - base_part)

    # Fallback from evaluations table if legacy datasets had credits_awarded without ds_id in tx description
    cursor.execute(
        f"""
        SELECT dataset_id, credits_awarded
        FROM evaluations
        WHERE dataset_id IN ({placeholders}) AND credits_awarded > 0
        """,
        dataset_ids,
    )
    for ev in cursor.fetchall():
        ds_id = ev["dataset_id"]
        if ds_id in rewards_map and rewards_map[ds_id]["basic"] == 0 and rewards_map[ds_id]["quality"] == 0:
            total_ev = int(ev["credits_awarded"] or 0)
            base_part = min(50, total_ev)
            rewards_map[ds_id]["basic"] = base_part
            rewards_map[ds_id]["quality"] = max(0, total_ev - base_part)

    return rewards_map, versions_map, query_counts_map


def _count_active_users(
    cursor,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> int:
    """Counts distinct users with at least one query, dataset upload, improvement, or unlock in the window."""
    q_conds, q_params = [], []
    d_conds, d_params = [], []
    v_conds, v_params = [], []
    u_conds, u_params = [], []

    _append_date_conditions(q_conds, q_params, "created_at", start_date, end_date)
    _append_date_conditions(d_conds, d_params, "created_at", start_date, end_date)
    _append_date_conditions(v_conds, v_params, "created_at", start_date, end_date)
    _append_date_conditions(u_conds, u_params, "created_at", start_date, end_date)

    q_w = f"WHERE {' AND '.join(q_conds)}" if q_conds else ""
    d_w = f"WHERE {' AND '.join(d_conds)}" if d_conds else ""
    v_w = f"WHERE {' AND '.join(v_conds)}" if v_conds else ""
    u_w = f"WHERE {' AND '.join(u_conds)}" if u_conds else ""

    sql = f"""
        SELECT COUNT(DISTINCT user_id) AS total
        FROM (
            SELECT user_id FROM queries {q_w}
            UNION
            SELECT user_id FROM datasets {d_w}
            UNION
            SELECT user_id FROM dataset_versions {v_w}
            UNION
            SELECT user_id FROM dataset_unlocks {u_w}
        ) active_u
        WHERE user_id IS NOT NULL
    """
    cursor.execute(sql, q_params + d_params + v_params + u_params)
    row = cursor.fetchone()
    return int(row["total"] or 0) if row else 0


@router.get("/overview", response_model=AdminOverviewResponse)
def get_admin_overview(
    request: Request,
    range: Optional[str] = Query("all", description="Date range preset: 7d, 30d, 90d, all, custom"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Returns platform-wide summary metrics and recent platform activities.
    Requires verified administrator authorization.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    _, cur_start, cur_end, _, _, _ = _resolve_date_window(range, start_date, end_date)

    # 1. Users
    u_conds, u_params = [], []
    _append_date_conditions(u_conds, u_params, "created_at", cur_start, cur_end)
    u_where = f"WHERE {' AND '.join(u_conds)}" if u_conds else ""
    cursor.execute(f"SELECT COUNT(*) AS total FROM users {u_where}", u_params)
    total_users = int(cursor.fetchone()["total"] or 0)

    active_users = _count_active_users(cursor, cur_start, cur_end)

    # 2. Datasets
    d_conds, d_params = [], []
    _append_date_conditions(d_conds, d_params, "created_at", cur_start, cur_end)
    d_where = f"WHERE {' AND '.join(d_conds)}" if d_conds else ""
    cursor.execute(f"SELECT COUNT(*) AS total FROM datasets {d_where}", d_params)
    total_datasets = int(cursor.fetchone()["total"] or 0)

    # 3. Queries
    q_conds, q_params = [], []
    _append_date_conditions(q_conds, q_params, "created_at", cur_start, cur_end)
    q_where = f"WHERE {' AND '.join(q_conds)}" if q_conds else ""
    cursor.execute(
        f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN UPPER(COALESCE(status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END) AS ok
        FROM queries {q_where}
        """,
        q_params,
    )
    q_row = cursor.fetchone()
    total_queries = int(q_row["total"] or 0)
    total_queries_successful = int(q_row["ok"] or 0)
    total_queries_failed = total_queries - total_queries_successful
    query_success_rate = round((total_queries_successful / total_queries) * 100.0, 1) if total_queries > 0 else 100.0

    # 4. Credits
    t_conds, t_params = [], []
    _append_date_conditions(t_conds, t_params, "created_at", cur_start, cur_end)
    t_where = f"WHERE {' AND '.join(t_conds)}" if t_conds else ""
    cursor.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS issued,
            COALESCE(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END)), 0) AS spent,
            COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%refund%' AND amount > 0 THEN amount ELSE 0 END), 0) AS refunded
        FROM credit_transactions {t_where}
        """,
        t_params,
    )
    t_row = cursor.fetchone()
    total_credits_issued = int(t_row["issued"] or 0)
    total_credits_spent = int(t_row["spent"] or 0)
    total_credits_refunded = int(t_row["refunded"] or 0)
    net_credit_movement = total_credits_issued - total_credits_spent

    # Authoritative current liability (sum of user balances)
    cursor.execute("SELECT COALESCE(SUM(credits), 0) AS total FROM users")
    net_credit_liability = int(cursor.fetchone()["total"] or 0)

    # 5. Recent platform activity feed (normalized chronological ordering)
    activity_items: List[AdminActivityItem] = []

    cursor.execute(f"SELECT id, email, full_name, created_at FROM users ORDER BY {_norm_ts_sql('created_at')} DESC LIMIT 6")
    for r in cursor.fetchall():
        activity_items.append(AdminActivityItem(
            id=f"act_reg_{r['id']}",
            type="USER_REGISTER",
            description=f"User registered: {r['full_name']}",
            user_id=r["id"],
            user_email=r["email"],
            status="SUCCESS",
            timestamp=r["created_at"],
        ))

    cursor.execute(f"""
        SELECT d.id, d.name, d.rows_count, d.created_at, u.id AS user_id, u.email AS user_email
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        ORDER BY {_norm_ts_sql('d.created_at')} DESC LIMIT 6
    """)
    for r in cursor.fetchall():
        activity_items.append(AdminActivityItem(
            id=f"act_ds_{r['id']}",
            type="DATASET_UPLOAD",
            description=f"Dataset uploaded: '{r['name']}' ({r['rows_count']} rows)",
            user_id=r["user_id"],
            user_email=r["user_email"],
            dataset_id=r["id"],
            status="SUCCESS",
            timestamp=r["created_at"],
        ))

    cursor.execute(f"""
        SELECT q.id, q.query_text, q.dataset_id, q.dataset_name, q.status, q.created_at, u.id AS user_id, u.email AS user_email
        FROM queries q
        JOIN users u ON q.user_id = u.id
        ORDER BY {_norm_ts_sql('q.created_at')} DESC LIMIT 6
    """)
    for r in cursor.fetchall():
        ds_name = r["dataset_name"] or "Cross-Catalog"
        q_snippet = (r["query_text"][:56] + "...") if len(r["query_text"]) > 56 else r["query_text"]
        activity_items.append(AdminActivityItem(
            id=f"act_qry_{r['id']}",
            type="QUERY_EXECUTION",
            description=f"Query on {ds_name}: \"{q_snippet}\"",
            user_id=r["user_id"],
            user_email=r["user_email"],
            dataset_id=r["dataset_id"],
            status=r["status"] or "SUCCESS",
            timestamp=r["created_at"],
        ))

    cursor.execute(f"""
        SELECT t.id, t.amount, t.description, t.transaction_type, t.created_at, u.id AS user_id, u.email AS user_email
        FROM credit_transactions t
        JOIN users u ON t.user_id = u.id
        ORDER BY {_norm_ts_sql('t.created_at')} DESC LIMIT 6
    """)
    for r in cursor.fetchall():
        impact = f"+{r['amount']}" if r["amount"] > 0 else f"{r['amount']}"
        _, ds_id, _ = _extract_resource_ids(r["description"] or "")
        activity_items.append(AdminActivityItem(
            id=f"act_tx_{r['id']}",
            type="CREDIT_TRANSACTION",
            description=f"{r['description']} ({impact} cr)",
            user_id=r["user_id"],
            user_email=r["user_email"],
            dataset_id=ds_id,
            status="SUCCESS",
            timestamp=r["created_at"],
        ))

    activity_items.sort(key=lambda a: (a.timestamp or "").replace(" ", "T"), reverse=True)
    recent_activity = activity_items[:12]

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_OVERVIEW",
        details=f"Platform overview requested (range={range})",
        ip_address=client_ip,
    )

    return AdminOverviewResponse(
        total_users=total_users,
        active_users=active_users,
        total_datasets=total_datasets,
        total_queries=total_queries,
        total_queries_successful=total_queries_successful,
        total_queries_failed=total_queries_failed,
        query_success_rate=query_success_rate,
        total_credits_issued=total_credits_issued,
        total_credits_spent=total_credits_spent,
        total_credits_refunded=total_credits_refunded,
        net_credit_movement=net_credit_movement,
        net_credit_liability=net_credit_liability,
        total_credits_in_circulation=net_credit_liability,
        recent_activity=recent_activity,
    )


@router.get("/analytics", response_model=AdminAnalyticsResponse)
def get_admin_analytics(
    request: Request,
    range: Optional[str] = Query("all", description="Date range preset: 7d, 30d, 90d, all, custom"),
    start_date: Optional[str] = Query(None, description="Custom start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Custom end date YYYY-MM-DD"),
    granularity: Optional[str] = Query("daily", description="Time bucket granularity: daily, weekly, monthly"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Comprehensive platform analytics powering KPI comparison deltas, time-series trends,
    and user/dataset leaderboards. Backed exclusively by real database records.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    gran = (granularity or "daily").strip().lower()
    if gran not in ("daily", "weekly", "monthly"):
        gran = "daily"

    norm_range, cur_start, cur_end, prev_start, prev_end, comparison_label = _resolve_date_window(
        range, start_date, end_date
    )

    # --- KPI totals (all-time baselines + selected period counts) ---
    cursor.execute("SELECT COUNT(*) AS total, COALESCE(SUM(credits), 0) AS liability FROM users")
    u_all = cursor.fetchone()
    total_users_all = int(u_all["total"] or 0)
    net_credit_liability = int(u_all["liability"] or 0)

    cursor.execute("SELECT COUNT(*) AS total FROM datasets")
    total_datasets_all = int(cursor.fetchone()["total"] or 0)

    def _window_metrics(w_start: Optional[str], w_end: Optional[str]) -> Dict[str, int]:
        uc, up = [], []
        _append_date_conditions(uc, up, "created_at", w_start, w_end)
        uw = f"WHERE {' AND '.join(uc)}" if uc else ""
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM users {uw}", up)
        users_cnt = int(cursor.fetchone()["cnt"] or 0)

        dc, dp = [], []
        _append_date_conditions(dc, dp, "created_at", w_start, w_end)
        dw = f"WHERE {' AND '.join(dc)}" if dc else ""
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM datasets {dw}", dp)
        ds_cnt = int(cursor.fetchone()["cnt"] or 0)

        qc, qp = [], []
        _append_date_conditions(qc, qp, "created_at", w_start, w_end)
        qw = f"WHERE {' AND '.join(qc)}" if qc else ""
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN UPPER(COALESCE(status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END), 0) AS ok
            FROM queries {qw}
            """,
            qp,
        )
        qr = cursor.fetchone()
        q_total = int(qr["total"] or 0)
        q_ok = int(qr["ok"] or 0)

        tc, tp = [], []
        _append_date_conditions(tc, tp, "created_at", w_start, w_end)
        tw = f"WHERE {' AND '.join(tc)}" if tc else ""
        owner_types_sql = ",".join(f"'{t}'" for t in OWNER_EARNING_TYPES)
        cursor.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS issued,
                COALESCE(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END)), 0) AS spent,
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%refund%' AND amount > 0 THEN amount ELSE 0 END), 0) AS refunded,
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) IN ({owner_types_sql}) AND amount > 0 THEN amount ELSE 0 END), 0) AS owner_earned,
                COALESCE(ABS(SUM(CASE WHEN LOWER(transaction_type) = 'query_fee' THEN amount ELSE 0 END)), 0) AS query_fees
            FROM credit_transactions {tw}
            """,
            tp,
        )
        tr = cursor.fetchone()
        return {
            "users": users_cnt,
            "active_users": _count_active_users(cursor, w_start, w_end),
            "datasets": ds_cnt,
            "queries": q_total,
            "queries_ok": q_ok,
            "queries_failed": q_total - q_ok,
            "issued": int(tr["issued"] or 0),
            "spent": int(tr["spent"] or 0),
            "refunded": int(tr["refunded"] or 0),
            "owner_earned": int(tr["owner_earned"] or 0),
            "query_fees": int(tr["query_fees"] or 0),
        }

    cur_m = _window_metrics(cur_start, cur_end)

    # Comparison deltas
    users_delta = active_delta = ds_delta = q_delta = issued_delta = spent_delta = None
    if prev_start and prev_end:
        if norm_range == "all":
            today = datetime.datetime.utcnow().date()
            c30_start = (today - datetime.timedelta(days=29)).isoformat()
            c30_end = today.isoformat()
            comp_cur = _window_metrics(c30_start, c30_end)
            comp_prev = _window_metrics(prev_start, prev_end)
        else:
            comp_cur = cur_m
            comp_prev = _window_metrics(prev_start, prev_end)
        users_delta = _pct_delta(comp_cur["users"], comp_prev["users"])
        active_delta = _pct_delta(comp_cur["active_users"], comp_prev["active_users"])
        ds_delta = _pct_delta(comp_cur["datasets"], comp_prev["datasets"])
        q_delta = _pct_delta(comp_cur["queries"], comp_prev["queries"])
        issued_delta = _pct_delta(comp_cur["issued"], comp_prev["issued"])
        spent_delta = _pct_delta(comp_cur["spent"], comp_prev["spent"])

    success_rate = round((cur_m["queries_ok"] / cur_m["queries"]) * 100.0, 1) if cur_m["queries"] > 0 else 100.0

    # --- Time-series Trends ---
    # 1. User Registration Trend
    u_conds, u_params = [], []
    _append_date_conditions(u_conds, u_params, "created_at", cur_start, cur_end)
    u_w = f"WHERE {' AND '.join(u_conds)}" if u_conds else ""
    u_bucket = _bucket_sql("created_at", gran)
    cursor.execute(
        f"""
        SELECT {u_bucket} AS bucket, COUNT(*) AS cnt
        FROM users {u_w}
        GROUP BY bucket
        ORDER BY bucket ASC
        """,
        u_params,
    )
    user_reg_trend = [
        AdminTrendPoint(bucket=r["bucket"], count=int(r["cnt"] or 0))
        for r in cursor.fetchall() if r["bucket"]
    ]

    # 2. Dataset Upload Trend
    d_conds, d_params = [], []
    _append_date_conditions(d_conds, d_params, "created_at", cur_start, cur_end)
    d_w = f"WHERE {' AND '.join(d_conds)}" if d_conds else ""
    d_bucket = _bucket_sql("created_at", gran)
    cursor.execute(
        f"""
        SELECT {d_bucket} AS bucket, COUNT(*) AS cnt
        FROM datasets {d_w}
        GROUP BY bucket
        ORDER BY bucket ASC
        """,
        d_params,
    )
    dataset_upload_trend = [
        AdminTrendPoint(bucket=r["bucket"], count=int(r["cnt"] or 0))
        for r in cursor.fetchall() if r["bucket"]
    ]

    # 3. Query Activity Trend (successful vs failed)
    q_conds, q_params = [], []
    _append_date_conditions(q_conds, q_params, "created_at", cur_start, cur_end)
    q_w = f"WHERE {' AND '.join(q_conds)}" if q_conds else ""
    q_bucket = _bucket_sql("created_at", gran)
    cursor.execute(
        f"""
        SELECT {q_bucket} AS bucket,
               COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END), 0) AS ok,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(status, 'SUCCESS')) != 'SUCCESS' THEN 1 ELSE 0 END), 0) AS failed
        FROM queries {q_w}
        GROUP BY bucket
        ORDER BY bucket ASC
        """,
        q_params,
    )
    query_activity_trend = [
        AdminQueryTrendPoint(
            bucket=r["bucket"],
            total=int(r["total"] or 0),
            successful=int(r["ok"] or 0),
            failed=int(r["failed"] or 0),
        )
        for r in cursor.fetchall() if r["bucket"]
    ]

    # 4. Credit Movement Trend (awarded, spent, refunded)
    t_conds, t_params = [], []
    _append_date_conditions(t_conds, t_params, "created_at", cur_start, cur_end)
    t_w = f"WHERE {' AND '.join(t_conds)}" if t_conds else ""
    t_bucket = _bucket_sql("created_at", gran)
    cursor.execute(
        f"""
        SELECT {t_bucket} AS bucket,
               COALESCE(SUM(CASE WHEN amount > 0 AND LOWER(transaction_type) NOT LIKE '%refund%' THEN amount ELSE 0 END), 0) AS awarded,
               COALESCE(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END)), 0) AS spent,
               COALESCE(SUM(CASE WHEN amount > 0 AND LOWER(transaction_type) LIKE '%refund%' THEN amount ELSE 0 END), 0) AS refunded
        FROM credit_transactions {t_w}
        GROUP BY bucket
        ORDER BY bucket ASC
        """,
        t_params,
    )
    credit_movement_trend = []
    for r in cursor.fetchall():
        if not r["bucket"]:
            continue
        aw = int(r["awarded"] or 0)
        sp = int(r["spent"] or 0)
        rf = int(r["refunded"] or 0)
        credit_movement_trend.append(AdminCreditTrendPoint(
            bucket=r["bucket"],
            awarded=aw,
            spent=sp,
            refunded=rf,
            net=(aw + rf) - sp,
        ))

    # --- Leaderboards (scoped to selected date window) ---
    # 5. Most Active Users (by query executions)
    aq_conds, aq_params = [], []
    _append_date_conditions(aq_conds, aq_params, "q.created_at", cur_start, cur_end)
    aq_w = f"WHERE {' AND '.join(aq_conds)}" if aq_conds else ""
    cursor.execute(
        f"""
        SELECT u.id AS user_id, u.full_name, u.email,
               COUNT(q.id) AS query_count,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(q.status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END), 0) AS ok,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(q.status, 'SUCCESS')) != 'SUCCESS' THEN 1 ELSE 0 END), 0) AS failed,
               MAX({_norm_ts_sql('q.created_at')}) AS last_activity
        FROM queries q
        JOIN users u ON q.user_id = u.id
        {aq_w}
        GROUP BY u.id, u.full_name, u.email
        ORDER BY query_count DESC, last_activity DESC, u.id ASC
        LIMIT 8
        """,
        aq_params,
    )
    most_active_users = [
        AdminActiveUserRank(
            user_id=r["user_id"],
            full_name=r["full_name"],
            email=r["email"],
            query_count=int(r["query_count"] or 0),
            successful_queries=int(r["ok"] or 0),
            failed_queries=int(r["failed"] or 0),
            last_activity=r["last_activity"],
        )
        for r in cursor.fetchall()
    ]

    # 6. Most Contributing Users (by dataset uploads)
    cd_conds, cd_params = [], []
    _append_date_conditions(cd_conds, cd_params, "d.created_at", cur_start, cur_end)
    cd_w = f"WHERE {' AND '.join(cd_conds)}" if cd_conds else ""
    cursor.execute(
        f"""
        SELECT u.id AS user_id, u.full_name, u.email,
               COUNT(d.id) AS dataset_count,
               COALESCE(SUM(d.rows_count), 0) AS total_rows,
               AVG(e.overall_score) AS avg_quality
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        {cd_w}
        GROUP BY u.id, u.full_name, u.email
        ORDER BY dataset_count DESC, total_rows DESC, u.id ASC
        LIMIT 8
        """,
        cd_params,
    )
    most_contributing_users = [
        AdminContributorRank(
            user_id=r["user_id"],
            full_name=r["full_name"],
            email=r["email"],
            dataset_count=int(r["dataset_count"] or 0),
            total_rows=int(r["total_rows"] or 0),
            avg_quality_score=round(float(r["avg_quality"]), 1) if r["avg_quality"] is not None else None,
        )
        for r in cursor.fetchall()
    ]

    # 7. Most Queried Datasets
    qd_conds, qd_params = ["q.dataset_id IS NOT NULL"], []
    _append_date_conditions(qd_conds, qd_params, "q.created_at", cur_start, cur_end)
    qd_w = f"WHERE {' AND '.join(qd_conds)}"
    cursor.execute(
        f"""
        SELECT q.dataset_id,
               COALESCE(d.name, MAX(q.dataset_name), q.dataset_id) AS dataset_name,
               COALESCE(d.domain, 'general') AS domain,
               d.user_id AS owner_id,
               u.full_name AS owner_name,
               COUNT(q.id) AS query_count,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(q.status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END), 0) AS ok,
               (SELECT COUNT(*) FROM dataset_unlocks du WHERE du.dataset_id = q.dataset_id) AS unlock_count,
               e.overall_score AS quality_score
        FROM queries q
        LEFT JOIN datasets d ON q.dataset_id = d.id
        LEFT JOIN users u ON d.user_id = u.id
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        {qd_w}
        GROUP BY q.dataset_id, d.name, d.domain, d.user_id, u.full_name, e.overall_score
        ORDER BY query_count DESC, ok DESC, q.dataset_id ASC
        LIMIT 8
        """,
        qd_params,
    )
    most_queried_datasets = [
        AdminQueriedDatasetRank(
            dataset_id=r["dataset_id"],
            dataset_name=r["dataset_name"],
            domain=r["domain"],
            owner_id=r["owner_id"],
            owner_name=r["owner_name"],
            query_count=int(r["query_count"] or 0),
            successful_queries=int(r["ok"] or 0),
            unlock_count=int(r["unlock_count"] or 0),
            quality_score=round(float(r["quality_score"]), 1) if r["quality_score"] is not None else None,
        )
        for r in cursor.fetchall()
    ]

    data_limitations = [
        "Session sign-in events are derived from persisted session timestamps; client IP and user-agent were not historically stored for regular logins.",
        "Credit refunds are tracked dynamically from credit_transactions; 0 indicates no refund transactions have been emitted in the database.",
    ]

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_ANALYTICS",
        details=f"Analytics requested range={norm_range}, granularity={gran}",
        ip_address=client_ip,
    )

    return AdminAnalyticsResponse(
        range=norm_range,
        start_date=cur_start,
        end_date=cur_end,
        granularity=gran,
        comparison_label=comparison_label,
        kpis=AdminAnalyticsKpis(
            total_users=total_users_all if norm_range == "all" else cur_m["users"],
            users_in_period=cur_m["users"],
            users_delta_pct=users_delta,
            active_users=cur_m["active_users"],
            active_users_delta_pct=active_delta,
            total_datasets=total_datasets_all if norm_range == "all" else cur_m["datasets"],
            datasets_in_period=cur_m["datasets"],
            datasets_delta_pct=ds_delta,
            total_queries=cur_m["queries"],
            queries_successful=cur_m["queries_ok"],
            queries_failed=cur_m["queries_failed"],
            query_success_rate=success_rate,
            queries_delta_pct=q_delta,
            total_credits_issued=cur_m["issued"],
            total_credits_spent=cur_m["spent"],
            total_credits_refunded=cur_m["refunded"],
            net_credit_movement=cur_m["issued"] - cur_m["spent"],
            net_credit_liability=net_credit_liability,
            total_credits_in_circulation=net_credit_liability,
            credits_issued_delta_pct=issued_delta,
            credits_spent_delta_pct=spent_delta,
            credits_earned_by_owners=cur_m["owner_earned"],
            query_fees_collected=cur_m["query_fees"],
        ),
        user_registration_trend=user_reg_trend,
        dataset_upload_trend=dataset_upload_trend,
        query_activity_trend=query_activity_trend,
        credit_movement_trend=credit_movement_trend,
        most_active_users=most_active_users,
        most_contributing_users=most_contributing_users,
        most_queried_datasets=most_queried_datasets,
        data_limitations=data_limitations,
    )


@router.get("/users", response_model=AdminUserListResponse)
def get_admin_users(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by user name, email, or user ID"),
    role: Optional[str] = Query(None, description="Filter by role: admin, user, all"),
    activity: Optional[str] = Query(None, description="Filter by activity: all, active, has_queries, has_datasets, inactive"),
    start_date: Optional[str] = Query(None, description="Start registration date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End registration date YYYY-MM-DD"),
    sort_by: Optional[str] = Query("created_at", description="Sort by: created_at, last_activity, credits, reputation_score, full_name, queries_count, datasets_count"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc, desc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Searchable, filterable, paginated directory of registered users for administrators.
    Computes datasets_count, queries_count, and last_activity without N+1 queries.
    Never exposes passwords, tokens, or hashes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(u.full_name) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(u.id) LIKE ?)")
        params.extend([term, term, term])

    if role and role.strip() and role.strip().lower() != "all":
        if role.strip().lower() == "admin":
            conditions.append("u.is_admin = 1")
        elif role.strip().lower() == "user":
            conditions.append("u.is_admin = 0")

    if activity and activity.strip() and activity.strip().lower() != "all":
        act = activity.strip().lower()
        if act == "has_queries":
            conditions.append("EXISTS (SELECT 1 FROM queries q WHERE q.user_id = u.id)")
        elif act == "has_datasets":
            conditions.append("EXISTS (SELECT 1 FROM datasets d WHERE d.user_id = u.id)")
        elif act == "active":
            conditions.append("(EXISTS (SELECT 1 FROM queries q WHERE q.user_id = u.id) OR EXISTS (SELECT 1 FROM datasets d WHERE d.user_id = u.id))")
        elif act in ("inactive", "no_activity"):
            conditions.append("(NOT EXISTS (SELECT 1 FROM queries q WHERE q.user_id = u.id) AND NOT EXISTS (SELECT 1 FROM datasets d WHERE d.user_id = u.id))")

    _append_date_conditions(conditions, params, "u.created_at", start_date, end_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor.execute(f"SELECT COUNT(*) AS total FROM users u {where_clause}", params)
    total = int(cursor.fetchone()["total"] or 0)

    valid_sort_cols = {
        "created_at": _norm_ts_sql("u.created_at"),
        "last_activity": "last_activity",
        "credits": "u.credits",
        "reputation_score": "u.reputation_score",
        "full_name": "LOWER(u.full_name)",
        "queries_count": "queries_count",
        "datasets_count": "datasets_count",
    }
    col = valid_sort_cols.get(sort_by or "created_at", _norm_ts_sql("u.created_at"))
    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"

    offset = (page - 1) * limit
    data_query = f"""
        WITH user_activity AS (
            SELECT user_id, MAX({_norm_ts_sql('ts')}) AS last_ts
            FROM (
                SELECT user_id, created_at AS ts FROM queries
                UNION ALL
                SELECT user_id, created_at AS ts FROM datasets
                UNION ALL
                SELECT user_id, created_at AS ts FROM dataset_versions
                UNION ALL
                SELECT user_id, created_at AS ts FROM dataset_unlocks
                UNION ALL
                SELECT user_id, created_at AS ts FROM credit_transactions
            )
            GROUP BY user_id
        ),
        ds_counts AS (
            SELECT user_id, COUNT(*) AS cnt FROM datasets GROUP BY user_id
        ),
        q_counts AS (
            SELECT user_id, COUNT(*) AS cnt FROM queries GROUP BY user_id
        )
        SELECT u.id, u.email, u.full_name, u.credits, u.reputation_score, u.is_admin, u.created_at,
               COALESCE(dc.cnt, 0) AS datasets_count,
               COALESCE(qc.cnt, 0) AS queries_count,
               COALESCE(ua.last_ts, {_norm_ts_sql('u.created_at')}) AS last_activity
        FROM users u
        LEFT JOIN ds_counts dc ON dc.user_id = u.id
        LEFT JOIN q_counts qc ON qc.user_id = u.id
        LEFT JOIN user_activity ua ON ua.user_id = u.id
        {where_clause}
        ORDER BY {col} {order}, u.id {order}
        LIMIT ? OFFSET ?
    """
    cursor.execute(data_query, list(params) + [limit, offset])
    rows = cursor.fetchall()

    items = []
    for r in rows:
        ds_cnt = int(r["datasets_count"] or 0)
        q_cnt = int(r["queries_count"] or 0)
        is_adm = bool(r["is_admin"]) if "is_admin" in r.keys() else False
        is_act = (ds_cnt > 0 or q_cnt > 0)
        items.append(AdminUserItem(
            id=r["id"],
            email=r["email"],
            full_name=r["full_name"],
            credits=int(r["credits"] or 0),
            reputation_score=int(r["reputation_score"]) if "reputation_score" in r.keys() and r["reputation_score"] is not None else 50,
            is_admin=is_adm,
            account_status="Admin" if is_adm else ("Active" if is_act else "Inactive"),
            is_active=is_act,
            datasets_count=ds_cnt,
            queries_count=q_cnt,
            last_activity=r["last_activity"],
            created_at=r["created_at"],
        ))

    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_USERS",
        details=f"Listed users page={page}, limit={limit}, search={search}",
        ip_address=client_ip,
    )

    return AdminUserListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def get_admin_user_detail(
    user_id: str,
    request: Request,
    admin: dict = Depends(get_current_admin_user),
):
    """
    Returns complete user profile, uploaded datasets with quality ratings, reward breakdowns,
    versions, real DuckDB storage availability, query stats, and transaction summaries.
    Zero N+1 queries; never exposes passwords, hashes, or session credentials.
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
            detail=f"User with ID '{user_id}' not found.",
        )

    # Aggregates in compact queries
    cursor.execute("SELECT COUNT(*) AS total FROM datasets WHERE user_id = ?", (user_id,))
    total_datasets = int(cursor.fetchone()["total"] or 0)

    cursor.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END), 0) AS ok
        FROM queries
        WHERE user_id = ?
        """,
        (user_id,),
    )
    q_agg = cursor.fetchone()
    total_queries = int(q_agg["total"] or 0)
    total_queries_successful = int(q_agg["ok"] or 0)
    total_queries_failed = total_queries - total_queries_successful
    query_success_rate = round((total_queries_successful / total_queries) * 100.0, 1) if total_queries > 0 else 100.0

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS earned,
            COALESCE(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END)), 0) AS spent,
            COALESCE(SUM(CASE WHEN amount > 0 AND LOWER(transaction_type) LIKE '%refund%' THEN amount ELSE 0 END), 0) AS refunded
        FROM credit_transactions
        WHERE user_id = ?
        """,
        (user_id,),
    )
    tx_agg = cursor.fetchone()
    total_credits_earned = int(tx_agg["earned"] or 0)
    total_credits_spent = int(tx_agg["spent"] or 0)
    total_credits_refunded = int(tx_agg["refunded"] or 0)

    cursor.execute("SELECT COUNT(*) AS total FROM dataset_unlocks WHERE user_id = ?", (user_id,))
    total_unlocks = int(cursor.fetchone()["total"] or 0)

    cursor.execute("SELECT COUNT(*) AS total FROM dataset_versions WHERE user_id = ?", (user_id,))
    total_improvements = int(cursor.fetchone()["total"] or 0)

    # Last activity timestamp across all user tables
    cursor.execute(
        f"""
        SELECT MAX({_norm_ts_sql('ts')}) AS last_ts
        FROM (
            SELECT created_at AS ts FROM users WHERE id = ?
            UNION ALL
            SELECT created_at AS ts FROM datasets WHERE user_id = ?
            UNION ALL
            SELECT created_at AS ts FROM queries WHERE user_id = ?
            UNION ALL
            SELECT created_at AS ts FROM dataset_versions WHERE user_id = ?
            UNION ALL
            SELECT created_at AS ts FROM dataset_unlocks WHERE user_id = ?
            UNION ALL
            SELECT created_at AS ts FROM credit_transactions WHERE user_id = ?
        )
        """,
        (user_id, user_id, user_id, user_id, user_id, user_id),
    )
    last_act_row = cursor.fetchone()
    last_activity = last_act_row["last_ts"] if last_act_row else user_row["created_at"]

    # User's uploaded datasets (batch versions, rewards, queries, DuckDB availability -> zero N+1)
    cursor.execute(
        f"""
        SELECT d.id, d.name, d.filename, d.domain, d.rows_count, d.columns_count, d.unlock_price, d.created_at,
               e.overall_score AS quality_score
        FROM datasets d
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        WHERE d.user_id = ?
        ORDER BY {_norm_ts_sql('d.created_at')} DESC, d.id DESC
        """,
        (user_id,),
    )
    ds_rows = cursor.fetchall()
    ds_ids = [r["id"] for r in ds_rows]
    rewards_map, versions_map, query_counts_map = _batch_dataset_rewards_and_versions(cursor, ds_ids)
    existing_duckdb_ids = get_existing_dataset_ids()

    datasets = []
    for r in ds_rows:
        ds_id = r["id"]
        v_rows = versions_map.get(ds_id, [])
        rew = rewards_map.get(ds_id, {"basic": 0, "quality": 0, "improvement": 0})
        availability = "Available" if ds_id in existing_duckdb_ids else "Metadata Only"
        datasets.append(AdminUserDatasetItem(
            id=ds_id,
            name=r["name"],
            filename=r["filename"],
            domain=r["domain"],
            rows_count=r["rows_count"],
            columns_count=r["columns_count"],
            quality_score=round(float(r["quality_score"]), 1) if r["quality_score"] is not None else None,
            unlock_price=r["unlock_price"] or 10,
            query_count=query_counts_map.get(ds_id, 0),
            basic_upload_reward=rew["basic"],
            quality_reward=rew["quality"],
            improvement_rewards=rew["improvement"],
            created_at=r["created_at"],
            version_count=len(v_rows) + 1,
            availability=availability,
            versions=v_rows,
        ))

    # Recent queries (latest 20 for quick overview preview; full paginated history via /users/{id}/queries)
    cursor.execute(
        f"""
        SELECT id, query_text, dataset_id, dataset_name, generated_sql, status, execution_time_ms,
               result_count, credits_charged, error_message, created_at
        FROM queries
        WHERE user_id = ?
        ORDER BY {_norm_ts_sql('created_at')} DESC, id DESC
        LIMIT 20
        """,
        (user_id,),
    )
    recent_queries = [
        {
            "id": r["id"],
            "natural_prompt": r["query_text"],
            "dataset_id": r["dataset_id"],
            "dataset_name": r["dataset_name"] or "Cross-Catalog",
            "generated_sql": r["generated_sql"] or "-- No SQL generated",
            "status": r["status"] or "SUCCESS",
            "execution_time_ms": r["execution_time_ms"] or 0,
            "rows_returned": r["result_count"] or 0,
            "credits_charged": r["credits_charged"] or 0,
            "error_message": r["error_message"],
            "timestamp": r["created_at"],
        }
        for r in cursor.fetchall()
    ]

    # Recent transactions (latest 20 for quick overview preview; full paginated ledger via /users/{id}/transactions)
    cursor.execute(
        f"""
        SELECT id, amount, transaction_type, description, status, created_at
        FROM credit_transactions
        WHERE user_id = ?
        ORDER BY {_norm_ts_sql('created_at')} DESC, id DESC
        LIMIT 20
        """,
        (user_id,),
    )
    recent_transactions = [
        {
            "id": r["id"],
            "amount": r["amount"],
            "transaction_type": r["transaction_type"],
            "description": r["description"],
            "status": r["status"],
            "balance_impact": f"+{r['amount']}" if r["amount"] > 0 else f"{r['amount']}",
            "created_at": r["created_at"],
        }
        for r in cursor.fetchall()
    ]

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_USER_DETAIL",
        target_resource=user_id,
        details=f"Viewed user detail for {user_row['email']}",
        ip_address=client_ip,
    )

    is_adm = bool(user_row["is_admin"]) if "is_admin" in user_row.keys() else False
    return AdminUserDetailResponse(
        id=user_row["id"],
        email=user_row["email"],
        full_name=user_row["full_name"],
        credits=int(user_row["credits"] or 0),
        reputation_score=int(user_row["reputation_score"]) if "reputation_score" in user_row.keys() and user_row["reputation_score"] is not None else 50,
        is_admin=is_adm,
        account_status="Admin" if is_adm else ("Active" if (total_datasets > 0 or total_queries > 0) else "Inactive"),
        created_at=user_row["created_at"],
        last_activity=last_activity,
        total_datasets=total_datasets,
        total_queries=total_queries,
        total_queries_successful=total_queries_successful,
        total_queries_failed=total_queries_failed,
        query_success_rate=query_success_rate,
        total_credits_earned=total_credits_earned,
        total_credits_spent=total_credits_spent,
        total_credits_refunded=total_credits_refunded,
        total_unlocks=total_unlocks,
        total_improvements=total_improvements,
        datasets=datasets,
        recent_queries=recent_queries,
        recent_transactions=recent_transactions,
    )


@router.get("/datasets", response_model=AdminDatasetListResponse)
def get_admin_datasets(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by dataset title, ID, filename, domain, or owner"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    owner_id: Optional[str] = Query(None, description="Filter by owner user ID"),
    availability: Optional[str] = Query(None, description="Filter by storage availability: all, available, missing"),
    start_date: Optional[str] = Query(None, description="Start upload date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End upload date YYYY-MM-DD"),
    sort_by: Optional[str] = Query("created_at", description="Sort by: created_at, rows_count, quality_score, query_count, unlock_price, name"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc, desc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Returns platform-wide dataset registry with ownership, quality evaluations,
    query usage, version counts, and real DuckDB storage availability.
    Avoids unrestricted raw file data dumps.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    existing_duckdb_ids = get_existing_dataset_ids()

    # Available distinct domains for filter dropdown
    cursor.execute("SELECT DISTINCT LOWER(domain) AS dom FROM datasets WHERE domain IS NOT NULL ORDER BY dom ASC")
    available_domains = [r["dom"] for r in cursor.fetchall() if r["dom"]]

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(d.id) LIKE ? OR LOWER(d.name) LIKE ? OR LOWER(d.filename) LIKE ? OR LOWER(d.domain) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(u.full_name) LIKE ?)")
        params.extend([term, term, term, term, term, term])

    if domain and domain.strip() and domain.strip().lower() != "all":
        conditions.append("LOWER(d.domain) = ?")
        params.append(domain.strip().lower())

    if owner_id and owner_id.strip():
        conditions.append("d.user_id = ?")
        params.append(owner_id.strip())

    _append_date_conditions(conditions, params, "d.created_at", start_date, end_date)

    if availability and availability.strip().lower() in ("available", "missing"):
        avail_mode = availability.strip().lower()
        if existing_duckdb_ids:
            ph = ",".join("?" for _ in existing_duckdb_ids)
            if avail_mode == "available":
                conditions.append(f"d.id IN ({ph})")
            else:
                conditions.append(f"d.id NOT IN ({ph})")
            params.extend(list(existing_duckdb_ids))
        else:
            if avail_mode == "available":
                conditions.append("1 = 0")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        {where_clause}
        """,
        params,
    )
    total = int(cursor.fetchone()["total"] or 0)

    valid_sort_cols = {
        "created_at": _norm_ts_sql("d.created_at"),
        "rows_count": "d.rows_count",
        "quality_score": "COALESCE(e.overall_score, -1)",
        "query_count": "query_count",
        "unlock_price": "COALESCE(d.unlock_price, 10)",
        "name": "LOWER(d.name)",
    }
    col = valid_sort_cols.get(sort_by or "created_at", _norm_ts_sql("d.created_at"))
    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"

    offset = (page - 1) * limit
    data_query = f"""
        WITH q_counts AS (
            SELECT dataset_id, COUNT(*) AS cnt FROM queries WHERE dataset_id IS NOT NULL GROUP BY dataset_id
        ),
        u_counts AS (
            SELECT dataset_id, COUNT(*) AS cnt FROM dataset_unlocks GROUP BY dataset_id
        ),
        v_counts AS (
            SELECT dataset_id, COUNT(*) AS cnt FROM dataset_versions GROUP BY dataset_id
        )
        SELECT d.id, d.name, d.filename, d.domain, d.rows_count, d.columns_count,
               d.content_summary, d.unlock_price, d.created_at,
               u.id AS owner_id, u.full_name AS owner_name, u.email AS owner_email,
               e.quality_score, e.domain_relevance_score, e.overall_score,
               e.status AS evaluation_status, e.credits_awarded,
               COALESCE(uc.cnt, 0) AS unlock_count,
               COALESCE(qc.cnt, 0) AS query_count,
               COALESCE(vc.cnt, 0) AS extra_versions
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        LEFT JOIN evaluations e ON d.id = e.dataset_id
        LEFT JOIN u_counts uc ON uc.dataset_id = d.id
        LEFT JOIN q_counts qc ON qc.dataset_id = d.id
        LEFT JOIN v_counts vc ON vc.dataset_id = d.id
        {where_clause}
        ORDER BY {col} {order}, d.id {order}
        LIMIT ? OFFSET ?
    """
    cursor.execute(data_query, list(params) + [limit, offset])
    rows = cursor.fetchall()

    items = []
    for r in rows:
        ds_id = r["id"]
        avail = "Available" if ds_id in existing_duckdb_ids else "Metadata Only"
        items.append(AdminDatasetItem(
            id=ds_id,
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
            unlock_count=int(r["unlock_count"] or 0),
            query_count=int(r["query_count"] or 0),
            version_count=int(r["extra_versions"] or 0) + 1,
            availability=avail,
            content_summary=r["content_summary"] or "",
            created_at=r["created_at"],
        ))

    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_DATASETS",
        details=f"Listed datasets page={page}, limit={limit}",
        ip_address=client_ip,
    )

    return AdminDatasetListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more,
        available_domains=available_domains,
    )


@router.get("/datasets/{dataset_id}", response_model=AdminDatasetDetailResponse)
def get_admin_dataset_detail(
    dataset_id: str,
    request: Request,
    admin: dict = Depends(get_current_admin_user),
):
    """
    Detailed administrative inspection of a single dataset: owner, schema structure (never raw rows),
    evaluation scores, reward breakdown, query usage stats, and version history.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT d.id, d.name, d.filename, d.domain, d.rows_count, d.columns_count,
               d.schema_json, d.content_summary, d.unlock_price, d.created_at,
               u.id AS owner_id, u.full_name AS owner_name, u.email AS owner_email
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        WHERE d.id = ?
        """,
        (dataset_id,),
    )
    ds = cursor.fetchone()
    if not ds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID '{dataset_id}' not found.",
        )

    # Parse schema columns (structure only, never raw data rows)
    schema_columns: List[Dict[str, str]] = []
    try:
        parsed_schema = json.loads(ds["schema_json"] or "{}")
        if isinstance(parsed_schema, dict):
            schema_columns = [{"name": str(k), "type": str(v)} for k, v in parsed_schema.items()]
    except Exception:
        schema_columns = []

    # Evaluation record
    cursor.execute("SELECT * FROM evaluations WHERE dataset_id = ?", (dataset_id,))
    ev = cursor.fetchone()
    evaluation = None
    if ev:
        evaluation = {
            "id": ev["id"],
            "status": ev["status"],
            "progress": ev["progress"],
            "quality_score": round(float(ev["quality_score"]), 1),
            "schema_fidelity_score": round(float(ev["schema_fidelity_score"]), 1),
            "completeness_score": round(float(ev["completeness_score"]), 1),
            "domain_relevance_score": round(float(ev["domain_relevance_score"]), 1),
            "overall_score": round(float(ev["overall_score"]), 1),
            "credits_awarded": int(ev["credits_awarded"] or 0),
            "error_message": ev["error_message"],
            "updated_at": ev["updated_at"],
            "created_at": ev["created_at"],
        }

    # Usage stats
    cursor.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END), 0) AS ok,
               COUNT(DISTINCT user_id) AS unique_queriers
        FROM queries
        WHERE dataset_id = ?
        """,
        (dataset_id,),
    )
    q_stat = cursor.fetchone()
    query_count = int(q_stat["total"] or 0)
    successful_queries = int(q_stat["ok"] or 0)
    failed_queries = query_count - successful_queries
    unique_queriers = int(q_stat["unique_queriers"] or 0)

    cursor.execute("SELECT COUNT(*) AS cnt FROM dataset_unlocks WHERE dataset_id = ?", (dataset_id,))
    unlock_count = int(cursor.fetchone()["cnt"] or 0)

    # Rewards & versions
    rewards_map, versions_map, _ = _batch_dataset_rewards_and_versions(cursor, [dataset_id])
    rew = rewards_map.get(dataset_id, {"basic": 0, "quality": 0, "improvement": 0})
    versions = versions_map.get(dataset_id, [])

    # Recent query metadata (no raw dataset content)
    cursor.execute(
        f"""
        SELECT q.id, q.user_id, u.full_name AS user_name, u.email AS user_email,
               q.query_text, q.status, q.execution_time_ms, q.result_count, q.credits_charged, q.created_at
        FROM queries q
        JOIN users u ON q.user_id = u.id
        WHERE q.dataset_id = ?
        ORDER BY {_norm_ts_sql('q.created_at')} DESC, q.id DESC
        LIMIT 10
        """,
        (dataset_id,),
    )
    recent_queries = [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "user_email": r["user_email"],
            "natural_prompt": r["query_text"],
            "status": r["status"] or "SUCCESS",
            "execution_time_ms": r["execution_time_ms"] or 0,
            "rows_returned": r["result_count"] or 0,
            "credits_charged": r["credits_charged"] or 0,
            "timestamp": r["created_at"],
        }
        for r in cursor.fetchall()
    ]

    existing_duckdb_ids = get_existing_dataset_ids()
    availability = "Available" if dataset_id in existing_duckdb_ids else "Metadata Only"

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_DATASET_DETAIL",
        target_resource=dataset_id,
        details=f"Viewed dataset detail for '{ds['name']}'",
        ip_address=client_ip,
    )

    return AdminDatasetDetailResponse(
        id=ds["id"],
        name=ds["name"],
        filename=ds["filename"],
        domain=ds["domain"],
        owner_id=ds["owner_id"],
        owner_name=ds["owner_name"],
        owner_email=ds["owner_email"],
        rows_count=ds["rows_count"],
        columns_count=ds["columns_count"],
        schema_columns=schema_columns,
        content_summary=ds["content_summary"] or "",
        unlock_price=ds["unlock_price"] or 10,
        unlock_count=unlock_count,
        query_count=query_count,
        successful_queries=successful_queries,
        failed_queries=failed_queries,
        unique_queriers=unique_queriers,
        availability=availability,
        created_at=ds["created_at"],
        evaluation=evaluation,
        basic_upload_reward=rew["basic"],
        quality_reward=rew["quality"],
        improvement_rewards=rew["improvement"],
        total_rewards=rew["basic"] + rew["quality"] + rew["improvement"],
        version_count=len(versions) + 1,
        versions=versions,
        recent_queries=recent_queries,
    )


@router.get("/queries", response_model=AdminQueryListResponse)
def get_admin_queries(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search prompt, SQL, dataset name, or user email"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    dataset_id: Optional[str] = Query(None, description="Filter by dataset ID"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, FAILED, SQL_REJECTED, INSUFFICIENT_CREDITS)"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    sort_order: Optional[str] = Query("desc", description="Sort order: desc, asc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Global query execution audit log across all users with summary analytics.
    Exposes prompt and generated SQL to administrators without exposing raw dataset rows.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(q.query_text) LIKE ? OR LOWER(COALESCE(q.generated_sql, '')) LIKE ? OR LOWER(COALESCE(q.dataset_name, '')) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(u.full_name) LIKE ? OR LOWER(q.id) LIKE ?)")
        params.extend([term, term, term, term, term, term])

    if user_id and user_id.strip():
        conditions.append("q.user_id = ?")
        params.append(user_id.strip())

    if dataset_id and dataset_id.strip():
        conditions.append("q.dataset_id = ?")
        params.append(dataset_id.strip())

    if status and status.strip() and status.strip().upper() != "ALL":
        st = status.strip().upper()
        if st == "FAILED":
            conditions.append("UPPER(COALESCE(q.status, 'SUCCESS')) != 'SUCCESS'")
        else:
            conditions.append("UPPER(COALESCE(q.status, 'SUCCESS')) = ?")
            params.append(st)

    _append_date_conditions(conditions, params, "q.created_at", start_date, end_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor.execute(
        f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(q.status, 'SUCCESS')) = 'SUCCESS' THEN 1 ELSE 0 END), 0) AS ok,
               COALESCE(AVG(COALESCE(q.execution_time_ms, 0)), 0) AS avg_ms,
               COALESCE(SUM(COALESCE(q.credits_charged, 0)), 0) AS total_charged
        FROM queries q
        JOIN users u ON q.user_id = u.id
        {where_clause}
        """,
        params,
    )
    agg = cursor.fetchone()
    total = int(agg["total"] or 0)
    ok_cnt = int(agg["ok"] or 0)
    fail_cnt = total - ok_cnt
    summary = {
        "total_queries": total,
        "successful_queries": ok_cnt,
        "failed_queries": fail_cnt,
        "success_rate": round((ok_cnt / total) * 100.0, 1) if total > 0 else 100.0,
        "avg_execution_time_ms": int(round(float(agg["avg_ms"] or 0))),
        "total_credits_charged": int(agg["total_charged"] or 0),
    }

    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"
    offset = (page - 1) * limit
    cursor.execute(
        f"""
        SELECT q.id, q.user_id, q.dataset_id, q.dataset_name, q.query_text, q.generated_sql,
               q.execution_time_ms, q.result_count, q.status, q.credits_charged, q.error_message, q.created_at,
               u.email AS user_email, u.full_name AS user_name
        FROM queries q
        JOIN users u ON q.user_id = u.id
        {where_clause}
        ORDER BY {_norm_ts_sql('q.created_at')} {order}, q.id {order}
        LIMIT ? OFFSET ?
        """,
        list(params) + [limit, offset],
    )
    rows = cursor.fetchall()

    items = [
        AdminQueryItem(
            id=r["id"],
            user_id=r["user_id"],
            user_email=r["user_email"],
            user_name=r["user_name"],
            natural_prompt=r["query_text"],
            dataset_id=r["dataset_id"],
            dataset_name=r["dataset_name"] or "Cross-Catalog",
            generated_sql=r["generated_sql"] or "-- No SQL generated",
            execution_status=r["status"] or "SUCCESS",
            execution_time_ms=int(r["execution_time_ms"] or 0),
            rows_returned=int(r["result_count"] or 0),
            credits_charged=int(r["credits_charged"] or 0),
            credits_refunded=0,
            error_message=r["error_message"],
            timestamp=r["created_at"],
        )
        for r in rows
    ]

    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_QUERIES",
        details=f"Listed queries page={page}, limit={limit}",
        ip_address=client_ip,
    )

    return AdminQueryListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more,
        summary=summary,
    )


def _fetch_transactions_with_running_balance(
    cursor,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    transaction_type: Optional[str] = None,
    direction: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sort_order: Optional[str] = "desc",
    page: int = 1,
    limit: int = 20,
) -> Tuple[List[AdminTransactionItem], int, Dict[str, int]]:
    """
    Computes exact historical running balance (balance_after) per user via SQL window function
    over the full credit_transactions table BEFORE filtering/pagination, so every ledger entry
    shows the user's true balance after that transaction.
    """
    cte_filter = "WHERE t0.user_id = ?" if user_id and user_id.strip() else ""
    cte_params: List[Any] = [user_id.strip()] if user_id and user_id.strip() else []

    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(tx.description) LIKE ? OR LOWER(tx.user_email) LIKE ? OR LOWER(tx.user_name) LIKE ? OR LOWER(tx.id) LIKE ? OR LOWER(tx.user_id) LIKE ?)")
        params.extend([term, term, term, term, term])

    if transaction_type and transaction_type.strip() and transaction_type.strip().lower() != "all":
        conditions.append("LOWER(tx.transaction_type) = ?")
        params.append(transaction_type.strip().lower())

    if direction and direction.strip().lower() in ("positive", "negative"):
        if direction.strip().lower() == "positive":
            conditions.append("tx.amount > 0")
        else:
            conditions.append("tx.amount < 0")

    _append_date_conditions(conditions, params, "tx.created_at", start_date, end_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    base_cte = f"""
        WITH ranked_tx AS (
            SELECT t0.id, t0.user_id, t0.amount, t0.transaction_type, t0.description, t0.status, t0.created_at,
                   u.email AS user_email, u.full_name AS user_name,
                   SUM(t0.amount) OVER (
                       PARTITION BY t0.user_id
                       ORDER BY {_norm_ts_sql('t0.created_at')} ASC, t0.rowid ASC
                   ) AS balance_after
            FROM credit_transactions t0
            JOIN users u ON t0.user_id = u.id
            {cte_filter}
        )
    """

    owner_types_sql = ",".join(f"'{t}'" for t in OWNER_EARNING_TYPES)
    cursor.execute(
        f"""
        {base_cte}
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN tx.amount > 0 THEN tx.amount ELSE 0 END), 0) AS issued,
               COALESCE(ABS(SUM(CASE WHEN tx.amount < 0 THEN tx.amount ELSE 0 END)), 0) AS spent,
               COALESCE(SUM(CASE WHEN LOWER(tx.transaction_type) IN ({owner_types_sql}) AND tx.amount > 0 THEN tx.amount ELSE 0 END), 0) AS owner_earned,
               COALESCE(ABS(SUM(CASE WHEN LOWER(tx.transaction_type) = 'query_fee' THEN tx.amount ELSE 0 END)), 0) AS query_fees,
               COALESCE(SUM(CASE WHEN LOWER(tx.transaction_type) LIKE '%refund%' AND tx.amount > 0 THEN tx.amount ELSE 0 END), 0) AS refunds
        FROM ranked_tx tx
        {where_clause}
        """,
        cte_params + params,
    )
    agg = cursor.fetchone()
    total = int(agg["total"] or 0)
    issued = int(agg["issued"] or 0)
    spent = int(agg["spent"] or 0)
    summary = {
        "total_issued": issued,
        "total_spent": spent,
        "net_movement": issued - spent,
        "earned_by_owners": int(agg["owner_earned"] or 0),
        "query_fees_collected": int(agg["query_fees"] or 0),
        "refunds_total": int(agg["refunds"] or 0),
    }

    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"
    offset = (page - 1) * limit
    cursor.execute(
        f"""
        {base_cte}
        SELECT tx.id, tx.user_id, tx.user_email, tx.user_name, tx.amount,
               tx.transaction_type, tx.description, tx.status, tx.created_at, tx.balance_after
        FROM ranked_tx tx
        {where_clause}
        ORDER BY {_norm_ts_sql('tx.created_at')} {order}, tx.id {order}
        LIMIT ? OFFSET ?
        """,
        cte_params + params + [limit, offset],
    )
    rows = cursor.fetchall()

    # Batch resolve dataset names/owners, query authors, and unlock buyers for sender/receiver attribution
    ds_ids: Set[str] = set()
    q_ids: Set[str] = set()
    royalty_ds_ids: Set[str] = set()
    parsed_refs: List[Tuple[Optional[str], Optional[str], Optional[str]]] = []
    for r in rows:
        assoc, ds_id, q_id = _extract_resource_ids(r["description"] or "")
        parsed_refs.append((assoc, ds_id, q_id))
        if ds_id:
            ds_ids.add(ds_id)
            if (r["transaction_type"] or "").lower() == "unlock_royalty":
                royalty_ds_ids.add(ds_id)
        if q_id:
            q_ids.add(q_id)

    ds_name_map: Dict[str, str] = {}
    ds_owner_map: Dict[str, Tuple[str, str, str]] = {}
    if ds_ids:
        ph = ",".join("?" for _ in ds_ids)
        cursor.execute(
            f"""
            SELECT d.id, d.name, d.user_id AS owner_id, u.full_name AS owner_name, u.email AS owner_email
            FROM datasets d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE d.id IN ({ph})
            """,
            list(ds_ids),
        )
        for dr in cursor.fetchall():
            ds_name_map[dr["id"]] = dr["name"]
            if dr["owner_id"]:
                ds_owner_map[dr["id"]] = (
                    dr["owner_id"],
                    dr["owner_name"] or dr["owner_id"],
                    dr["owner_email"] or "",
                )

    q_user_map: Dict[str, Tuple[str, str, str]] = {}
    if q_ids:
        ph = ",".join("?" for _ in q_ids)
        cursor.execute(
            f"""
            SELECT q.id, q.user_id, u.full_name, u.email
            FROM queries q
            LEFT JOIN users u ON q.user_id = u.id
            WHERE q.id IN ({ph})
            """,
            list(q_ids),
        )
        for qr in cursor.fetchall():
            if qr["user_id"]:
                q_user_map[qr["id"]] = (
                    qr["user_id"],
                    qr["full_name"] or qr["user_id"],
                    qr["email"] or "",
                )

    unlock_buyers_by_ds: Dict[str, List[Tuple[str, str, str]]] = {}
    if royalty_ds_ids:
        ph = ",".join("?" for _ in royalty_ds_ids)
        cursor.execute(
            f"""
            SELECT du.dataset_id, du.user_id, u.full_name, u.email
            FROM dataset_unlocks du
            LEFT JOIN users u ON du.user_id = u.id
            WHERE du.dataset_id IN ({ph})
            ORDER BY {_norm_ts_sql('du.created_at')} DESC
            """,
            list(royalty_ds_ids),
        )
        for ur in cursor.fetchall():
            unlock_buyers_by_ds.setdefault(ur["dataset_id"], []).append(
                (ur["user_id"], ur["full_name"] or ur["user_id"], ur["email"] or "")
            )

    def _fmt_party(name: str, email: str) -> str:
        return f"{name} ({email})" if email else name

    items = []
    for r, (assoc, ds_id, q_id) in zip(rows, parsed_refs):
        amount = int(r["amount"] or 0)
        impact = f"+{amount}" if amount > 0 else f"{amount}"
        tx_type = (r["transaction_type"] or "").lower()
        user_label = _fmt_party(r["user_name"], r["user_email"])
        desc = r["description"] or ""

        sender = "DataPulse Platform"
        sender_id: Optional[str] = None
        receiver = "DataPulse Platform"
        receiver_id: Optional[str] = None

        if tx_type == "query_fee":
            sender = user_label
            sender_id = r["user_id"]
            if ds_id and ds_id in ds_owner_map:
                oid, oname, oemail = ds_owner_map[ds_id]
                receiver = _fmt_party(oname, oemail)
                receiver_id = oid
            else:
                receiver = "DataPulse Marketplace"
        elif tx_type == "query_reward":
            if q_id and q_id in q_user_map:
                qid_u, qname, qemail = q_user_map[q_id]
                sender = _fmt_party(qname, qemail)
                sender_id = qid_u
            else:
                sender = "DataPulse Marketplace"
            receiver = user_label
            receiver_id = r["user_id"]
        elif tx_type == "dataset_unlock":
            sender = user_label
            sender_id = r["user_id"]
            if ds_id and ds_id in ds_owner_map:
                oid, oname, oemail = ds_owner_map[ds_id]
                receiver = _fmt_party(oname, oemail)
                receiver_id = oid
            else:
                receiver = "DataPulse Marketplace"
        elif tx_type == "unlock_royalty":
            matched_buyer = None
            by_idx = desc.rfind(" by ")
            buyer_name_hint = desc[by_idx + 4:].strip().lower() if by_idx != -1 else ""
            if ds_id and ds_id in unlock_buyers_by_ds:
                candidates = unlock_buyers_by_ds[ds_id]
                if buyer_name_hint:
                    matched_buyer = next(
                        (c for c in candidates if c[1].strip().lower() == buyer_name_hint),
                        None,
                    )
                if not matched_buyer and candidates:
                    matched_buyer = candidates[0]
            if matched_buyer:
                sender = _fmt_party(matched_buyer[1], matched_buyer[2])
                sender_id = matched_buyer[0]
            elif by_idx != -1 and desc[by_idx + 4:].strip():
                sender = desc[by_idx + 4:].strip()
            else:
                sender = "Marketplace Buyer"
            receiver = user_label
            receiver_id = r["user_id"]
        elif tx_type == "redeem":
            sender = user_label
            sender_id = r["user_id"]
            receiver = "Payout Redemption"
        elif amount >= 0:
            sender = "DataPulse Platform"
            receiver = user_label
            receiver_id = r["user_id"]
        else:
            sender = user_label
            sender_id = r["user_id"]
            receiver = "DataPulse Platform"

        items.append(AdminTransactionItem(
            id=r["id"],
            user_id=r["user_id"],
            user_email=r["user_email"],
            user_name=r["user_name"],
            sender=sender,
            sender_id=sender_id,
            receiver=receiver,
            receiver_id=receiver_id,
            transaction_type=r["transaction_type"],
            amount=amount,
            balance_impact=impact,
            balance_after=int(r["balance_after"]) if r["balance_after"] is not None else None,
            associated_resource=assoc,
            related_dataset_id=ds_id,
            related_dataset_name=ds_name_map.get(ds_id) if ds_id else None,
            related_query_id=q_id,
            description=desc,
            status=r["status"] or "completed",
            timestamp=r["created_at"],
        ))

    return items, total, summary


@router.get("/transactions", response_model=AdminTransactionListResponse)
def get_admin_transactions(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search description, user name, email, or ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    transaction_type: Optional[str] = Query(None, description="Filter by transaction type"),
    direction: Optional[str] = Query(None, description="Filter by credit direction: all, positive, negative"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    sort_order: Optional[str] = Query("desc", description="Sort order: desc, asc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Platform-wide credit ledger and financial audit history with running balances and summary totals.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    items, total, summary = _fetch_transactions_with_running_balance(
        cursor=cursor,
        user_id=user_id,
        search=search,
        transaction_type=transaction_type,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        sort_order=sort_order,
        page=page,
        limit=limit,
    )

    offset = (page - 1) * limit
    has_more = (offset + len(items)) < total

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="LIST_TRANSACTIONS",
        details=f"Listed credit transactions page={page}, limit={limit}",
        ip_address=client_ip,
    )

    return AdminTransactionListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more,
        summary=summary,
    )


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def get_admin_audit_logs(
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    search: Optional[str] = Query(None, description="Search details, target resource, or admin email"),
    admin: dict = Depends(get_current_admin_user),
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

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(COALESCE(details, '')) LIKE ? OR LOWER(COALESCE(target_resource, '')) LIKE ? OR LOWER(admin_email) LIKE ? OR LOWER(action) LIKE ?)")
        params.extend([term, term, term, term])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor.execute(f"SELECT COUNT(*) AS total FROM admin_audit_logs {where_clause}", params)
    total = int(cursor.fetchone()["total"] or 0)

    offset = (page - 1) * limit
    cursor.execute(
        f"""
        SELECT id, admin_user_id, admin_email, action, target_resource, details, ip_address, created_at
        FROM admin_audit_logs
        {where_clause}
        ORDER BY {_norm_ts_sql('created_at')} DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        list(params) + [limit, offset],
    )
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
            timestamp=r["created_at"],
        )
        for r in rows
    ]

    return AdminAuditLogListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(items)) < total,
    )


def _get_timeline_events(
    cursor,
    user_id: Optional[str] = None,
    activity_type: Optional[str] = None,
    dataset_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    sort_order: Optional[str] = "desc",
    include_admin_audit: bool = False,
    limit: int = 20,
    offset: int = 0,
):
    """
    Unified chronological event stream across all persisted platform tables.
    - Uses normalized ISO timestamps (REPLACE(' ', 'T')) for deterministic ordering & date filtering.
    - Includes USER_LOGIN derived from persisted session rows WITHOUT ever exposing session credentials.
    - Excludes noisy read-only ADMIN_AUDIT events unless explicitly requested via activity_type='ADMIN_AUDIT'.
    """
    norm_u = _norm_ts_sql("u.created_at")
    norm_tok = _norm_ts_sql("s.created_at")
    norm_d = _norm_ts_sql("d.created_at")
    norm_q = _norm_ts_sql("q.created_at")
    norm_t = _norm_ts_sql("t.created_at")
    norm_v = _norm_ts_sql("v.created_at")
    norm_du = _norm_ts_sql("du.created_at")
    norm_a = _norm_ts_sql("a.created_at")

    want_audit = include_admin_audit or (activity_type and activity_type.strip().upper() == "ADMIN_AUDIT")

    union_parts = [
        f"""
        SELECT 'reg_' || u.id AS id,
               'USER_REGISTER' AS type,
               'Account Registered' AS title,
               'User ' || u.full_name || ' registered on DataPulse' AS description,
               {norm_u} AS timestamp,
               'SUCCESS' AS status,
               u.id AS user_id,
               u.email AS user_email,
               u.full_name AS user_name,
               NULL AS dataset_id,
               NULL AS dataset_name,
               NULL AS related_query_id,
               NULL AS related_transaction_id,
               '100' AS detail_1,
               CASE WHEN u.is_admin = 1 THEN 'Administrator' ELSE 'Contributor' END AS detail_2,
               NULL AS detail_3
        FROM users u
        """,
        f"""
        SELECT 'login_' || CAST(s.rowid AS TEXT) AS id,
               'USER_LOGIN' AS type,
               'Account Sign-In' AS title,
               'Authenticated session started for ' || u.full_name AS description,
               {norm_tok} AS timestamp,
               'SUCCESS' AS status,
               s.user_id AS user_id,
               u.email AS user_email,
               u.full_name AS user_name,
               NULL AS dataset_id,
               NULL AS dataset_name,
               NULL AS related_query_id,
               NULL AS related_transaction_id,
               'session_record' AS detail_1,
               NULL AS detail_2,
               NULL AS detail_3
        FROM tokens s
        JOIN users u ON s.user_id = u.id
        WHERE SUBSTR({norm_tok}, 1, 19) != SUBSTR({norm_u}, 1, 19)
        """,
        f"""
        SELECT 'ds_' || d.id AS id,
               'DATASET_UPLOAD' AS type,
               'Dataset Uploaded' AS title,
               d.name || ' (' || d.rows_count || ' rows, ' || d.columns_count || ' cols)' AS description,
               {norm_d} AS timestamp,
               'SUCCESS' AS status,
               d.user_id AS user_id,
               u.email AS user_email,
               u.full_name AS user_name,
               d.id AS dataset_id,
               d.name AS dataset_name,
               NULL AS related_query_id,
               NULL AS related_transaction_id,
               CAST(d.rows_count AS TEXT) AS detail_1,
               d.filename AS detail_2,
               d.domain AS detail_3
        FROM datasets d
        JOIN users u ON d.user_id = u.id
        """,
        f"""
        SELECT 'qry_' || q.id AS id,
               'QUERY_EXECUTION' AS type,
               CASE WHEN UPPER(COALESCE(q.status, 'SUCCESS')) = 'SUCCESS' THEN 'Query Executed' ELSE 'Query Failed' END AS title,
               q.query_text AS description,
               {norm_q} AS timestamp,
               COALESCE(q.status, 'SUCCESS') AS status,
               q.user_id AS user_id,
               u.email AS user_email,
               u.full_name AS user_name,
               q.dataset_id AS dataset_id,
               COALESCE(q.dataset_name, 'Cross-Catalog') AS dataset_name,
               q.id AS related_query_id,
               NULL AS related_transaction_id,
               CAST(COALESCE(q.credits_charged, 0) AS TEXT) AS detail_1,
               COALESCE(q.generated_sql, '') AS detail_2,
               COALESCE(q.error_message, CAST(COALESCE(q.execution_time_ms, 0) AS TEXT) || 'ms • ' || CAST(COALESCE(q.result_count, 0) AS TEXT) || ' rows') AS detail_3
        FROM queries q
        JOIN users u ON q.user_id = u.id
        """,
        f"""
        SELECT 'tx_' || t.id AS id,
               'CREDIT_TRANSACTION' AS type,
               CASE
                   WHEN LOWER(t.transaction_type) LIKE '%refund%' THEN 'Credit Refund'
                   WHEN LOWER(t.transaction_type) = 'query_fee' THEN 'Query Fee Charged'
                   WHEN LOWER(t.transaction_type) = 'redeem' THEN 'Credit Redemption'
                   WHEN t.amount > 0 THEN 'Credit Reward'
                   ELSE 'Credit Debit'
               END AS title,
               t.description AS description,
               {norm_t} AS timestamp,
               COALESCE(t.status, 'completed') AS status,
               t.user_id AS user_id,
               u.email AS user_email,
               u.full_name AS user_name,
               NULL AS dataset_id,
               NULL AS dataset_name,
               NULL AS related_query_id,
               t.id AS related_transaction_id,
               CAST(t.amount AS TEXT) AS detail_1,
               t.transaction_type AS detail_2,
               NULL AS detail_3
        FROM credit_transactions t
        JOIN users u ON t.user_id = u.id
        """,
        f"""
        SELECT 'ver_' || v.id AS id,
               'DATASET_IMPROVE' AS type,
               'Dataset Version Improved' AS title,
               v.changes_summary AS description,
               {norm_v} AS timestamp,
               'SUCCESS' AS status,
               v.user_id AS user_id,
               u.email AS user_email,
               u.full_name AS user_name,
               v.dataset_id AS dataset_id,
               d.name AS dataset_name,
               NULL AS related_query_id,
               NULL AS related_transaction_id,
               '+' || CAST(v.credits_awarded AS TEXT) || ' cr' AS detail_1,
               v.version AS detail_2,
               '+' || CAST(ROUND(v.delta_score, 1) AS TEXT) AS detail_3
        FROM dataset_versions v
        JOIN users u ON v.user_id = u.id
        LEFT JOIN datasets d ON v.dataset_id = d.id
        """,
        f"""
        SELECT 'unl_' || du.id AS id,
               'DATASET_UNLOCK' AS type,
               'Dataset Unlocked' AS title,
               'Unlocked dataset ' || COALESCE(d.name, du.dataset_id) AS description,
               {norm_du} AS timestamp,
               'SUCCESS' AS status,
               du.user_id AS user_id,
               u.email AS user_email,
               u.full_name AS user_name,
               du.dataset_id AS dataset_id,
               d.name AS dataset_name,
               NULL AS related_query_id,
               NULL AS related_transaction_id,
               '-' || CAST(du.unlock_price AS TEXT) || ' cr' AS detail_1,
               NULL AS detail_2,
               NULL AS detail_3
        FROM dataset_unlocks du
        JOIN users u ON du.user_id = u.id
        LEFT JOIN datasets d ON du.dataset_id = d.id
        """,
    ]

    if want_audit:
        union_parts.append(f"""
        SELECT 'aud_' || a.id AS id,
               'ADMIN_AUDIT' AS type,
               'Admin Inspection' AS title,
               a.action || ': ' || COALESCE(a.details, 'Administrative audit') AS description,
               {norm_a} AS timestamp,
               'SUCCESS' AS status,
               a.admin_user_id AS user_id,
               a.admin_email AS user_email,
               'Administrator' AS user_name,
               NULL AS dataset_id,
               NULL AS dataset_name,
               NULL AS related_query_id,
               NULL AS related_transaction_id,
               a.action AS detail_1,
               a.target_resource AS detail_2,
               a.ip_address AS detail_3
        FROM admin_audit_logs a
        """)

    base_union = "\nUNION ALL\n".join(union_parts)

    conditions = []
    params: List[Any] = []

    if user_id and user_id.strip():
        uid = user_id.strip()
        if want_audit:
            conditions.append("(events.user_id = ? OR (events.type = 'ADMIN_AUDIT' AND events.detail_2 = ?))")
            params.extend([uid, uid])
        else:
            conditions.append("events.user_id = ?")
            params.append(uid)

    if activity_type and activity_type.strip() and activity_type.strip().lower() != "all":
        at = activity_type.strip().upper()
        if at == "QUERY_SUCCESS":
            conditions.append("(events.type = 'QUERY_EXECUTION' AND UPPER(events.status) = 'SUCCESS')")
        elif at == "QUERY_FAILED":
            conditions.append("(events.type = 'QUERY_EXECUTION' AND UPPER(events.status) != 'SUCCESS')")
        elif at == "CREDIT_REWARD":
            conditions.append("(events.type = 'CREDIT_TRANSACTION' AND CAST(events.detail_1 AS INTEGER) > 0 AND LOWER(COALESCE(events.detail_2, '')) NOT LIKE '%refund%')")
        elif at == "QUERY_FEE":
            conditions.append("(events.type = 'CREDIT_TRANSACTION' AND LOWER(COALESCE(events.detail_2, '')) = 'query_fee')")
        elif at == "REFUND":
            conditions.append("(events.type = 'CREDIT_TRANSACTION' AND LOWER(COALESCE(events.detail_2, '')) LIKE '%refund%')")
        else:
            conditions.append("UPPER(events.type) = ?")
            params.append(at)

    if dataset_id and dataset_id.strip():
        conditions.append("events.dataset_id = ?")
        params.append(dataset_id.strip())

    if status_filter and status_filter.strip() and status_filter.strip().lower() != "all":
        sf = status_filter.strip().upper()
        if sf == "FAILED":
            conditions.append("UPPER(events.status) NOT IN ('SUCCESS', 'COMPLETED')")
        else:
            conditions.append("UPPER(events.status) = ?")
            params.append(sf)

    _append_date_conditions(conditions, params, "events.timestamp", start_date, end_date)

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(events.title) LIKE ? OR LOWER(events.description) LIKE ? OR LOWER(COALESCE(events.user_email, '')) LIKE ? OR LOWER(COALESCE(events.user_name, '')) LIKE ? OR LOWER(COALESCE(events.user_id, '')) LIKE ? OR LOWER(COALESCE(events.dataset_name, '')) LIKE ? OR LOWER(COALESCE(events.dataset_id, '')) LIKE ?)")
        params.extend([term, term, term, term, term, term, term])

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"

    cursor.execute(f"SELECT COUNT(*) AS total FROM ({base_union}) events {where_sql}", params)
    total = int(cursor.fetchone()["total"] or 0)

    cursor.execute(
        f"""
        SELECT id, type, title, description, timestamp, status, user_id, user_email, user_name,
               dataset_id, dataset_name, related_query_id, related_transaction_id,
               detail_1, detail_2, detail_3
        FROM ({base_union}) events
        {where_sql}
        ORDER BY timestamp {order}, id {order}
        LIMIT ? OFFSET ?
        """,
        list(params) + [limit, offset],
    )
    rows = cursor.fetchall()

    items = []
    for r in rows:
        t = r["type"]
        meta: Dict[str, Any] = {}
        ds_id = r["dataset_id"]
        rel_q_id = r["related_query_id"]
        rel_tx_id = r["related_transaction_id"]

        if t == "USER_REGISTER":
            meta = {"initial_credits": 100, "role": r["detail_2"]}
        elif t == "USER_LOGIN":
            meta = {"source": r["detail_1"]}
        elif t == "DATASET_UPLOAD":
            meta = {"rows_count": r["detail_1"], "filename": r["detail_2"], "domain": r["detail_3"]}
        elif t == "QUERY_EXECUTION":
            meta = {
                "credits_charged": r["detail_1"],
                "generated_sql": r["detail_2"],
                "execution_info": r["detail_3"],
            }
            if (r["status"] or "").upper() != "SUCCESS":
                meta["error_message"] = r["detail_3"]
        elif t == "CREDIT_TRANSACTION":
            _, parsed_ds, parsed_q = _extract_resource_ids(r["description"] or "")
            if not ds_id and parsed_ds:
                ds_id = parsed_ds
            if not rel_q_id and parsed_q:
                rel_q_id = parsed_q
            meta = {"amount": r["detail_1"], "transaction_type": r["detail_2"]}
        elif t == "DATASET_IMPROVE":
            meta = {"credits_awarded": r["detail_1"], "version": r["detail_2"], "delta_score": r["detail_3"]}
        elif t == "DATASET_UNLOCK":
            meta = {"unlock_price": r["detail_1"]}
        elif t == "ADMIN_AUDIT":
            meta = {"action": r["detail_1"], "target_resource": r["detail_2"], "ip_address": r["detail_3"]}

        items.append(AdminTimelineItem(
            id=r["id"],
            type=t,
            title=r["title"],
            description=r["description"],
            timestamp=r["timestamp"],
            status=r["status"] or "SUCCESS",
            user_id=r["user_id"],
            user_email=r["user_email"],
            user_name=r["user_name"],
            dataset_id=ds_id,
            dataset_name=r["dataset_name"],
            related_query_id=rel_q_id,
            related_transaction_id=rel_tx_id,
            metadata=meta,
        ))

    return items, total


@router.get("/users/{user_id}/queries", response_model=AdminQueryListResponse)
def get_admin_user_queries(
    user_id: str,
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search prompt, SQL, or dataset name"),
    dataset_id: Optional[str] = Query(None, description="Filter by dataset ID"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, FAILED, SQL_REJECTED, INSUFFICIENT_CREDITS)"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    sort_order: Optional[str] = Query("desc", description="Sort order: desc, asc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Dedicated, server-side paginated query history belonging to a specific user.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{user_id}' not found.",
        )

    conditions = ["q.user_id = ?"]
    params: List[Any] = [user_id]

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(q.query_text) LIKE ? OR LOWER(COALESCE(q.generated_sql, '')) LIKE ? OR LOWER(COALESCE(q.dataset_name, '')) LIKE ?)")
        params.extend([term, term, term])

    if dataset_id and dataset_id.strip():
        conditions.append("q.dataset_id = ?")
        params.append(dataset_id.strip())

    if status and status.strip() and status.strip().upper() != "ALL":
        st = status.strip().upper()
        if st == "FAILED":
            conditions.append("UPPER(COALESCE(q.status, 'SUCCESS')) != 'SUCCESS'")
        else:
            conditions.append("UPPER(COALESCE(q.status, 'SUCCESS')) = ?")
            params.append(st)

    _append_date_conditions(conditions, params, "q.created_at", start_date, end_date)

    where_clause = f"WHERE {' AND '.join(conditions)}"

    cursor.execute(f"SELECT COUNT(*) AS total FROM queries q {where_clause}", params)
    total = int(cursor.fetchone()["total"] or 0)

    order = "ASC" if (sort_order or "desc").lower() == "asc" else "DESC"
    offset = (page - 1) * limit
    cursor.execute(
        f"""
        SELECT q.id, q.user_id, q.dataset_id, q.dataset_name, q.query_text, q.generated_sql,
               q.execution_time_ms, q.result_count, q.status, q.credits_charged, q.error_message, q.created_at,
               u.email AS user_email, u.full_name AS user_name
        FROM queries q
        JOIN users u ON q.user_id = u.id
        {where_clause}
        ORDER BY {_norm_ts_sql('q.created_at')} {order}, q.id {order}
        LIMIT ? OFFSET ?
        """,
        list(params) + [limit, offset],
    )
    rows = cursor.fetchall()

    items = [
        AdminQueryItem(
            id=r["id"],
            user_id=r["user_id"],
            user_email=r["user_email"],
            user_name=r["user_name"],
            natural_prompt=r["query_text"],
            dataset_id=r["dataset_id"],
            dataset_name=r["dataset_name"] or "Cross-Catalog",
            generated_sql=r["generated_sql"] or "-- No SQL generated",
            execution_status=r["status"] or "SUCCESS",
            execution_time_ms=int(r["execution_time_ms"] or 0),
            rows_returned=int(r["result_count"] or 0),
            credits_charged=int(r["credits_charged"] or 0),
            credits_refunded=0,
            error_message=r["error_message"],
            timestamp=r["created_at"],
        )
        for r in rows
    ]

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_USER_QUERIES",
        target_resource=user_id,
        details=f"Viewed queries for user {u_row['email']}, page={page}",
        ip_address=client_ip,
    )

    return AdminQueryListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(items)) < total,
    )


@router.get("/users/{user_id}/datasets", response_model=AdminDatasetListResponse)
def get_admin_user_datasets(
    user_id: str,
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search title, filename, domain"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Dedicated, server-side paginated dataset uploads belonging to a specific user.
    Includes per-dataset reward breakdowns (basic, quality, improvement), versions, query usage, and DuckDB availability.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{user_id}' not found.",
        )

    conditions = ["d.user_id = ?"]
    params: List[Any] = [user_id]

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(d.name) LIKE ? OR LOWER(d.filename) LIKE ? OR LOWER(d.domain) LIKE ?)")
        params.extend([term, term, term])

    if domain and domain.strip() and domain.strip().lower() != "all":
        conditions.append("LOWER(d.domain) = ?")
        params.append(domain.strip().lower())

    where_clause = f"WHERE {' AND '.join(conditions)}"

    cursor.execute(f"SELECT COUNT(*) AS total FROM datasets d {where_clause}", params)
    total = int(cursor.fetchone()["total"] or 0)

    offset = (page - 1) * limit
    cursor.execute(
        f"""
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
        ORDER BY {_norm_ts_sql('d.created_at')} DESC, d.id DESC
        LIMIT ? OFFSET ?
        """,
        list(params) + [limit, offset],
    )
    rows = cursor.fetchall()

    ds_ids = [r["id"] for r in rows]
    rewards_map, versions_map, query_counts_map = _batch_dataset_rewards_and_versions(cursor, ds_ids)
    existing_duckdb_ids = get_existing_dataset_ids()

    items = []
    for r in rows:
        ds_id = r["id"]
        rew = rewards_map.get(ds_id, {"basic": 0, "quality": 0, "improvement": 0})
        vers = versions_map.get(ds_id, [])
        avail = "Available" if ds_id in existing_duckdb_ids else "Metadata Only"
        items.append(AdminDatasetItem(
            id=ds_id,
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
            basic_upload_reward=rew["basic"],
            quality_reward=rew["quality"],
            improvement_rewards=rew["improvement"],
            unlock_price=r["unlock_price"] or 10,
            unlock_count=int(r["unlock_count"] or 0),
            query_count=query_counts_map.get(ds_id, 0),
            version_count=len(vers) + 1,
            versions=vers,
            availability=avail,
            content_summary=r["content_summary"] or "",
            created_at=r["created_at"],
        ))

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_USER_DATASETS",
        target_resource=user_id,
        details=f"Viewed datasets for user {u_row['email']}, page={page}",
        ip_address=client_ip,
    )

    return AdminDatasetListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(items)) < total,
    )


@router.get("/users/{user_id}/transactions", response_model=AdminTransactionListResponse)
def get_admin_user_transactions(
    user_id: str,
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search description"),
    transaction_type: Optional[str] = Query(None, description="Filter by transaction type"),
    direction: Optional[str] = Query(None, description="Filter by direction: all, positive, negative"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    sort_order: Optional[str] = Query("desc", description="Sort order: desc, asc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Dedicated, server-side paginated credit ledger belonging to a specific user
    with historical running balances.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{user_id}' not found.",
        )

    items, total, summary = _fetch_transactions_with_running_balance(
        cursor=cursor,
        user_id=user_id,
        search=search,
        transaction_type=transaction_type,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        sort_order=sort_order,
        page=page,
        limit=limit,
    )

    offset = (page - 1) * limit
    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_USER_TRANSACTIONS",
        target_resource=user_id,
        details=f"Viewed transactions for user {u_row['email']}, page={page}",
        ip_address=client_ip,
    )

    return AdminTransactionListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(items)) < total,
        summary=summary,
    )


@router.get("/users/{user_id}/activity", response_model=AdminTimelineResponse)
def get_admin_user_activity(
    user_id: str,
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    activity_type: Optional[str] = Query(None, description="Filter by activity type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    sort_order: Optional[str] = Query("desc", description="Sort order: desc, asc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Chronological activity timeline consolidating registration, sign-ins, uploads, queries,
    credit transactions, improvements, and unlocks for a single user.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{user_id}' not found.",
        )

    offset = (page - 1) * limit
    items, total = _get_timeline_events(
        cursor=cursor,
        user_id=user_id,
        activity_type=activity_type,
        status_filter=status,
        start_date=start_date,
        end_date=end_date,
        sort_order=sort_order,
        include_admin_audit=False,
        limit=limit,
        offset=offset,
    )

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_USER_TIMELINE",
        target_resource=user_id,
        details=f"Viewed activity timeline for user {u_row['email']}, page={page}",
        ip_address=client_ip,
    )

    return AdminTimelineResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(items)) < total,
    )


@router.get("/activity", response_model=AdminTimelineResponse)
def get_admin_global_activity(
    request: Request,
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search user, email, dataset, prompt, or description"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    activity_type: Optional[str] = Query(None, description="Filter by activity type"),
    dataset_id: Optional[str] = Query(None, description="Filter by dataset ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    sort_order: Optional[str] = Query("desc", description="Sort order: desc, asc"),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Global platform activity explorer across all users with multi-dimensional filtering and sorting.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    offset = (page - 1) * limit
    items, total = _get_timeline_events(
        cursor=cursor,
        user_id=user_id,
        activity_type=activity_type,
        dataset_id=dataset_id,
        status_filter=status,
        start_date=start_date,
        end_date=end_date,
        search=search,
        sort_order=sort_order,
        include_admin_audit=False,
        limit=limit,
        offset=offset,
    )

    client_ip = request.client.host if request.client else None
    log_admin_audit(
        admin_user_id=admin["id"],
        admin_email=admin["email"],
        action="VIEW_GLOBAL_ACTIVITY",
        details=f"Viewed global activity explorer page={page}, limit={limit}",
        ip_address=client_ip,
    )

    return AdminTimelineResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(items)) < total,
    )


def _validate_score_bound(value: Optional[float], field_name: str, fallback: float) -> float:
    if value is None:
        return round(float(fallback), 2)
    if value < 0.0 or value > 100.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be between 0.0 and 100.0.",
        )
    return round(float(value), 2)


def _validate_iso_timestamp(ts_value: Optional[str]) -> str:
    if not ts_value or not ts_value.strip():
        return datetime.datetime.utcnow().isoformat()
    cleaned = ts_value.strip()
    candidate = cleaned.replace(" ", "T")
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        datetime.datetime.fromisoformat(candidate)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="created_at must be a valid ISO-8601 timestamp.",
        )
    return cleaned


def _resolve_import_owner(cursor, requested_owner_email: Optional[str], admin: dict) -> Tuple[str, str, bool]:
    """
    Resolve dataset owner by email if that account exists in production.
    Otherwise fall back to the configured platform administrator account.
    Returns (owner_id, owner_email, owner_fallback_used).
    """
    norm_requested = (requested_owner_email or "").strip().lower()
    if norm_requested:
        cursor.execute(
            "SELECT id, email FROM users WHERE LOWER(email) = ? LIMIT 1",
            (norm_requested,),
        )
        matched = cursor.fetchone()
        if matched:
            return matched["id"], matched["email"], False

    configured_admin_email = (
        getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com") or "datapulseapplication@gmail.com"
    ).strip().lower()
    cursor.execute(
        "SELECT id, email FROM users WHERE LOWER(email) = ? LIMIT 1",
        (configured_admin_email,),
    )
    admin_row = cursor.fetchone()
    if admin_row:
        fallback_used = bool(norm_requested and norm_requested != admin_row["email"].strip().lower())
        return admin_row["id"], admin_row["email"], fallback_used

    fallback_used = bool(norm_requested and norm_requested != (admin.get("email") or "").strip().lower())
    return admin["id"], admin["email"], fallback_used


def _build_existing_dataset_import_response(
    cursor,
    existing_ds,
    dry_run: bool,
    fallback_content_hash: str,
) -> AdminDatasetImportResponse:
    dataset_id = existing_ds["id"]
    cursor.execute("SELECT email FROM users WHERE id = ? LIMIT 1", (existing_ds["user_id"],))
    owner_row = cursor.fetchone()
    owner_email = owner_row["email"] if owner_row else ""

    cursor.execute("SELECT * FROM evaluations WHERE dataset_id = ? LIMIT 1", (dataset_id,))
    eval_row = cursor.fetchone()

    table_name = get_dataset_table_name(dataset_id)
    storage_ok = dataset_table_exists(dataset_id)
    duckdb_rows = get_dataset_row_count(dataset_id) if storage_ok else 0

    return AdminDatasetImportResponse(
        dataset_id=dataset_id,
        status="would_skip" if dry_run else "skipped",
        dry_run=dry_run,
        already_exists=True,
        name=existing_ds["name"],
        filename=existing_ds["filename"],
        domain=existing_ds["domain"],
        owner_id=existing_ds["user_id"],
        owner_email=owner_email,
        owner_fallback_used=False,
        rows_count=int(existing_ds["rows_count"] or 0),
        columns_count=int(existing_ds["columns_count"] or 0),
        unlock_price=int(existing_ds["unlock_price"] if existing_ds["unlock_price"] is not None else 10),
        quality_score=float(eval_row["quality_score"]) if eval_row else 0.0,
        schema_fidelity_score=float(eval_row["schema_fidelity_score"]) if eval_row else 0.0,
        completeness_score=float(eval_row["completeness_score"]) if eval_row else 0.0,
        domain_relevance_score=float(eval_row["domain_relevance_score"]) if eval_row else 0.0,
        overall_score=float(eval_row["overall_score"]) if eval_row else 0.0,
        credits_awarded=0,
        content_hash=(existing_ds["content_hash"] or fallback_content_hash),
        storage_available=storage_ok,
        duckdb_table_name=table_name,
        duckdb_row_count=duckdb_rows,
        created_at=existing_ds["created_at"],
        message=(
            f"Dry run: dataset '{dataset_id}' already exists and would be skipped."
            if dry_run
            else f"Dataset '{dataset_id}' already exists; skipped without modifying existing data."
        ),
    )


@router.post("/datasets/import", response_model=AdminDatasetImportResponse)
async def import_admin_dataset(
    request: Request,
    file: UploadFile = File(...),
    dataset_id: str = Form(...),
    name: str = Form(...),
    filename: Optional[str] = Form(None),
    domain: str = Form("general"),
    content_summary: Optional[str] = Form(None),
    unlock_price: int = Form(10),
    owner_email: Optional[str] = Form(None),
    created_at: Optional[str] = Form(None),
    quality_score: Optional[float] = Form(None),
    schema_fidelity_score: Optional[float] = Form(None),
    completeness_score: Optional[float] = Form(None),
    domain_relevance_score: Optional[float] = Form(None),
    overall_score: Optional[float] = Form(None),
    eval_status: str = Form("completed"),
    eval_progress: int = Form(100),
    dry_run: bool = Form(False),
    admin: dict = Depends(get_current_admin_user),
):
    """
    Admin-only idempotent dataset migration/import endpoint.

    Guarantees:
      - Requires verified administrator authentication (401/403 otherwise).
      - Preserves explicit dataset_id, metadata, evaluation scores, and unlock_price.
      - Preserves existing production owners by email; falls back to configured ADMIN_EMAIL.
      - Awards ZERO upload/quality credits and creates ZERO credit_transactions rows.
      - Allows distinct dataset_id listings even when CSV content_hash matches another listing.
      - Deduplicates strictly by dataset_id (skips cleanly if dataset_id already exists).
      - Supports dry_run=true with zero database or storage writes.
      - Atomic write with automatic SQLite + DuckDB + CSV rollback on any failure.
    """
    clean_dataset_id = (dataset_id or "").strip()
    if not clean_dataset_id or len(clean_dataset_id) > 64 or not DATASET_ID_REGEX.match(clean_dataset_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid dataset_id format. Must match '^ds_[a-zA-Z0-9_-]+$' and be <= 64 characters.",
        )

    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dataset name is required.",
        )

    raw_filename = (filename or file.filename or "").strip()
    effective_filename = os.path.basename(raw_filename.replace("\\", "/"))
    if not effective_filename or not effective_filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files (.csv) are supported for dataset import.",
        )

    clean_domain = (domain or "general").strip() or "general"

    if unlock_price < 0 or unlock_price > 10000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unlock_price must be between 0 and 10000.",
        )

    clean_eval_status = (eval_status or "completed").strip().lower()
    if clean_eval_status not in _VALID_EVAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"eval_status must be one of {sorted(_VALID_EVAL_STATUSES)}.",
        )

    if eval_progress < 0 or eval_progress > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="eval_progress must be between 0 and 100.",
        )

    effective_created_at = _validate_iso_timestamp(created_at)

    content_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(content_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"CSV file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )
    csv_content = content_bytes.decode("utf-8", errors="replace")

    eval_check = parse_and_evaluate_csv(csv_content, effective_filename, clean_domain)
    if not eval_check["valid"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=eval_check["error"],
        )

    cleaned_csv = eval_check.get("cleaned_csv") or csv_content
    content_hash = eval_check.get("content_hash") or ""
    rows_count = int(eval_check["rows_count"])
    columns_count = int(eval_check["columns_count"])
    schema_json_str = json.dumps(eval_check["schema"])

    computed_quality, computed_fidelity, computed_completeness, computed_relevance, computed_overall = (
        eval_check["scores"][:5]
    )
    final_quality = _validate_score_bound(quality_score, "quality_score", computed_quality)
    final_fidelity = _validate_score_bound(schema_fidelity_score, "schema_fidelity_score", computed_fidelity)
    final_completeness = _validate_score_bound(completeness_score, "completeness_score", computed_completeness)
    final_relevance = _validate_score_bound(domain_relevance_score, "domain_relevance_score", computed_relevance)
    final_overall = _validate_score_bound(overall_score, "overall_score", computed_overall)

    effective_summary = (
        (content_summary or "").strip()
        or f"Structured dataset with {rows_count} rows across {columns_count} columns in the {clean_domain} domain."
    )
    table_name = get_dataset_table_name(clean_dataset_id)
    client_ip = request.client.host if request.client else None

    with _dataset_import_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Strict ID-based idempotency check (never overwrites existing dataset)
        cursor.execute("SELECT * FROM datasets WHERE id = ? LIMIT 1", (clean_dataset_id,))
        existing_ds = cursor.fetchone()
        if existing_ds:
            resp = _build_existing_dataset_import_response(
                cursor=cursor,
                existing_ds=existing_ds,
                dry_run=dry_run,
                fallback_content_hash=content_hash,
            )
            if not dry_run:
                log_admin_audit(
                    admin_user_id=admin["id"],
                    admin_email=admin["email"],
                    action="IMPORT_DATASET_SKIPPED",
                    target_resource=clean_dataset_id,
                    details=f"Skipped existing dataset '{clean_dataset_id}' (storage_available={resp.storage_available})",
                    ip_address=client_ip,
                )
            return resp

        # 2. Resolve target owner (preserve existing user by email, else configured admin)
        resolved_owner_id, resolved_owner_email, owner_fallback_used = _resolve_import_owner(
            cursor=cursor,
            requested_owner_email=owner_email,
            admin=admin,
        )

        # 3. Dry-run exits before any write to disk, DuckDB, or SQLite
        if dry_run:
            return AdminDatasetImportResponse(
                dataset_id=clean_dataset_id,
                status="dry_run_ok",
                dry_run=True,
                already_exists=False,
                name=clean_name,
                filename=effective_filename,
                domain=clean_domain,
                owner_id=resolved_owner_id,
                owner_email=resolved_owner_email,
                owner_fallback_used=owner_fallback_used,
                rows_count=rows_count,
                columns_count=columns_count,
                unlock_price=unlock_price,
                quality_score=final_quality,
                schema_fidelity_score=final_fidelity,
                completeness_score=final_completeness,
                domain_relevance_score=final_relevance,
                overall_score=final_overall,
                credits_awarded=0,
                content_hash=content_hash,
                storage_available=False,
                duckdb_table_name=table_name,
                duckdb_row_count=0,
                created_at=effective_created_at,
                message=(
                    f"Dry run validated dataset '{clean_dataset_id}' ({rows_count} rows, {columns_count} cols). "
                    f"Owner resolved to {resolved_owner_email}"
                    + (" (fallback to admin)." if owner_fallback_used else " (preserved).")
                ),
            )

        # 4. Persist CSV + DuckDB analytical table
        try:
            persist_result = persist_dataset(
                dataset_id=clean_dataset_id,
                user_id=resolved_owner_id,
                filename=effective_filename,
                csv_content=cleaned_csv,
                rows_count=rows_count,
                columns_count=columns_count,
            )
        except Exception:
            logger.exception("Admin import failed during DuckDB/CSV persistence for %s", clean_dataset_id)
            delete_dataset_storage(clean_dataset_id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Failed to persist imported dataset into analytical storage.",
            )

        # 5. Atomic SQLite metadata + evaluation insert (strictly 0 credits awarded, 0 credit_transactions)
        evaluation_id = f"eval_{uuid.uuid4().hex[:12]}"
        try:
            if not dataset_table_exists(clean_dataset_id):
                raise RuntimeError(f"DuckDB table verification failed for {clean_dataset_id}")
            duckdb_rows = get_dataset_row_count(clean_dataset_id)
            duckdb_cols = len(get_dataset_columns(clean_dataset_id))
            if duckdb_rows != rows_count or duckdb_cols != columns_count:
                raise RuntimeError(
                    f"DuckDB verification mismatch for {clean_dataset_id}: "
                    f"expected {rows_count}x{columns_count}, got {duckdb_rows}x{duckdb_cols}"
                )

            cursor.execute(
                """
                INSERT INTO datasets (
                    id, user_id, name, filename, domain, rows_count, columns_count,
                    schema_json, content_summary, unlock_price, content_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_dataset_id,
                    resolved_owner_id,
                    clean_name,
                    effective_filename,
                    clean_domain,
                    rows_count,
                    columns_count,
                    schema_json_str,
                    effective_summary,
                    unlock_price,
                    content_hash,
                    effective_created_at,
                ),
            )

            cursor.execute(
                """
                INSERT INTO evaluations (
                    id, dataset_id, status, progress, quality_score, schema_fidelity_score,
                    completeness_score, domain_relevance_score, overall_score, credits_awarded,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    evaluation_id,
                    clean_dataset_id,
                    clean_eval_status,
                    eval_progress,
                    final_quality,
                    final_fidelity,
                    final_completeness,
                    final_relevance,
                    final_overall,
                    effective_created_at,
                    effective_created_at,
                ),
            )

            conn.commit()
        except Exception:
            conn.rollback()
            delete_dataset_storage(clean_dataset_id)
            logger.exception("Admin import failed during SQLite registration/verification for %s; rolled back.", clean_dataset_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to register dataset '{clean_dataset_id}'; all changes rolled back.",
            )

        log_admin_audit(
            admin_user_id=admin["id"],
            admin_email=admin["email"],
            action="IMPORT_DATASET",
            target_resource=clean_dataset_id,
            details=(
                f"Imported dataset '{clean_name}' ({rows_count}x{columns_count}, unlock={unlock_price} cr, "
                f"owner={resolved_owner_email}, fallback={owner_fallback_used}, migration_credits=0)"
            ),
            ip_address=client_ip,
        )

        return AdminDatasetImportResponse(
            dataset_id=clean_dataset_id,
            status="imported",
            dry_run=False,
            already_exists=False,
            name=clean_name,
            filename=effective_filename,
            domain=clean_domain,
            owner_id=resolved_owner_id,
            owner_email=resolved_owner_email,
            owner_fallback_used=owner_fallback_used,
            rows_count=rows_count,
            columns_count=columns_count,
            unlock_price=unlock_price,
            quality_score=final_quality,
            schema_fidelity_score=final_fidelity,
            completeness_score=final_completeness,
            domain_relevance_score=final_relevance,
            overall_score=final_overall,
            credits_awarded=0,
            content_hash=content_hash,
            storage_available=True,
            duckdb_table_name=persist_result["table_name"],
            duckdb_row_count=int(persist_result["rows_count"]),
            created_at=effective_created_at,
            message=f"Successfully imported dataset '{clean_dataset_id}' with 0 migration credits.",
        )
