import re
import math
from typing import Optional
from app.config import settings
from app.services.embeddings import get_embedding

def cosine_similarity(vec_a, vec_b) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))

def rule_based_relevance_score(query: str, doc_text: str, domain: Optional[str] = None) -> float:
    """Rule-based fallback scoring when embeddings are disabled and no LLM is configured."""
    q_words = set(re.findall(r"\w+", query.lower()))
    d_words = set(re.findall(r"\w+", doc_text.lower()))
    
    if not q_words or not d_words:
        return 0.1
    
    # Keyword overlap
    overlap = len(q_words.intersection(d_words))
    jaccard = overlap / len(q_words.union(d_words)) if q_words.union(d_words) else 0.0
    recall = overlap / len(q_words) if q_words else 0.0
    
    score = (0.6 * recall) + (0.4 * jaccard)
    
    # Domain match bonus
    if domain and domain.lower() in query.lower():
        score += 0.25
        
    return min(1.0, max(0.05, score))

def compute_relevance(query: str, doc_text: str, domain: Optional[str] = None) -> float:
    """
    Compute relevance score.
    When EMBEDDINGS_ENABLED is true: uses dense vector cosine similarity.
    When false: skips sentence-transformers entirely, uses LLM/rule-based fallback.
    """
    if settings.EMBEDDINGS_ENABLED:
        q_emb = get_embedding(query)
        d_emb = get_embedding(doc_text)
        if q_emb and d_emb:
            return cosine_similarity(q_emb, d_emb)
    
    # Fallback when embeddings disabled or not loaded
    return rule_based_relevance_score(query, doc_text, domain)
