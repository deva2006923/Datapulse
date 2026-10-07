import uuid
import json
import datetime
from fastapi import HTTPException, status, Depends
from app.routers import TrailingSlashRouter
from app.database import get_db_connection
from app.auth import get_optional_user
from app.schemas import QueryRequest, QueryResponse
from app.services.relevance import compute_relevance
from app.config import settings

router = TrailingSlashRouter(tags=["Query & Analysis"])

@router.post("/query", response_model=QueryResponse)
def execute_query(req: QueryRequest, user: dict = Depends(get_optional_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if req.dataset_id:
        cursor.execute("SELECT * FROM datasets WHERE id = ?", (req.dataset_id,))
    else:
        cursor.execute("SELECT * FROM datasets ORDER BY created_at DESC LIMIT 10")
        
    datasets = cursor.fetchall()
    if not datasets:
        return QueryResponse(
            query=req.query,
            answer="No relevant datasets found in the catalog to answer your query. Upload structured datasets to start querying.",
            matching_datasets=[],
            records_analyzed=0,
            relevance_score=0.0,
            method="rule_fallback" if not settings.EMBEDDINGS_ENABLED else "embeddings"
        )
        
    best_dataset = None
    best_score = -1.0
    matching_names = []
    total_records = 0
    
    for d in datasets:
        matching_names.append(d["name"])
        total_records += d["rows_count"]
        doc_text = f"{d['name']} {d['domain']} {d['content_summary']} {d['schema_json']}"
        score = compute_relevance(req.query, doc_text, domain=d["domain"])
        if score > best_score:
            best_score = score
            best_dataset = d
            
    relevance_score = round(max(0.0, min(1.0, best_score)), 4)
    method_used = "embeddings" if settings.EMBEDDINGS_ENABLED else "rule_fallback"
    
    answer = (
        f"Analyzed query '{req.query}' across {len(datasets)} dataset(s) ({total_records} rows). "
        f"Top match: '{best_dataset['name']}' in domain '{best_dataset['domain']}' with schema {best_dataset['schema_json']} "
        f"and confidence {round(relevance_score * 100, 1)}%."
    )
    
    # Store query record
    query_id = f"qry_{uuid.uuid4().hex[:12]}"
    user_id = user["id"] if user else "anonymous"
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO queries (id, user_id, query_text, results_json, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (query_id, user_id, req.query, json.dumps({"answer": answer, "score": relevance_score}), now))
    conn.commit()
    
    return QueryResponse(
        query=req.query,
        answer=answer,
        matching_datasets=matching_names[:3],
        records_analyzed=total_records,
        relevance_score=relevance_score,
        method=method_used
    )
