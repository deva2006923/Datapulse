#!/usr/bin/env python3
"""
DataPulse Local-to-Production Dataset Migration Tool.

Safely migrates ONLY the five explicitly approved genuine local datasets from
local SQLite (`datapulse.db`) + local CSV storage (`storage/datasets/`) to a
DataPulse backend via the admin-only `POST /admin/datasets/import` endpoint.

Key Safety Guarantees:
  - Strict allowlist of the 5 approved dataset IDs (never touches the 556 test datasets).
  - Opens local SQLite strictly in read-only mode (`mode=ro`); never modifies local data.
  - Defaults to `--dry-run`; requires explicit `--execute` to write to target backend.
  - Preserves original dataset IDs, names, metadata, evaluation scores, and unlock prices.
  - Preserves existing target owners by email; otherwise assigns to configured admin email.
  - Awards ZERO upload/quality credits and creates ZERO credit_transactions rows.
  - Supports idempotency (re-runs skip existing dataset IDs safely).
  - Supports automatic rollback of newly imported datasets if any step or verification fails.
  - Never accepts passwords on the CLI and never prints passwords or bearer tokens.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_TARGET_URL = "https://datapulse-1215.onrender.com"
DEFAULT_ADMIN_EMAIL = "datapulseapplication@gmail.com"
DEFAULT_SQLITE_PATH = "datapulse.db"
DEFAULT_STORAGE_DIR = "storage/datasets"

# Strict allowlist: ONLY the 5 genuine user-uploaded dataset listings.
# Automated test datasets (556 rows) are explicitly excluded and rejected.
APPROVED_DATASET_IDS: Tuple[str, ...] = (
    "ds_4ea9dd2fad18",
    "ds_29bdba6e06c4",
    "ds_1145c9ac8987",
    "ds_90ec661cdf80",
    "ds_affea73a8720",
)
APPROVED_DATASET_ID_SET = frozenset(APPROVED_DATASET_IDS)


@dataclass(frozen=True)
class LocalDatasetRecord:
    dataset_id: str
    name: str
    filename: str
    domain: str
    rows_count: int
    columns_count: int
    content_summary: str
    unlock_price: int
    owner_email: str
    created_at: str
    quality_score: float
    schema_fidelity_score: float
    completeness_score: float
    domain_relevance_score: float
    overall_score: float
    eval_status: str
    eval_progress: int
    csv_path: Path


@dataclass
class HttpResponse:
    status: int
    body: Any


def validate_requested_dataset_ids(requested_ids: Optional[Sequence[str]]) -> Tuple[str, ...]:
    """Enforce the strict 5-dataset allowlist; reject any non-approved dataset ID."""
    if not requested_ids:
        return APPROVED_DATASET_IDS

    cleaned: List[str] = []
    seen = set()
    invalid: List[str] = []
    for raw in requested_ids:
        ds_id = (raw or "").strip()
        if not ds_id:
            continue
        if ds_id not in APPROVED_DATASET_ID_SET:
            invalid.append(ds_id)
        elif ds_id not in seen:
            seen.add(ds_id)
            cleaned.append(ds_id)

    if invalid:
        raise ValueError(
            f"Refusing to migrate unapproved dataset ID(s): {', '.join(invalid)}. "
            f"Allowed IDs: {', '.join(APPROVED_DATASET_IDS)}"
        )
    if not cleaned:
        raise ValueError("No valid approved dataset IDs selected.")
    return tuple(cleaned)


def load_approved_local_datasets(
    sqlite_path: str | Path = DEFAULT_SQLITE_PATH,
    storage_dir: str | Path = DEFAULT_STORAGE_DIR,
    requested_ids: Optional[Sequence[str]] = None,
) -> List[LocalDatasetRecord]:
    """
    Read ONLY the approved dataset records from local SQLite (read-only mode)
    and verify their corresponding local CSV files exist and are non-empty.
    """
    target_ids = validate_requested_dataset_ids(requested_ids)
    db_file = Path(sqlite_path).resolve()
    csv_dir = Path(storage_dir).resolve()

    if not db_file.exists():
        raise FileNotFoundError(f"Local SQLite database not found: {db_file}")
    if not csv_dir.exists():
        raise FileNotFoundError(f"Local CSV storage directory not found: {csv_dir}")

    # Open strictly read-only so local database is never modified
    uri = f"file:{db_file.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in target_ids)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                d.id,
                d.name,
                d.filename,
                d.domain,
                d.rows_count,
                d.columns_count,
                d.content_summary,
                d.unlock_price,
                d.created_at,
                COALESCE(u.email, '') AS owner_email,
                COALESCE(e.status, 'completed') AS eval_status,
                COALESCE(e.progress, 100) AS eval_progress,
                COALESCE(e.quality_score, 0.0) AS quality_score,
                COALESCE(e.schema_fidelity_score, 0.0) AS schema_fidelity_score,
                COALESCE(e.completeness_score, 0.0) AS completeness_score,
                COALESCE(e.domain_relevance_score, 0.0) AS domain_relevance_score,
                COALESCE(e.overall_score, 0.0) AS overall_score
            FROM datasets d
            LEFT JOIN users u ON d.user_id = u.id
            LEFT JOIN evaluations e ON d.id = e.dataset_id
            WHERE d.id IN ({placeholders})
            """,
            list(target_ids),
        )
        rows_by_id = {row["id"]: row for row in cursor.fetchall()}
    finally:
        conn.close()

    missing_db_ids = [ds_id for ds_id in target_ids if ds_id not in rows_by_id]
    if missing_db_ids:
        raise RuntimeError(
            f"Approved dataset(s) missing from local SQLite ({db_file}): {', '.join(missing_db_ids)}"
        )

    records: List[LocalDatasetRecord] = []
    for ds_id in target_ids:
        r = rows_by_id[ds_id]
        csv_path = csv_dir / f"{ds_id}.csv"
        if not csv_path.exists() or csv_path.stat().st_size == 0:
            raise FileNotFoundError(f"Local CSV file missing or empty for {ds_id}: {csv_path}")

        records.append(
            LocalDatasetRecord(
                dataset_id=ds_id,
                name=str(r["name"]),
                filename=str(r["filename"]),
                domain=str(r["domain"] or "general"),
                rows_count=int(r["rows_count"]),
                columns_count=int(r["columns_count"]),
                content_summary=str(r["content_summary"] or ""),
                unlock_price=int(r["unlock_price"] if r["unlock_price"] is not None else 10),
                owner_email=str(r["owner_email"] or "").strip(),
                created_at=str(r["created_at"]),
                quality_score=float(r["quality_score"]),
                schema_fidelity_score=float(r["schema_fidelity_score"]),
                completeness_score=float(r["completeness_score"]),
                domain_relevance_score=float(r["domain_relevance_score"]),
                overall_score=float(r["overall_score"]),
                eval_status=str(r["eval_status"] or "completed"),
                eval_progress=int(r["eval_progress"] if r["eval_progress"] is not None else 100),
                csv_path=csv_path,
            )
        )
    return records


