"""HTTP fixture for the app API: the real app on the rolled-back test session."""

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

USER = "user_a"


@dataclass
class Api:
    client: TestClient
    session: Session

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

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            yield Api(client, db_session)
    finally:
        app.dependency_overrides.clear()
