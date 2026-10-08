import os
import re
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    VERSION: str = "1.0.0"

    # CORS Settings
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://datapulse.ai.studio"
    CORS_ORIGIN_REGEX: str = r"https://.*\.(lovable\.app|lovableproject\.com|lovable\.dev)$"

    # AI & Embeddings Flag
    EMBEDDINGS_ENABLED: bool = True

    # AI & LLM Provider Settings
    AI_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Marketplace / Credits Settings
    QUERY_COST: int = 1
    DATASET_OWNER_REWARD: int = 1

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
