"""Application settings, read from the environment only (never hard-coded)."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real env vars win; the repo-root .env is a local-dev fallback.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None
    webhook_secret_shopdemo: SecretStr | None = None
    provider_mode: Literal["mock"] = "mock"

    llm_provider: str | None = None
    llm_model_planner: str | None = None
    llm_model_categorizer: str | None = None
    llm_api_key: SecretStr | None = None

    app_basic_auth_user: str | None = None
    app_basic_auth_pass: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
