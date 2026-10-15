"""HTTP fixtures for the webhook receiver.

The client runs the real app with three dependencies overridden: the DB session
(the rolled-back test session), the vendor secrets (random per test run, never
printed), and the clock (fixed, so window edges are exact).
"""

import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.models import AuditLog, WebhookEvent
from app.webhooks.signature import get_now, get_vendor_secrets, sign
from tests.webhooks.payloads import encode

NOW = 1_791_000_000  # fixed Unix time for every request
VENDOR = "shopdemo"
OTHER_VENDOR = "othervendor"
SECRETS = {VENDOR: secrets.token_hex(32), OTHER_VENDOR: secrets.token_hex(32)}
WRONG_SECRET = secrets.token_hex(32)  # signs with a key no vendor has


@dataclass
class Webhook:
    client: TestClient
    session: Session

    def post(
        self,
        data: dict[str, Any] | bytes,
        *,
        vendor: str = VENDOR,
        timestamp: int | str = NOW,
        secret: str | None = None,
        signature: str | None = None,
        drop: str | None = None,
    ) -> httpx.Response:
        """POST a correctly signed body; each keyword breaks one part of it."""
        body = data if isinstance(data, bytes) else encode(data)
        ts = str(timestamp)
        key = secret if secret is not None else SECRETS.get(vendor, "")
        headers = {
            "X-Vendor-Id": vendor,
            "X-Timestamp": ts,
            "X-Signature": signature if signature is not None else sign(key, ts, body),
            "Content-Type": "application/json",
        }
        if drop is not None:
            del headers[drop]
        return self.client.post("/webhooks/bnpl", content=body, headers=headers)

    def count(self, model: type[WebhookEvent] | type[AuditLog]) -> int:
        return self.session.execute(select(func.count()).select_from(model)).scalar_one()

    def nothing_written(self) -> bool:
        return self.count(WebhookEvent) == 0 and self.count(AuditLog) == 0


@pytest.fixture
def webhook(db_session: Session) -> Iterator[Webhook]:
    def session_override() -> Iterator[Session]:
        yield db_session

    overrides: dict[Callable[..., Any], Callable[..., Any]] = {
        get_session: session_override,
        get_vendor_secrets: lambda: {v: SecretStr(s) for v, s in SECRETS.items()},
        get_now: lambda: NOW,
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield Webhook(client, db_session)
    finally:
        app.dependency_overrides.clear()
