from fastapi import APIRouter
from app.routers import TrailingSlashRouter
from app.config import settings
from app.schemas import HealthResponse

router = TrailingSlashRouter(tags=["Health"])

@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Health check endpoint returning service status, CORS regex configuration, 
    embeddings engine state, and API version.
    """
    return HealthResponse(
        status="ok",
        cors_regex=bool(settings.CORS_ORIGIN_REGEX),
        embeddings=bool(settings.EMBEDDINGS_ENABLED),
        version=settings.VERSION
    )
