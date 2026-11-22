import os
import re
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Server Settings
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    VERSION: str = "1.0.0"

    # Upload Limits
    MAX_UPLOAD_SIZE_MB: int = 25

    # CORS Settings
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://datapulse.ai.studio"
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
    DATABASE_PATH: str = "datapulse.db"
    DUCKDB_PATH: str = "datapulse_analytics.duckdb"
    DATASETS_STORAGE_DIR: str = "storage/datasets"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return (self.ENVIRONMENT or "").strip().lower() == "production"

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
        if not self.CORS_ORIGINS:
            return []
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def is_origin_allowed(self, origin: str) -> bool:
        if not origin:
            return False
        if origin in self.cors_origins_list or "*" in self.cors_origins_list:
            return True
        if self.CORS_ORIGIN_REGEX:
            try:
                if re.match(self.CORS_ORIGIN_REGEX, origin):
                    return True
            except re.error:
                pass
        return False


settings = Settings()
