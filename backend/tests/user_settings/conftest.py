"""HTTP fixture for the app API: the real app on the rolled-back test session, with a
fresh mock bank, push and platform provider per test."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.providers import get_bank_provider, get_platform_provider, get_push_provider
from app.providers.mock_bank import MockBankAccountProvider
from app.providers.mock_platform import MockPlatformProvider
from app.providers.mock_push import MockPushProvider

USER = "user_a"


@dataclass
class Api:
    client: TestClient
    session: Session
    bank: MockBankAccountProvider
    push: MockPushProvider
    platform: MockPlatformProvider

    def call(
        self, method: str, path: str, body: Any = None, *, user: str | None = USER
    ) -> httpx.Response:
        """`body` is encoded as JSON (bytes are sent as they are, to write raw JSON
        such as a bare number). user=None sends no X-Demo-User header."""
        headers = {"Content-Type": "application/json"}
        if user is not None:
            headers["X-Demo-User"] = user
        if body is None:
            content = b""
        else:
            content = body if isinstance(body, bytes) else json.dumps(body).encode()
        return self.client.request(method, path, headers=headers, content=content)


@pytest.fixture
def api(db_session: Session) -> Iterator[Api]:
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
    try:
        with TestClient(app) as client:
            yield Api(client, db_session, bank, push, platform)
    finally:
        app.dependency_overrides.clear()
