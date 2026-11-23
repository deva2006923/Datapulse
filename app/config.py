import os
import re
from typing import List, Optional, Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_DEV_CORS_ORIGINS: Tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class Settings(BaseSettings):
    # Server Settings
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    VERSION: str = "1.0.0"

    # Upload Limits
    MAX_UPLOAD_SIZE_MB: int = 25

    # CORS Settings (explicit origins only — never wildcard '*' with allow_credentials=True)
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "https://datapulse.ai.studio"
    )
    CORS_ORIGIN_REGEX: str = r"https://.*\.(lovable\.app|lovableproject\.com|lovable\.dev)$"

    # AI & Embeddings Flag
    EMBEDDINGS_ENABLED: bool = True

    # Primary AI Provider Settings (Groq primary; Gemini optional fallback)
    AI_PROVIDER: str = "groq"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BACKUP_MODELS: str = "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b"

    # Optional Fallback & Retry AI Provider Settings
    AI_TIMEOUT_SECONDS: float = 20.0
    AI_MAX_RETRIES: int = 2
    AI_RETRY_BASE_DELAY_SECONDS: float = 0.5
    AI_RETRY_MAX_WAIT_SECONDS: float = 4.0
    AI_FALLBACK_PROVIDER: Optional[str] = "gemini"
    AI_FALLBACK_API_KEY: Optional[str] = None
    AI_FALLBACK_MODEL: Optional[str] = None
    AI_FALLBACK_BASE_URL: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Marketplace / Credits Settings
    QUERY_COST: int = 1
    DATASET_OWNER_REWARD: int = 1

    # Administrator Authorization & Default Provisioning
    ADMIN_EMAIL: str = "datapulseapplication@gmail.com"
    ADMIN_PASSWORD: Optional[str] = None

    # Security, Sessions, Query Limits & Rate Limiting
    TOKEN_TTL_HOURS: int = 24
    QUERY_TIMEOUT_SECONDS: int = 10
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MIN: int = 20
    RATE_LIMIT_QUERY_PER_MIN: int = 30
    RATE_LIMIT_UPLOAD_PER_MIN: int = 15
    RATE_LIMIT_DEFAULT_PER_MIN: int = 180

    SECRET_KEY: str = "datapulse-production-secret-key-replace-in-env"
    # Optional PostgreSQL connection string for production (e.g. postgresql://user:pass@host:5432/db?sslmode=require).
    # When unset, DataPulse uses local SQLite at DATABASE_PATH seamlessly.
    DATABASE_URL: Optional[str] = None
    DATABASE_PATH: str = "datapulse.db"
    DUCKDB_PATH: str = "datapulse_analytics.duckdb"
    DATASETS_STORAGE_DIR: str = "storage/datasets"

    # Curated Public Dataset Library & Optional Cloudflare R2 Object Storage
    CURATED_MANIFEST_PATH: str = "data/curated_manifest.json"
    CURATED_DATA_DIR: str = "data/curated"
    CURATED_SYNC_ON_STARTUP: bool = True
    R2_PERSIST_COMMUNITY_UPLOADS: bool = True
    R2_REQUIRED_IN_PRODUCTION: bool = True
    R2_ENDPOINT_URL: Optional[str] = None
    R2_BUCKET_NAME: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_REGION: str = "auto"
    R2_TIMEOUT_SECONDS: int = 30
    R2_MAX_RETRIES: int = 3
    CURATED_CACHE_MAX_MB: int = 200
    CURATED_CACHE_MAX_TABLES: int = 25
    CURATED_TARGET_MAX_MB: int = 10
    CURATED_TARGET_MAX_ROWS: int = 100000
    CURATED_HARD_MAX_MB: int = 25
    CURATED_HARD_MAX_ROWS: int = 250000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return (self.ENVIRONMENT or "").strip().lower() == "production"

    @property
    def is_postgres_configured(self) -> bool:
        url = (self.DATABASE_URL or "").strip().lower()
        return url.startswith("postgres://") or url.startswith("postgresql://")

    @property
    def groq_backup_models_list(self) -> List[str]:
        if not self.GROQ_BACKUP_MODELS:
            return []
        return [m.strip() for m in self.GROQ_BACKUP_MODELS.split(",") if m.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return max(1, int(self.MAX_UPLOAD_SIZE_MB)) * 1024 * 1024

    @property
    def cors_origins_list(self) -> List[str]:
        origins: List[str] = []
        seen = set()

        def _add(raw_origin: str) -> None:
            cleaned = (raw_origin or "").strip().rstrip("/")
            # Never allow wildcard '*' when allow_credentials=True
            if not cleaned or cleaned == "*":
                return
            if cleaned not in seen:
                seen.add(cleaned)
                origins.append(cleaned)

        if self.CORS_ORIGINS:
            for origin in self.CORS_ORIGINS.split(","):
                _add(origin)

        # In local development only, always include standard localhost/127.0.0.1 dev ports
        if not self.is_production:
            for dev_origin in LOCAL_DEV_CORS_ORIGINS:
                _add(dev_origin)

        return origins

    def is_origin_allowed(self, origin: str) -> bool:
        cleaned = (origin or "").strip().rstrip("/")
        if not cleaned:
            return False
        if cleaned in self.cors_origins_list:
            return True
        if self.CORS_ORIGIN_REGEX:
            try:
                if re.match(self.CORS_ORIGIN_REGEX, cleaned):
                    return True
            except re.error:
                pass
        return False


settings = Settings()
