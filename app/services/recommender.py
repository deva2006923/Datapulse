from typing import List, Dict, Any, Tuple
from app.config import settings
from app.services.relevance import compute_relevance

def rank_with_tfidf(query: str, corpus: List[str]) -> List[float]:
    """Calculate TF-IDF similarity vector using scikit-learn."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        all_docs = [query] + corpus
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(all_docs)
        
        query_vec = tfidf_matrix[0:1]
        doc_vecs = tfidf_matrix[1:]
        
        sims = cosine_similarity(query_vec, doc_vecs).flatten()
        return sims.tolist()
    except Exception:
        # Fallback manual TF-IDF approximation if scikit-learn issues arise
        scores = []
        q_tokens = set(query.lower().split())
        for doc in corpus:
            d_tokens = doc.lower().split()
            overlap = sum(1 for t in q_tokens if t in d_tokens)
            scores.append(overlap / (len(q_tokens) + 1e-5))
        return scores

def recommend_datasets(query: str, datasets: List[Dict[str, Any]], limit: int = 10) -> Tuple[List[Dict[str, Any]], str]:
    """
    Recommend/rank datasets matching query.
    When EMBEDDINGS_ENABLED is false: uses TF-IDF only.
    When true: uses hybrid embeddings and domain scoring.
    """
    if not datasets:
        return [], "none"
        
    corpus = [
        f"{d.get('name', '')} {d.get('domain', '')} {d.get('content_summary', '')} {d.get('schema_json', '')}"
        for d in datasets
    ]
    
    if not settings.EMBEDDINGS_ENABLED:
        # Strict TF-IDF ONLY
        scores = rank_with_tfidf(query, corpus)
        ranked = []
        for d, score in zip(datasets, scores):
            item = dict(d)
            item["score"] = round(float(score), 4)
            ranked.append(item)
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked[:limit], "tfidf_only"
    
    # Embeddings / Hybrid method
    ranked = []
    for d, text in zip(datasets, corpus):
        score = compute_relevance(query, text, domain=d.get("domain"))
        item = dict(d)
        item["score"] = round(float(score), 4)
        ranked.append(item)
        
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit], "embeddings"
