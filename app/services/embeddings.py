import logging
from typing import Optional, List
from app.config import settings

logger = logging.getLogger(__name__)

_model = None
_model_failed = False

def is_embeddings_available() -> bool:
    """Return whether embeddings feature is active and enabled."""
    return settings.EMBEDDINGS_ENABLED and not _model_failed

def get_embedding_model():
    """Lazy-load the sentence-transformers model so startup stays fast."""
    global _model, _model_failed
    if not settings.EMBEDDINGS_ENABLED:
        return None
    if _model_failed:
        return None
    if _model is None:
        try:
            logger.info("Lazy-loading sentence-transformers embedding model...")
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("SentenceTransformer model loaded successfully.")
        except Exception as e:
            logger.warning("Could not load sentence-transformers (%s). Falling back.", e)
            _model_failed = True
            return None
    return _model

def get_embedding(text: str) -> Optional[List[float]]:
    """Generate dense vector embedding for text or None if disabled/unavailable."""
    if not settings.EMBEDDINGS_ENABLED:
        return None
    model = get_embedding_model()
    if model is None:
        return None
    try:
        vec = model.encode(text, convert_to_numpy=True)
        return vec.tolist()
    except Exception as e:
        logger.error("Embedding generation error: %s", e)
        return None
