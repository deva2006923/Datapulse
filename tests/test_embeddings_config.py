import sys
from app.config import settings
from app.services.relevance import compute_relevance
from app.services.recommender import recommend_datasets
from app.services.embeddings import is_embeddings_available

def test_embeddings_disabled_behavior():
    orig_val = settings.EMBEDDINGS_ENABLED
    try:
        settings.EMBEDDINGS_ENABLED = False
        assert is_embeddings_available() is False
        
        # Test relevance fallback
        score = compute_relevance("finance records revenue", "Quarterly revenue and finance dataset", domain="finance")
        assert score > 0.0
        assert score <= 1.0
        
        # Test recommender uses TF-IDF only
        datasets = [
            {"id": "1", "name": "Financial Transactions", "domain": "finance", "content_summary": "bank transaction records", "schema_json": ""},
            {"id": "2", "name": "Patient Health Logs", "domain": "healthcare", "content_summary": "clinical visits and medical records", "schema_json": ""},
        ]
        results, method = recommend_datasets("financial bank transactions", datasets)
        assert method == "tfidf_only"
        assert len(results) == 2
        assert results[0]["id"] == "1"
        assert results[0]["score"] > results[1]["score"]
        
    finally:
        settings.EMBEDDINGS_ENABLED = orig_val
