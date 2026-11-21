from fastapi import HTTPException, status
from app.routers import TrailingSlashRouter
from app.config import settings
from app.database import get_db_connection
from app.services.storage import get_duckdb_connection
from app.schemas import HealthResponse

router = TrailingSlashRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Production health check verifying API liveness, SQLite connectivity,
    and DuckDB analytical storage readiness without exposing internal paths or secrets.
    """
    db_ok = False
    storage_ok = False

    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False

    try:
        duck_cur = get_duckdb_connection()
        duck_cur.execute("SELECT 1").fetchone()
        storage_ok = True
    except Exception:
        storage_ok = False

    if not db_ok or not storage_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service degraded: persistent database or analytical storage unavailable.",
        )

    return HealthResponse(
        status="ok",
        cors_regex=bool(settings.CORS_ORIGIN_REGEX),
        embeddings=bool(settings.EMBEDDINGS_ENABLED),
        version=settings.VERSION,
        database_ok=db_ok,
        storage_ok=storage_ok,
        environment=settings.ENVIRONMENT,
    )
