import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import init_db
from app.services.admin_bootstrap import ensure_default_admin
from app.services.storage import init_storage
from app.routers import health, auth, datasets, query, credits, user, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("datapulse")

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def reset_rate_limiter() -> None:
    """Clear sliding-window rate-limit state (primarily for tests)."""
    with _rate_limit_lock:
        _rate_limit_buckets.clear()


def _resolve_rate_limit(path: str, method: str) -> tuple[str, int]:
    norm = (path or "/").rstrip("/") or "/"
    if norm in ("/auth/login", "/auth/register"):
        return "auth", max(1, int(settings.RATE_LIMIT_AUTH_PER_MIN))
    if norm == "/query" and method.upper() == "POST":
        return "query", max(1, int(settings.RATE_LIMIT_QUERY_PER_MIN))
    if norm == "/datasets/upload" and method.upper() == "POST":
        return "upload", max(1, int(settings.RATE_LIMIT_UPLOAD_PER_MIN))
    return "default", max(1, int(settings.RATE_LIMIT_DEFAULT_PER_MIN))


def _get_client_ip(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    return request.client.host if request.client else "unknown"

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
    logger.info("Verifying default administrator account...")
    ensure_default_admin()

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


@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    path = request.url.path or "/"
    method = request.method.upper()

    # Apply sliding-window per-IP rate limiting (skip health probes and CORS preflight)
    if settings.RATE_LIMIT_ENABLED and method != "OPTIONS" and not path.rstrip("/").endswith("/health"):
        bucket_name, max_requests = _resolve_rate_limit(path, method)
        client_ip = _get_client_ip(request)
        now = time.monotonic()
        window_seconds = 60.0

        with _rate_limit_lock:
            q = _rate_limit_buckets[(client_ip, bucket_name)]
            while q and (now - q[0]) >= window_seconds:
                q.popleft()
            if len(q) >= max_requests:
                retry_after = max(1, int(window_seconds - (now - q[0])))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down and try again shortly."},
                    headers={"Retry-After": str(retry_after)},
                )
            q.append(now)

    response = await call_next(request)

    # Harden HTTP security headers on all responses
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if path.startswith("/auth") or path.startswith("/admin"):
        response.headers.setdefault("Cache-Control", "no-store")

    return response

# Include Routers (all using TrailingSlashRouter for seamless slash/no-slash matching)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(query.router)
app.include_router(credits.router)
app.include_router(user.router)
app.include_router(admin.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=not settings.is_production)