def encode_multipart_formdata(
    fields: Dict[str, str],
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str = "text/csv",
) -> Tuple[bytes, str]:
    """Pure-stdlib RFC-7578 multipart/form-data encoder."""
    boundary = f"----DataPulseMigration{uuid.uuid4().hex}"
    chunks: List[bytes] = []

    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    safe_filename = os.path.basename(filename.replace("\\", "/")).replace('"', "_")
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_filename}"\r\n'.encode("utf-8")
    )
    chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(chunks)
    header_value = f"multipart/form-data; boundary={boundary}"
    return body, header_value


RequesterFn = Callable[[str, str, Dict[str, str], Optional[bytes]], HttpResponse]


def build_urllib_requester(base_url: str, timeout: int = 90) -> RequesterFn:
    normalized_base = base_url.rstrip("/")

    def _request(
        method: str,
        path: str,
        headers: Dict[str, str],
        data: Optional[bytes] = None,
    ) -> HttpResponse:
        url = f"{normalized_base}{path}"
        req_headers = {"Accept": "application/json", "User-Agent": "DataPulse-Dataset-Migrator/1.0"}
        req_headers.update(headers)
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = raw
                return HttpResponse(status=resp.status, body=parsed)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return HttpResponse(status=exc.code, body=parsed)

    return _request


