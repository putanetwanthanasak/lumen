"""An app built with DEMO_ENDPOINTS_ENABLED on, so POST /demo/payday exists, on the
rolled-back test session with fresh mock providers. The shared `api` fixture uses
the module app, built from the environment, where the flag is off."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.providers import get_bank_provider, get_platform_provider, get_push_provider
from app.providers.mock_bank import MockBankAccountProvider
from app.providers.mock_platform import MockPlatformProvider
from app.providers.mock_push import MockPushProvider
from tests.user_settings.conftest import Api, api

__all__ = ["api", "demo"]


@pytest.fixture
def demo(db_session: Session) -> Iterator[Api]:
    app = create_app(Settings(demo_endpoints_enabled=True))

    def session_override() -> Iterator[Session]:
        yield db_session

    bank, push, platform = MockBankAccountProvider(), MockPushProvider(), MockPlatformProvider()
    app.dependency_overrides.update(
        {
            get_session: session_override,
            get_bank_provider: lambda: bank,
            get_push_provider: lambda: push,
            get_platform_provider: lambda: platform,
        }
    )
    with TestClient(app) as client:
        yield Api(client, db_session, bank, push, platform)
