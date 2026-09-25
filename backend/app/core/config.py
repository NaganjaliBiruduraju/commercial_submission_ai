"""
Application configuration.

All settings are loaded from environment variables using Pydantic Settings.
This ensures:
  1. No secrets are ever hard-coded in source code
  2. Configuration is validated at startup — the app fails fast with a clear
     error if a required variable is missing or has an invalid type
  3. Settings are typed and IDE-discoverable throughout the codebase

Usage:
    from app.core.config import settings
    print(settings.app_name)
    print(settings.database_url)

The actual .env file is git-ignored. .env.example documents all required vars.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object.

    Pydantic validates every field on first access.
    If a required env var is missing the application raises ConfigurationError
    at startup, not during a request.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore extra env vars — don't error on unknown keys
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_name: str = Field(default="INSIGHT AI", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # CORS — comma-separated list of allowed origins
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # -------------------------------------------------------------------------
    # Database
    # Credentials loaded from environment — never hard-coded.
    # -------------------------------------------------------------------------
    database_url: str = Field(alias="DATABASE_URL")

    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure the database URL uses the asyncpg driver for async SQLAlchemy."""
        if not v:
            raise ValueError("DATABASE_URL is required")
        if "postgresql" in v and "asyncpg" not in v and "+asyncpg" not in v:
            # Auto-upgrade postgresql:// to postgresql+asyncpg://
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # -------------------------------------------------------------------------
    # Authentication
    # SECRET_KEY signs all JWT tokens — treat like a password.
    # Generate with: openssl rand -hex 32
    # -------------------------------------------------------------------------
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(
        default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS"
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or v == "GENERATE_WITH_openssl_rand_-hex_32":
            raise ValueError(
                "SECRET_KEY must be set to a real secret. "
                "Generate one with: openssl rand -hex 32"
            )
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    # -------------------------------------------------------------------------
    # LLM — Groq API
    # GROQ_API_KEY is NEVER logged, printed, or returned in responses.
    # The frontend NEVER receives this key.
    # -------------------------------------------------------------------------
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")

    llm_model: str = Field(default="openai/gpt-oss-20b", alias="LLM_MODEL")
    llm_temperature_extraction: float = Field(
        default=0.1, alias="LLM_TEMPERATURE_EXTRACTION"
    )
    llm_temperature_summarization: float = Field(
        default=0.3, alias="LLM_TEMPERATURE_SUMMARIZATION"
    )
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")

    # -------------------------------------------------------------------------
    # Embedding Model (sentence-transformers)
    # -------------------------------------------------------------------------
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(default=384, alias="EMBEDDING_DIMENSION")
    llm_timeout_seconds: int = Field(default=60, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")

    @field_validator("llm_temperature_extraction", "llm_temperature_summarization")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("LLM temperature must be between 0.0 and 2.0")
        return v

    # -------------------------------------------------------------------------
    # Embeddings
    # sentence-transformers runs locally — no API key required.
    # -------------------------------------------------------------------------
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(default=384, alias="EMBEDDING_DIMENSION")

    # -------------------------------------------------------------------------
    # File Upload
    # -------------------------------------------------------------------------
    upload_dir: str = Field(default="./data/uploads", alias="UPLOAD_DIR")
    knowledge_upload_dir: str = Field(default="./data/knowledge", alias="KNOWLEDGE_UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=50, alias="MAX_UPLOAD_SIZE_MB")
    max_files_per_submission: int = Field(
        default=20, alias="MAX_FILES_PER_SUBMISSION"
    )
    allowed_extensions: str = Field(
        default="pdf,docx,xlsx,csv,jpg,jpeg,png",
        alias="ALLOWED_EXTENSIONS",
    )

    @property
    def allowed_extensions_set(self) -> set[str]:
        """Return allowed extensions as a lowercase set."""
        return {ext.strip().lower() for ext in self.allowed_extensions.split(",")}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    # -------------------------------------------------------------------------
    # Risk Scoring Thresholds
    # These are DEMO values — real thresholds require approved underwriting rules.
    # All marked [DEMO RULE — NOT APPROVED POLICY]
    # -------------------------------------------------------------------------
    risk_low_max: int = Field(default=39, alias="RISK_LOW_MAX")       # [DEMO RULE]
    risk_medium_max: int = Field(default=69, alias="RISK_MEDIUM_MAX")  # [DEMO RULE]
    risk_high_min: int = Field(default=70, alias="RISK_HIGH_MIN")      # [DEMO RULE]
    risk_base_score: int = Field(default=50, alias="RISK_BASE_SCORE")  # [DEMO RULE]

    @model_validator(mode="after")
    def validate_risk_thresholds(self) -> "Settings":
        if not (self.risk_low_max < self.risk_medium_max < self.risk_high_min):
            raise ValueError(
                "Risk thresholds must satisfy: RISK_LOW_MAX < RISK_MEDIUM_MAX < RISK_HIGH_MIN"
            )
        return self

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")
    log_file: str | None = Field(default=None, alias="LOG_FILE")

    # -------------------------------------------------------------------------
    # Computed helpers
    # -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def llm_configured(self) -> bool:
        """True only if a real Groq API key has been provided."""
        return bool(
            self.groq_api_key
            and self.groq_api_key != "your_groq_api_key_here"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    lru_cache ensures the .env file is only read once per process.
    In tests, call get_settings.cache_clear() between tests that need
    different settings values.
    """
    return Settings()


# Module-level convenience alias
# Import this throughout the application: from app.core.config import settings
settings = get_settings()
