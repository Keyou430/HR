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

    # ── Auth & Security ─────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)
    REFRESH_TOKEN_BYTES: int = Field(default=32, gt=0)
    LOGIN_MAX_ATTEMPTS: int = Field(default=5, gt=0)
    LOGIN_WINDOW_SECONDS: int = Field(default=300, gt=0)
    BCRYPT_ROUNDS: int = Field(default=12, gt=0)

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.JWT_SECRET_KEY == "change-me-in-production-use-openssl-rand-hex-32"

    # ── Database ────────────────────────────────────────────────
    # SQLite for dev; switch to postgresql+psycopg://... for prod (pgvector)
    # Path is resolved relative to this config file so the DB lives in backend/
    # regardless of the working directory the app is started from.
    DATABASE_URL: str = f"sqlite:///{(Path(__file__).parent / 'replica_platform.db').as_posix()}"


def _pytest_database_url(default_url: str) -> str:
    """Redirect to a per-test temp database when running under pytest,
    unless DATABASE_URL was explicitly set in the environment.
    """
    current_test = os.getenv("PYTEST_CURRENT_TEST")
    if not current_test:
        return default_url
    # If DATABASE_URL was explicitly set by the test fixture (not the class
    # default), respect the override.
    if os.getenv("DATABASE_URL"):
        return default_url

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
