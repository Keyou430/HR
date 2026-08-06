import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).with_name(".env"),
        env_file_encoding="utf-8",
    )

    # ── Hermes Gateway ──────────────────────────────────────────
    HERMES_MODE: Literal["mock", "real"] = "mock"
    HERMES_BASE_URL: str = "http://localhost:8001"
    HERMES_API_KEY: str | None = None
    HERMES_PROFILE: str | None = None
    HERMES_MODEL: str = "hermes-default"
    HERMES_API_STYLE: Literal["chat_completions", "responses"] = "chat_completions"
    HERMES_TIMEOUT_SECONDS: int = Field(default=60, gt=0)

    # ── FastGPT Gateway ─────────────────────────────────────────
    FASTGPT_MODE: Literal["mock", "real"] = "mock"
    FASTGPT_BASE_URL: str = "http://127.0.0.1:3100/api"
    FASTGPT_API_KEY: str | None = None
    FASTGPT_TIMEOUT_SECONDS: int = Field(default=60, gt=0)
    FASTGPT_SEARCH_APP_ID: str | None = None
    FASTGPT_CHAT_APP_ID: str | None = None
    FASTGPT_DEFAULT_PLATFORM_USER_ID: str | None = None
    FASTGPT_DEFAULT_TEAM_ID: str | None = "team-default"
    FASTGPT_DEFAULT_APP_ID: str | None = None
    FASTGPT_DEFAULT_DATASET_ID: str | None = None
    FASTGPT_DEFAULT_DISPLAY_NAME: str = "FastGPT 本地知识库"

    # ── Integration Embed URLs ───────────────────────────────────
    FEISHU_EMBED_URL: str | None = "https://www.feishu.cn/"
    DINGTALK_EMBED_URL: str | None = "https://www.dingtalk.com/"

    # ── AI Security (Phase 5) ────────────────────────────────────
    AI_SECURITY_MAX_QUERY_LENGTH: int = Field(default=2000, gt=0)
    AI_SECURITY_MAX_RETRIEVAL_CHUNKS: int = Field(default=20, gt=0)
    AI_SECURITY_RATE_LIMIT_PER_MINUTE: int = Field(default=10, gt=0)
    AI_SECURITY_ENABLE_INJECTION_DETECTION: bool = True
    AI_SECURITY_LOG_SNIPPET_LENGTH: int = Field(default=256, gt=0)

    # ── Auth & Security ─────────────────────────────────────────
    JWT_SECRET_KEY: str = ""  # MUST be set via env var; no hardcoded default
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)
    REFRESH_TOKEN_BYTES: int = Field(default=32, gt=0)
    LOGIN_MAX_ATTEMPTS: int = Field(default=5, gt=0)
    LOGIN_WINDOW_SECONDS: int = Field(default=300, gt=0)
    BCRYPT_ROUNDS: int = Field(default=12, gt=0)

    # ── Audit (Phase 6) ──────────────────────────────────────────
    AUDIT_ENABLED: bool = True
    AUDIT_RECORD_AUTH_DENIED: bool = True
    AUDIT_RETENTION_DAYS: int = Field(default=90, gt=0)

    # ── Deployment / Environment ──────────────────────────────────
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── PostgreSQL ─────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "replica"
    POSTGRES_USER: str = "replica"
    POSTGRES_PASSWORD: str = "replica"
    POOL_SIZE: int = 10
    MAX_OVERFLOW: int = 20

    # ── Admin Bootstrap ────────────────────────────────────────────
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_EMAIL: str = ""

    # ── Backup ─────────────────────────────────────────────────────
    BACKUP_RETENTION_DAYS: int = 14

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a list, excluding 'null'."""
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        # Prevent null origin (security risk per rbac-design-v2.md)
        if "null" in origins:
            import logging
            logging.getLogger("replica").warning("CORS_ORIGINS contains 'null' — removed for security.")
            origins.remove("null")
        return origins

    @property
    def jwt_secret_is_default(self) -> bool:
        return not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY == "change-me-in-production-use-openssl-rand-hex-32"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # ── Database ────────────────────────────────────────────────
    # Default to SQLite for safe local development.
    # For production, set DATABASE_URL to a PostgreSQL connection string.
    DATABASE_URL: str = "sqlite:///./replica_platform.db"


def _pytest_database_url(default_url: str) -> str:
    """Redirect to a per-test temp SQLite database when running under pytest.

    If DATABASE_URL was explicitly set in the environment (e.g. by a test fixture
    via monkeypatch), respect that value and skip the auto-redirect.  Otherwise
    generate a safe per-test SQLite path so tests never touch the dev database.

    To test against PostgreSQL, set REPLICA_TEST_DATABASE_URL in the environment.
    """
    current_test = os.getenv("PYTEST_CURRENT_TEST")
    if not current_test:
        return default_url

    # If a fixture explicitly set DATABASE_URL, respect it
    if os.getenv("DATABASE_URL"):
        return default_url

    # Allow explicit PG override for integration tests
    explicit_test_url = os.getenv("REPLICA_TEST_DATABASE_URL")
    if explicit_test_url:
        return explicit_test_url

    safe_test_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", current_test).strip("_")
    temp_dir = tempfile.gettempdir()
    return f"sqlite:///{temp_dir}/replica_platform_{safe_test_name}.db"


@lru_cache
def _get_settings(cache_key: str) -> Settings:
    settings = Settings()
    settings.DATABASE_URL = _pytest_database_url(settings.DATABASE_URL)
    return settings


def get_settings() -> Settings:
    cache_key = os.getenv("PYTEST_CURRENT_TEST") or "__default__"
    return _get_settings(cache_key)


get_settings.cache_clear = _get_settings.cache_clear  # type: ignore[attr-defined]
