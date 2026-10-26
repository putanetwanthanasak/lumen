"""Real concurrency: threads, separate DB connections, committed transactions.

These tests cannot use the rolled-back db_session: concurrent requests must race
through their own connections and really commit, or Postgres never arbitrates
between them. So each test uses a unique user, opts it in with a committed row,
and deletes everything for that user afterwards, even on failure.

The clean-up runs as the schema owner: the app role has no DELETE anywhere (S2).
audit_log is append-only (a trigger rejects DELETE). The clean-up disables that
trigger, deletes this test user's rows and re-enables it inside one transaction:
Postgres DDL is transactional, so no other session ever sees it off. It only runs
against the *_test database the shared test_db_url fixture insists on. Without it,
committed audit rows would break the tests that count every audit row.

Run them alone for the demo:  uv run pytest -m concurrency -v
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, delete, text
from sqlalchemy.orm import Session

from app.db import get_session, make_engine
from app.main import app
from app.models import (
    Installment,
    Notification,
    SavingsTransaction,
    UserBalance,
    UserSettings,
    WebhookEvent,
)
from app.providers import get_platform_provider, get_push_provider
from app.providers.mock_bank import MockBankAccountProvider
from app.providers.mock_platform import MockPlatformProvider
from app.providers.mock_push import MockPushProvider
from app.webhooks import processor
from app.webhooks.signature import get_now, get_vendor_secrets, sign
from tests.db.factories import profile
from tests.processing.conftest import CONSENT_AT
from tests.webhooks.conftest import NOW, SECRETS, VENDOR
from tests.webhooks.payloads import encode

MAX_THREADS = 50


@pytest.fixture(scope="session")
def concurrent_engine(engine: Engine, test_db_url: str) -> Iterator[Engine]:
    """A pool big enough that every thread holds its own connection at once, built by
    the app's make_engine so it runs at the app's isolation level (R7). Depends on
    `engine` so migrations have run."""
    eng = make_engine(test_db_url, pool_size=MAX_THREADS, max_overflow=0, pool_timeout=30)
    yield eng
    eng.dispose()


def _clean_up(eng: Engine, user: str) -> None:
    with eng.begin() as conn:
        conn.execute(delete(Notification).where(Notification.user_id == user))
        conn.execute(delete(SavingsTransaction).where(SavingsTransaction.user_id == user))
        conn.execute(delete(UserBalance).where(UserBalance.user_id == user))
        conn.execute(delete(UserSettings).where(UserSettings.user_id == user))
        conn.execute(delete(Installment).where(Installment.user_id == user))
        conn.execute(delete(WebhookEvent).where(WebhookEvent.user_id == user))
        conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
        conn.execute(text("DELETE FROM audit_log WHERE user_id = :user"), {"user": user})
        conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only"))


@dataclass
class Race:
    engine: Engine
    client: TestClient
    bank: MockBankAccountProvider
    push: MockPushProvider
    platform: MockPlatformProvider
    user: str

    def fire(self, bodies: list[dict[str, Any]]) -> list[httpx.Response]:
        """POST every body from its own thread, all released at the same instant."""
        return self.parallel([lambda data=data: self.post_webhook(data) for data in bodies])

    def post_webhook(self, data: dict[str, Any]) -> httpx.Response:
        body = encode(data)
        headers = {
            "X-Vendor-Id": VENDOR,
            "X-Timestamp": str(NOW),
            "X-Signature": sign(SECRETS[VENDOR], str(NOW), body),
            "Content-Type": "application/json",
        }
        return self.client.post("/webhooks/bnpl", content=body, headers=headers)

    def not_me(self, installment_id: uuid.UUID) -> httpx.Response:
        return self.client.post(
            f"/debts/{installment_id}/not-me", headers={"X-Demo-User": self.user}
        )

    def parallel(self, calls: list[Callable[[], httpx.Response]]) -> list[httpx.Response]:
        """Run every call from its own thread, all released at the same instant."""
        barrier = threading.Barrier(len(calls))
        responses: list[httpx.Response | None] = [None] * len(calls)
        errors: list[BaseException] = []

        def send(index: int, call: Callable[[], httpx.Response]) -> None:
            try:
                barrier.wait(timeout=30)
                responses[index] = call()
            except BaseException as exc:  # reported by the main thread
                errors.append(exc)

        threads = [threading.Thread(target=send, args=(i, call)) for i, call in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        # R6: a thread still alive may yet commit, so nothing below could be trusted.
        alive = [thread.name for thread in threads if thread.is_alive()]
        if alive:
            pytest.fail(f"requests still in flight after 120 s: {alive}")
        assert not errors, errors
        assert all(r is not None for r in responses), "a request did not finish"
        return [r for r in responses if r is not None]

    def id(self, name: str) -> str:
        """An event or contract id unique to this test (R6): a run killed before its
        clean-up cannot collide with a later one."""
        return f"{self.user}_{name}"

    def session(self) -> Session:
        return Session(self.engine)


@pytest.fixture
def race(
    concurrent_engine: Engine, migration_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Race]:
    user = f"conc_{uuid.uuid4().hex[:12]}"
    bank = MockBankAccountProvider()
    push = MockPushProvider()
    platform = MockPlatformProvider()

    def fresh_session() -> Iterator[Session]:
        with Session(concurrent_engine) as session:
            yield session

    overrides: dict[Callable[..., Any], Callable[..., Any]] = {
        get_session: fresh_session,
        get_vendor_secrets: lambda: {v: SecretStr(s) for v, s in SECRETS.items()},
        get_now: lambda: NOW,
        get_push_provider: lambda: push,
        get_platform_provider: lambda: platform,
    }
    monkeypatch.setattr(processor, "get_bank_provider", lambda: bank)
    app.dependency_overrides.update(overrides)
    try:
        with Session(concurrent_engine) as session, session.begin():
            session.add(
                UserSettings(
                    user_id=user, auto_save_enabled=True, consent_at=CONSENT_AT, **profile()
                )
            )
        with TestClient(app) as client:
            yield Race(concurrent_engine, client, bank, push, platform, user)
    finally:
        app.dependency_overrides.clear()
        _clean_up(migration_engine, user)
