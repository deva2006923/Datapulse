import csv
import hashlib
import io
import json
import re
import uuid
import datetime
from typing import Dict, Any, Tuple
from app.database import get_db_connection

from app.services.storage import sanitize_headers
from app.services.pricing import calculate_dataset_unlock_price
from app.services.reputation import sync_and_get_user_reputation

BASIC_UPLOAD_REWARD = 50
MAX_CSV_COLUMNS = 250
MAX_CSV_ROWS = 250000
_SIGNED_NUMBER_RE = re.compile(r"^[+-]\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")


def sanitize_csv_cell(cell: str) -> str:
    """
    Neutralize spreadsheet formula injection payloads (=, @, tab, CR, or non-numeric +/-)
    while preserving legitimate signed numeric values (e.g. -42, -3.14, +100).
    """
    if not cell:
        return cell
    trimmed_left = cell.lstrip(" ")
    if not trimmed_left:
        return cell
    first = trimmed_left[0]
    if first in ("=", "@", "\t", "\r"):
        return "'" + cell
    if first in ("+", "-") and not _SIGNED_NUMBER_RE.match(trimmed_left.strip()):
        return "'" + cell
    return cell


def compute_csv_content_hash(cleaned_csv: str) -> str:
    """Compute a deterministic SHA-256 fingerprint of normalized CSV content."""
    normalized = (cleaned_csv or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def parse_and_evaluate_csv(csv_content: str, filename: str, domain: str) -> Dict[str, Any]:
    """
    Evaluate dataset quality:
    - schema fidelity
    - completeness
    - domain relevance
    - overall score, credits awarded (basic + quality), and dynamic unlock price
    """
    if not csv_content or not csv_content.strip():
        return {
            "valid": False,
            "error": "CSV file is empty",
            "rows_count": 0,
            "columns_count": 0,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "content_hash": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }

    if "\x00" in csv_content:
        return {
            "valid": False,
            "error": "Malformed CSV: binary or null-byte content is not permitted",
            "rows_count": 0,
            "columns_count": 0,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "content_hash": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }

    try:
        f = io.StringIO(csv_content.strip())
        reader = csv.reader(f)
        header = next(reader)
    except StopIteration:
        return {
            "valid": False,
            "error": "CSV file is empty",
            "rows_count": 0,
            "columns_count": 0,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Failed to parse CSV header: {str(e)}",
            "rows_count": 0,
            "columns_count": 0,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }
    
    try:
        rows = list(reader)
    except Exception as e:
        return {
            "valid": False,
            "error": f"Failed to parse CSV rows: {str(e)}",
            "rows_count": 0,
            "columns_count": 0,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }

    total_rows = len(rows)
    total_cols = len(header)
    
    if total_rows == 0 or total_cols == 0:
        return {
            "valid": False,
            "error": "Dataset must have at least one data row and column",
            "rows_count": total_rows,
            "columns_count": total_cols,
            "schema": {h: "string" for h in header},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "content_hash": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }

    if total_cols > MAX_CSV_COLUMNS:
        return {
            "valid": False,
            "error": f"CSV exceeds maximum supported column count ({MAX_CSV_COLUMNS})",
            "rows_count": total_rows,
            "columns_count": total_cols,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "content_hash": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }

    if total_rows > MAX_CSV_ROWS:
        return {
            "valid": False,
            "error": f"CSV exceeds maximum supported row count ({MAX_CSV_ROWS})",
            "rows_count": total_rows,
            "columns_count": total_cols,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0.0, 0, 5),
            "cleaned_csv": "",
            "content_hash": "",
            "unlock_price": 5,
            "basic_reward": 0,
            "quality_reward": 0
        }
        
    # Sanitize and deduplicate column names
    clean_header = sanitize_headers(header)

    # Normalize ragged rows and neutralize spreadsheet formula injection payloads
    sanitized_rows = []
    for row in rows:
        if len(row) < total_cols:
            padded = list(row) + [""] * (total_cols - len(row))
        elif len(row) > total_cols:
            padded = list(row[:total_cols])
        else:
            padded = list(row)
        sanitized_rows.append([sanitize_csv_cell(cell) for cell in padded])
    rows = sanitized_rows

    # Reconstruct cleaned CSV
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(clean_header)
    for row in rows:
        writer.writerow(row)
    cleaned_csv = out.getvalue()
    content_hash = compute_csv_content_hash(cleaned_csv)

    # Completeness check
    empty_cells = sum(row.count("") for row in rows)
    total_cells = total_rows * total_cols
    completeness_score = round(max(0.0, 100.0 * (1.0 - (empty_cells / total_cells))), 2)
    
    # Schema fidelity check
    schema = {}
    type_fidelity_points = 0
    for col_idx, col_name in enumerate(clean_header):
        types_seen = set()
        for row in rows:
            if col_idx < len(row):
                val = row[col_idx].strip()
                if val.isdigit():
                    types_seen.add("integer")
                elif val.replace(".", "", 1).isdigit() and "." in val:
                    types_seen.add("float")
                else:
                    types_seen.add("string")
        primary_type = "float" if "float" in types_seen else ("integer" if "integer" in types_seen else "string")
        schema[col_name] = primary_type
        if len(types_seen) <= 2:
            type_fidelity_points += 1
            
    schema_fidelity_score = round((type_fidelity_points / total_cols) * 100.0, 2)
    
    # Domain relevance check
    domain_relevance_score = 90.0 if domain and domain.lower() in ("finance", "healthcare", "ecommerce", "technology", "logistics") else 85.0
    
    # Overall score
    overall_score = round((0.4 * completeness_score) + (0.35 * schema_fidelity_score) + (0.25 * domain_relevance_score), 2)
    quality_score = overall_score
    
    # Documented & configurable rewards:
    # 1. Basic Upload Reward: 50 credits base for accepted upload
    # 2. Quality Reward: up to 50 credits based on actual overall score (50% of score)
    basic_reward = BASIC_UPLOAD_REWARD
    quality_reward = int(round(overall_score * 0.50))
    credits_awarded = basic_reward + quality_reward

    # Deterministic dataset unlock price
    unlock_price = calculate_dataset_unlock_price(
        quality_score=quality_score,
        completeness_score=completeness_score,
        domain_relevance_score=domain_relevance_score,
        rows_count=total_rows,
        columns_count=total_cols
    )
    
    return {
        "valid": True,
        "error": None,
        "rows_count": total_rows,
        "columns_count": total_cols,
        "schema": schema,
        "scores": (quality_score, schema_fidelity_score, completeness_score, domain_relevance_score, overall_score, credits_awarded, unlock_price),
        "cleaned_csv": cleaned_csv,
        "content_hash": content_hash,
        "unlock_price": unlock_price,
        "basic_reward": basic_reward,
        "quality_reward": quality_reward
    }