def _build_import_form_fields(rec: LocalDatasetRecord, dry_run: bool) -> Dict[str, str]:
    return {
        "dataset_id": rec.dataset_id,
        "name": rec.name,
        "filename": rec.filename,
        "domain": rec.domain,
        "content_summary": rec.content_summary,
        "unlock_price": str(rec.unlock_price),
        "owner_email": rec.owner_email,
        "created_at": rec.created_at,
        "quality_score": f"{rec.quality_score:.2f}",
        "schema_fidelity_score": f"{rec.schema_fidelity_score:.2f}",
        "completeness_score": f"{rec.completeness_score:.2f}",
        "domain_relevance_score": f"{rec.domain_relevance_score:.2f}",
        "overall_score": f"{rec.overall_score:.2f}",
        "eval_status": rec.eval_status,
        "eval_progress": str(rec.eval_progress),
        "dry_run": "true" if dry_run else "false",
    }


def _approx_equal(a: Optional[float], b: float, tol: float = 0.05) -> bool:
    if a is None:
        return False
    return abs(float(a) - float(b)) <= tol


def _rollback_imported_datasets(
    requester: RequesterFn,
    auth_headers: Dict[str, str],
    imported_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    """Deletes ONLY dataset IDs newly created during the current failed migration run."""
    rollback_results: List[Dict[str, Any]] = []
    for ds_id in reversed(list(imported_ids)):
        resp = requester("DELETE", f"/datasets/{ds_id}", auth_headers, None)
        rollback_results.append(
            {
                "dataset_id": ds_id,
                "status_code": resp.status,
                "rolled_back": resp.status == 200,
            }
        )
    return rollback_results


def _verify_post_import(
    requester: RequesterFn,
    auth_headers: Dict[str, str],
    records: Sequence[LocalDatasetRecord],
    import_results: Dict[str, Dict[str, Any]],
    pre_credits_in_circulation: int,
    pre_tx_total: int,
    verify_query: bool = False,
) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Complete post-import verification:
      1. Public catalog `/datasets` contains every target dataset with `storage_available=True` and matching metadata.
      2. `/datasets/{id}/evaluation` preserves all quality scores and has `credits_awarded == 0`.
      3. `/admin/datasets/{id}` confirms DuckDB availability, owner resolution, schema columns, and 0 migration rewards.
      4. `/admin/overview` and `/admin/transactions` confirm zero migration credits and zero new reward transactions.
      5. Optional `/query` check when `--verify-query` is enabled.
    """
    errors: List[str] = []
    checks: List[Dict[str, Any]] = []

    ds_list_resp = requester("GET", "/datasets", {}, None)
    if ds_list_resp.status != 200 or not isinstance(ds_list_resp.body, dict):
        errors.append(f"GET /datasets failed during verification (HTTP {ds_list_resp.status})")
        return False, errors, checks

    catalog_by_id = {d.get("id"): d for d in ds_list_resp.body.get("datasets", [])}

    for rec in records:
        ds_id = rec.dataset_id
        ds_item = catalog_by_id.get(ds_id)
        item_errors: List[str] = []

        if not ds_item:
            item_errors.append("missing from GET /datasets")
        else:
            if ds_item.get("name") != rec.name:
                item_errors.append(f"name mismatch: {ds_item.get('name')!r} != {rec.name!r}")
            if ds_item.get("filename") != rec.filename:
                item_errors.append(f"filename mismatch: {ds_item.get('filename')!r} != {rec.filename!r}")
            if ds_item.get("domain") != rec.domain:
                item_errors.append(f"domain mismatch: {ds_item.get('domain')!r} != {rec.domain!r}")
            if int(ds_item.get("rows_count", -1)) != rec.rows_count:
                item_errors.append(f"rows_count mismatch: {ds_item.get('rows_count')} != {rec.rows_count}")
            if int(ds_item.get("columns_count", -1)) != rec.columns_count:
                item_errors.append(f"columns_count mismatch: {ds_item.get('columns_count')} != {rec.columns_count}")
            if int(ds_item.get("unlock_price", -1)) != rec.unlock_price:
                item_errors.append(f"unlock_price mismatch: {ds_item.get('unlock_price')} != {rec.unlock_price}")
            if ds_item.get("storage_available") is not True or ds_item.get("availability") != "Available":
                item_errors.append(
                    f"storage not available (storage_available={ds_item.get('storage_available')}, "
                    f"availability={ds_item.get('availability')})"
                )
            if not _approx_equal(ds_item.get("overall_score"), rec.overall_score):
                item_errors.append(f"overall_score mismatch: {ds_item.get('overall_score')} != {rec.overall_score}")

        eval_resp = requester("GET", f"/datasets/{ds_id}/evaluation", {}, None)
        if eval_resp.status != 200 or not isinstance(eval_resp.body, dict):
            item_errors.append(f"GET /datasets/{ds_id}/evaluation returned HTTP {eval_resp.status}")
        else:
            ev = eval_resp.body
            if ev.get("status") != rec.eval_status:
                item_errors.append(f"eval status mismatch: {ev.get('status')} != {rec.eval_status}")
            if not _approx_equal(ev.get("quality_score"), rec.quality_score):
                item_errors.append(f"quality_score mismatch: {ev.get('quality_score')} != {rec.quality_score}")
            if not _approx_equal(ev.get("schema_fidelity_score"), rec.schema_fidelity_score):
                item_errors.append(
                    f"schema_fidelity_score mismatch: {ev.get('schema_fidelity_score')} != {rec.schema_fidelity_score}"
                )
            if not _approx_equal(ev.get("completeness_score"), rec.completeness_score):
                item_errors.append(
                    f"completeness_score mismatch: {ev.get('completeness_score')} != {rec.completeness_score}"
                )
            if not _approx_equal(ev.get("domain_relevance_score"), rec.domain_relevance_score):
                item_errors.append(
                    f"domain_relevance_score mismatch: {ev.get('domain_relevance_score')} != {rec.domain_relevance_score}"
                )
            if import_results.get(ds_id, {}).get("status") == "imported" and int(ev.get("credits_awarded", -1)) != 0:
                item_errors.append(f"expected credits_awarded=0, got {ev.get('credits_awarded')}")

        admin_ds_resp = requester("GET", f"/admin/datasets/{ds_id}", auth_headers, None)
        if admin_ds_resp.status != 200 or not isinstance(admin_ds_resp.body, dict):
            item_errors.append(f"GET /admin/datasets/{ds_id} returned HTTP {admin_ds_resp.status}")
        else:
            ad = admin_ds_resp.body
            if ad.get("availability") != "Available":
                item_errors.append(f"admin availability={ad.get('availability')}")
            if len(ad.get("schema_columns", [])) != rec.columns_count:
                item_errors.append(
                    f"admin schema_columns len={len(ad.get('schema_columns', []))} != {rec.columns_count}"
                )
            if import_results.get(ds_id, {}).get("status") == "imported":
                if int(ad.get("total_rewards", -1)) != 0:
                    item_errors.append(f"expected admin total_rewards=0, got {ad.get('total_rewards')}")

        # Credit invariance check BEFORE optional live query test (since non-owner queries charge 1 credit)
        checks.append(
            {
                "dataset_id": ds_id,
                "verified": len(item_errors) == 0,
                "errors": item_errors,
            }
        )
        for err in item_errors:
            errors.append(f"{ds_id}: {err}")

    # Verify zero migration credits & zero new credit transactions
    ov_after = requester("GET", "/admin/overview", auth_headers, None)
    tx_after = requester("GET", "/admin/transactions?limit=1", auth_headers, None)
    if ov_after.status != 200 or not isinstance(ov_after.body, dict):
        errors.append(f"GET /admin/overview failed post-import (HTTP {ov_after.status})")
    else:
        post_credits = int(ov_after.body.get("total_credits_in_circulation", -1))
        if post_credits != pre_credits_in_circulation:
            errors.append(
                f"Credits in circulation changed during migration: {pre_credits_in_circulation} -> {post_credits}"
            )
    if tx_after.status != 200 or not isinstance(tx_after.body, dict):
        errors.append(f"GET /admin/transactions failed post-import (HTTP {tx_after.status})")
    else:
        post_tx_total = int(tx_after.body.get("total", -1))
        if post_tx_total != pre_tx_total:
            errors.append(
                f"Credit transaction count changed during migration: {pre_tx_total} -> {post_tx_total}"
            )

    if verify_query and not errors:
        for rec in records:
            q_payload = json.dumps(
                {"dataset_id": rec.dataset_id, "query": "How many rows are in this dataset?"}
            ).encode("utf-8")
            q_headers = dict(auth_headers)
            q_headers["Content-Type"] = "application/json"
            q_resp = requester("POST", "/query", q_headers, q_payload)
            if q_resp.status != 200:
                errors.append(f"{rec.dataset_id}: live query verification failed (HTTP {q_resp.status})")

    return len(errors) == 0, errors, checks


def run_migration(
    records: Sequence[LocalDatasetRecord],
    requester: RequesterFn,
    admin_email: str,
    admin_password: str,
    dry_run: bool = True,
    rollback_on_error: bool = True,
    verify_query: bool = False,
) -> Dict[str, Any]:
    """Execute dry-run or live migration workflow with verification and rollback."""
    # 1. Health check
    health_resp = requester("GET", "/health", {}, None)
    if health_resp.status != 200 or not isinstance(health_resp.body, dict):
        raise RuntimeError(f"Target health check failed (HTTP {health_resp.status})")
    if health_resp.body.get("status") != "ok" or not health_resp.body.get("database_ok") or not health_resp.body.get("storage_ok"):
        raise RuntimeError(f"Target backend is not healthy: {health_resp.body}")

    # 2. Authenticate admin (never store or print plaintext password/token in report)
    login_body = json.dumps({"email": admin_email, "password": admin_password}).encode("utf-8")
    login_resp = requester("POST", "/auth/login", {"Content-Type": "application/json"}, login_body)
    if login_resp.status != 200 or not isinstance(login_resp.body, dict):
        detail = login_resp.body.get("detail") if isinstance(login_resp.body, dict) else "Authentication failed"
        raise RuntimeError(f"Admin authentication failed (HTTP {login_resp.status}): {detail}")

    token = login_resp.body.get("access_token")
    user_info = login_resp.body.get("user") or {}
    if not token or not user_info.get("is_admin"):
        raise RuntimeError("Authenticated account does not hold verified administrator privileges.")

    auth_headers = {"Authorization": f"Bearer {token}"}

    # 3. Capture pre-migration snapshot
    ov_before = requester("GET", "/admin/overview", auth_headers, None)
    tx_before = requester("GET", "/admin/transactions?limit=1", auth_headers, None)
    if ov_before.status != 200 or not isinstance(ov_before.body, dict):
        raise RuntimeError(f"Failed to read GET /admin/overview (HTTP {ov_before.status})")
    if tx_before.status != 200 or not isinstance(tx_before.body, dict):
        raise RuntimeError(f"Failed to read GET /admin/transactions (HTTP {tx_before.status})")

    pre_credits_in_circulation = int(ov_before.body.get("total_credits_in_circulation", 0))
    pre_datasets_total = int(ov_before.body.get("total_datasets", 0))
    pre_tx_total = int(tx_before.body.get("total", 0))

    # 4. Run dry-run or live import for each approved dataset
    results: List[Dict[str, Any]] = []
    results_by_id: Dict[str, Dict[str, Any]] = {}
    newly_imported_ids: List[str] = []
    errors: List[str] = []
    rollback_report: List[Dict[str, Any]] = []

    for rec in records:
        csv_bytes = rec.csv_path.read_bytes()
        form_fields = _build_import_form_fields(rec, dry_run=dry_run)
        body_bytes, content_type = encode_multipart_formdata(
            fields=form_fields,
            file_field="file",
            filename=rec.filename,
            file_bytes=csv_bytes,
        )
        req_headers = dict(auth_headers)
        req_headers["Content-Type"] = content_type

        resp = requester("POST", "/admin/datasets/import", req_headers, body_bytes)
        if resp.status != 200 or not isinstance(resp.body, dict):
            detail = resp.body.get("detail") if isinstance(resp.body, dict) else str(resp.body)[:200]
            errors.append(f"{rec.dataset_id}: HTTP {resp.status} - {detail}")
            results.append(
                {
                    "dataset_id": rec.dataset_id,
                    "name": rec.name,
                    "status": "error",
                    "http_status": resp.status,
                    "detail": detail,
                }
            )
            if not dry_run and rollback_on_error and newly_imported_ids:
                rollback_report = _rollback_imported_datasets(requester, auth_headers, newly_imported_ids)
            break

        item_result = dict(resp.body)
        results.append(item_result)
        results_by_id[rec.dataset_id] = item_result
        if item_result.get("status") == "imported":
            newly_imported_ids.append(rec.dataset_id)

    # 5. Post-import verification (only for --execute when all imports succeeded)
    verification: Optional[Dict[str, Any]] = None
    if not dry_run and not errors:
        verified, ver_errors, ver_checks = _verify_post_import(
            requester=requester,
            auth_headers=auth_headers,
            records=records,
            import_results=results_by_id,
            pre_credits_in_circulation=pre_credits_in_circulation,
            pre_tx_total=pre_tx_total,
            verify_query=verify_query,
        )
        verification = {
            "passed": verified,
            "errors": ver_errors,
            "checks": ver_checks,
        }
        if not verified:
            errors.extend(ver_errors)
            if rollback_on_error and newly_imported_ids:
                rollback_report = _rollback_imported_datasets(requester, auth_headers, newly_imported_ids)

    ov_final = requester("GET", "/admin/overview", auth_headers, None)
    post_datasets_total = (
        int(ov_final.body.get("total_datasets", pre_datasets_total))
        if ov_final.status == 200 and isinstance(ov_final.body, dict)
        else pre_datasets_total
    )
    post_credits_total = (
        int(ov_final.body.get("total_credits_in_circulation", pre_credits_in_circulation))
        if ov_final.status == 200 and isinstance(ov_final.body, dict)
        else pre_credits_in_circulation
    )

    return {
        "mode": "dry_run" if dry_run else "execute",
        "success": len(errors) == 0,
        "approved_dataset_count": len(records),
        "pre_snapshot": {
            "total_datasets": pre_datasets_total,
            "total_credits_in_circulation": pre_credits_in_circulation,
            "total_credit_transactions": pre_tx_total,
        },
        "post_snapshot": {
            "total_datasets": post_datasets_total,
            "total_credits_in_circulation": post_credits_total,
        },
        "imported_count": sum(1 for r in results if r.get("status") == "imported"),
        "skipped_count": sum(1 for r in results if r.get("status") in ("skipped", "would_skip")),
        "dry_run_ready_count": sum(1 for r in results if r.get("status") == "dry_run_ok"),
        "results": results,
        "verification": verification,
        "rollback": rollback_report,
        "errors": errors,
    }


def _print_report(report: Dict[str, Any]) -> None:
    mode_label = "DRY RUN (NO WRITES)" if report["mode"] == "dry_run" else "LIVE EXECUTION"
    print(f"\n=== DataPulse Dataset Migration Report [{mode_label}] ===")
    print(
        f"Approved datasets selected : {report['approved_dataset_count']}\n"
        f"Pre-migration datasets     : {report['pre_snapshot']['total_datasets']}\n"
        f"Post-migration datasets    : {report['post_snapshot']['total_datasets']}\n"
        f"Credits in circulation     : {report['pre_snapshot']['total_credits_in_circulation']} -> "
        f"{report['post_snapshot']['total_credits_in_circulation']} (delta="
        f"{report['post_snapshot']['total_credits_in_circulation'] - report['pre_snapshot']['total_credits_in_circulation']})\n"
    )

    header = f"{'Dataset ID':<16} {'Status':<12} {'Rows x Cols':<13} {'Price':>5} {'Score':>6} {'Credits':>7} {'Owner Email'}"
    print(header)
    print("-" * len(header))
    for item in report["results"]:
        ds_id = item.get("dataset_id", "")
        st = item.get("status", "unknown")
        dims = f"{item.get('rows_count', '?')}x{item.get('columns_count', '?')}"
        price = item.get("unlock_price", "?")
        score = f"{item['overall_score']:.2f}" if isinstance(item.get("overall_score"), (int, float)) else "?"
        cr = item.get("credits_awarded", 0)
        owner = item.get("owner_email", item.get("detail", ""))
        if item.get("owner_fallback_used"):
            owner = f"{owner} (admin fallback)"
        print(f"{ds_id:<16} {st:<12} {dims:<13} {str(price):>5} {score:>6} {str(cr):>7} {owner}")

    if report.get("verification") is not None:
        v = report["verification"]
        print(f"\nPost-import verification   : {'PASSED' if v['passed'] else 'FAILED'}")
    if report.get("rollback"):
        print(f"Rollback executed for      : {[r['dataset_id'] for r in report['rollback']]}")
    if report.get("errors"):
        print("\nErrors:")
        for err in report["errors"]:
            print(f"  - {err}")
    print()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate the 5 approved local DataPulse datasets to a target backend (defaults to --dry-run)."
    )
    parser.add_argument(
        "--target-url",
        default=DEFAULT_TARGET_URL,
        help=f"Target DataPulse backend base URL (default: {DEFAULT_TARGET_URL})",
    )
    parser.add_argument(
        "--admin-email",
        default=os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL),
        help=f"Admin account email (default: {DEFAULT_ADMIN_EMAIL})",
    )
    parser.add_argument(
        "--sqlite-path",
        default=DEFAULT_SQLITE_PATH,
        help=f"Path to local SQLite database (opened read-only; default: {DEFAULT_SQLITE_PATH})",
    )
    parser.add_argument(
        "--storage-dir",
        default=DEFAULT_STORAGE_DIR,
        help=f"Path to local CSV storage directory (default: {DEFAULT_STORAGE_DIR})",
    )
    parser.add_argument(
        "--dataset-ids",
        default=None,
        help="Optional comma-separated subset of the 5 approved dataset IDs.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate and preview migration without modifying target database or storage (default).",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute the live import and post-import verification against the target backend.",
    )
    parser.add_argument(
        "--no-rollback-on-error",
        action="store_true",
        default=False,
        help="Disable automatic rollback of newly imported datasets if an error occurs mid-batch.",
    )
    parser.add_argument(
        "--verify-query",
        action="store_true",
        default=False,
        help="Also run a live POST /query test per imported dataset during verification.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="HTTP timeout in seconds (default: 90s for Render cold starts).",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Output machine-readable JSON report (never includes credentials or tokens).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    dry_run = not args.execute

    requested_ids = [s.strip() for s in args.dataset_ids.split(",")] if args.dataset_ids else None
    try:
        records = load_approved_local_datasets(
            sqlite_path=args.sqlite_path,
            storage_dir=args.storage_dir,
            requested_ids=requested_ids,
        )
    except Exception as exc:
        print(f"ERROR loading approved local datasets: {exc}", file=sys.stderr)
        return 2

    admin_password = os.environ.get("ADMIN_PASSWORD") or ""
    if not admin_password:
        try:
            admin_password = getpass.getpass(f"Admin password for {args.admin_email} (hidden): ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted: admin password is required.", file=sys.stderr)
            return 2
    if not admin_password.strip():
        print("ERROR: Admin password cannot be empty.", file=sys.stderr)
        return 2

    requester = build_urllib_requester(args.target_url, timeout=args.timeout)
    try:
        report = run_migration(
            records=records,
            requester=requester,
            admin_email=args.admin_email,
            admin_password=admin_password,
            dry_run=dry_run,
            rollback_on_error=not args.no_rollback_on_error,
            verify_query=args.verify_query,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)

    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

