import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import init_db
from app.services.storage import init_storage
from app.routers import health, auth, datasets, query, credits, user, admin, admin_bootstrap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("datapulse")

_INSECURE_SECRET_DEFAULTS = {
    "dev-secret-key-change-in-production",
    "datapulse-production-secret-key-replace-in-env",
    "changeme",
    "secret",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize persistent SQLite & DuckDB storage without overwriting existing data
    logger.info("Initializing DataPulse SQLite Database...")
    init_db()
    logger.info("Initializing DataPulse Analytical Storage...")
    init_storage()

    if settings.is_production:
        if not settings.SECRET_KEY or settings.SECRET_KEY.strip() in _INSECURE_SECRET_DEFAULTS or len(settings.SECRET_KEY.strip()) < 32:
            logger.warning(
                "SECURITY WARNING: SECRET_KEY is using a weak or default value in production. "
                "Generate a >=32-byte random secret in your hosting environment."
            )
        if not settings.GEMINI_API_KEY:
            logger.warning(
                "CONFIGURATION WARNING: GEMINI_API_KEY is not set; natural-language SQL generation will use limited rule fallback."
            )

    logger.info(
        "DataPulse Backend initialized. Version: %s, Environment: %s",
        settings.VERSION,
        settings.ENVIRONMENT,
    )
    yield
    logger.info("DataPulse Backend shutting down.")


# Keep redirect_slashes=False so Authorization headers are never stripped by 307 redirects
app = FastAPI(
    title="DataPulse Backend API",
    description="DataPulse Backend API powering crowdsourced dataset uploads, automated quality evaluation, vector search, and credits redemption.",
    version=settings.VERSION,
    redirect_slashes=False,
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Prevents leaking internal stack traces or secret details in HTTP 500 responses."""
    logger.exception("Unhandled server error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# CORS configuration: allow explicit configured origins (and optional regex when configured)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX if settings.CORS_ORIGIN_REGEX else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Include Routers (all using TrailingSlashRouter for seamless slash/no-slash matching)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(query.router)
app.include_router(credits.router)
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(admin_bootstrap.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=not settings.is_production)