def run_evaluation_pipeline(evaluation_id: str, dataset_id: str, csv_content: str, filename: str, domain: str, user_id: str):
    """Execute evaluation and store completed results in DB."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    res = parse_and_evaluate_csv(csv_content, filename, domain)
    now = datetime.datetime.utcnow().isoformat()
    
    if not res["valid"]:
        cursor.execute("""
            UPDATE evaluations
            SET status = 'failed', progress = 100, error_message = ?, updated_at = ?
            WHERE id = ?
        """, (res["error"], now, evaluation_id))
        sync_and_get_user_reputation(user_id, conn)
        conn.commit()
        return
        
    quality, fidelity, completeness, relevance, overall, credits = res["scores"][:6]
    unlock_price = res.get("unlock_price", 10)
    basic_reward = res.get("basic_reward", BASIC_UPLOAD_REWARD)
    quality_reward = res.get("quality_reward", credits - basic_reward)
    
    cursor.execute("""
        UPDATE evaluations
        SET status = 'completed', progress = 100, quality_score = ?,
            schema_fidelity_score = ?, completeness_score = ?, domain_relevance_score = ?,
            overall_score = ?, credits_awarded = ?, updated_at = ?
        WHERE id = ?
    """, (quality, fidelity, completeness, relevance, overall, credits, now, evaluation_id))
    
    # Persist dataset-specific unlock price in datasets table
    cursor.execute("UPDATE datasets SET unlock_price = ? WHERE id = ?", (unlock_price, dataset_id))

    # Award credits atomically to user
    cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (credits, user_id))
    
    # Record basic upload reward in persistent credit transactions ledger
    tx_base = f"tx_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, ?, 'upload_reward', ?, 'completed', ?)
    """, (tx_base, user_id, basic_reward, f"Basic upload reward for dataset '{filename}' ({dataset_id})", now))
    
    # Record quality evaluation reward if earned
    if quality_reward > 0:
        tx_qual = f"tx_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
            VALUES (?, ?, ?, 'quality_reward', ?, 'completed', ?)
        """, (tx_qual, user_id, quality_reward, f"Quality reward ({overall:.1f}% overall score) for dataset '{filename}' ({dataset_id})", now))

    # Recalculate dynamic user reputation score from authoritative records
    sync_and_get_user_reputation(user_id, conn)
    
    conn.commit()

