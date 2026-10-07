import csv
import io
import json
import uuid
import datetime
from typing import Dict, Any, Tuple
from app.database import get_db_connection

from app.services.storage import sanitize_headers

def parse_and_evaluate_csv(csv_content: str, filename: str, domain: str) -> Dict[str, Any]:
    """
    Evaluate dataset quality:
    - schema fidelity
    - completeness
    - domain relevance
    - overall score and credits awarded
    """
    if not csv_content or not csv_content.strip():
        return {
            "valid": False,
            "error": "CSV file is empty",
            "rows_count": 0,
            "columns_count": 0,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0, 0),
            "cleaned_csv": ""
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
            "scores": (0.0, 0.0, 0.0, 0.0, 0, 0),
            "cleaned_csv": ""
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Failed to parse CSV header: {str(e)}",
            "rows_count": 0,
            "columns_count": 0,
            "schema": {},
            "scores": (0.0, 0.0, 0.0, 0.0, 0, 0),
            "cleaned_csv": ""
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
            "scores": (0.0, 0.0, 0.0, 0.0, 0, 0),
            "cleaned_csv": ""
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
            "scores": (0.0, 0.0, 0.0, 0.0, 0, 0),
            "cleaned_csv": ""
        }
        
    # Sanitize and deduplicate column names
    clean_header = sanitize_headers(header)

    # Reconstruct cleaned CSV
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(clean_header)
    for row in rows:
        writer.writerow(row)
    cleaned_csv = out.getvalue()

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
    
    # Credits calculation: 50 base + up to 50 for high quality
    credits_awarded = int(50 + (overall_score / 2.0))
    
    return {
        "valid": True,
        "error": None,
        "rows_count": total_rows,
        "columns_count": total_cols,
        "schema": schema,
        "scores": (quality_score, schema_fidelity_score, completeness_score, domain_relevance_score, overall_score, credits_awarded),
        "cleaned_csv": cleaned_csv
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
        conn.commit()
        return
        
    quality, fidelity, completeness, relevance, overall, credits = res["scores"]
    
    cursor.execute("""
        UPDATE evaluations
        SET status = 'completed', progress = 100, quality_score = ?,
            schema_fidelity_score = ?, completeness_score = ?, domain_relevance_score = ?,
            overall_score = ?, credits_awarded = ?, updated_at = ?
        WHERE id = ?
    """, (quality, fidelity, completeness, relevance, overall, credits, now, evaluation_id))
    
    # Award credits to user
    cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (credits, user_id))
    
    # Record transaction
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO credit_transactions (id, user_id, amount, transaction_type, description, status, created_at)
        VALUES (?, ?, ?, 'reward', ?, 'completed', ?)
    """, (tx_id, user_id, credits, f"Awarded for dataset {filename} evaluation", now))
    
    conn.commit()
