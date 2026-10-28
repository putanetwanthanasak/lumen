"""Application settings, read from the environment only (never hard-coded)."""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real env vars win; the repo-root .env is a local-dev fallback.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # S2: the app connects as lumen_app; only Alembic uses the superuser URLs.
    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    test_migration_database_url: SecretStr | None = None
    # S12: /docs, /redoc and /openapi.json are served only when DEBUG is true.
    debug: bool = False
    webhook_secret_shopdemo: SecretStr | None = None
    provider_mode: Literal["mock"] = "mock"
    # POST /demo/payday exists only when this is true (DEMO_ENDPOINTS_ENABLED). Off by
    # default: a deployment never exposes it unless someone turns it on on purpose.
    demo_endpoints_enabled: bool = False
    # The payoff assistant's consolidation estimate (L70). EXAMPLE values, NOT A REAL
    # RATE: no bank has offered them. A real deployment takes the rate and term from
    # the bank's offer. The rate is yearly, e.g. "0.18" for 18% a year; env values are
    # strings, so the Decimal never passes through float.
    consolidation_example_annual_rate: Annotated[Decimal, Field(ge=0, lt=1, decimal_places=4)] = (
        Decimal("0.18")
    )
    consolidation_example_term_months: Annotated[int, Field(ge=1, le=600)] = 24
    # The mock bank's decision on every consolidation request (L71), for demos:
    # CONSOLIDATION_MOCK_DECISION=approve or decline.
    consolidation_mock_decision: Literal["approve", "decline"] = "approve"

    llm_provider: str | None = None
    llm_model_planner: str | None = None
    llm_model_categorizer: str | None = None
    llm_api_key: SecretStr | None = None

    app_basic_auth_user: str | None = None
    app_basic_auth_pass: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
