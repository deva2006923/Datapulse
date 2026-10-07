import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.database import init_db
from app.services.storage import init_storage
from app.routers import health, auth, datasets, query, credits, user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("datapulse")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SQLite tables
    logger.info("Initializing DataPulse SQLite Database...")
    init_db()
    logger.info("Initializing DataPulse Analytical Storage...")
    init_storage()
    logger.info("DataPulse Backend initialized. Version: %s", settings.VERSION)
    yield
    # Shutdown
    logger.info("DataPulse Backend shutting down.")

# Requirement 2: Set redirect_slashes=False
app = FastAPI(
    title="DataPulse Backend API",
    description="DataPulse Backend API powering crowdsourced dataset uploads, automated quality evaluation, vector search, and credits redemption.",
    version=settings.VERSION,
    redirect_slashes=False,
    lifespan=lifespan
)

# Requirement 1: CORS configuration
# Allow origins matching either the list or the regex.
# Allow credentials, all methods, all headers (including ngrok-skip-browser-warning and Authorization), and expose Content-Disposition.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX if settings.CORS_ORIGIN_REGEX else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Include Routers (all using TrailingSlashRouter for seamless slash/no-slash matching)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(query.router)
app.include_router(credits.router)
app.include_router(user.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
