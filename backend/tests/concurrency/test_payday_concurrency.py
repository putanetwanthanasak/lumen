"""PD-03: the same payday month run 8 times at once (L67), through HTTP, each request
on its own thread and its own DB connection. One run counts; the others get its
stored outcome and change nothing.
"""

import uuid
from collections import Counter
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.config import Settings
from app.ledger.reconcile import check_user_invariants
from app.main import app, create_app
from app.models import Notification, PaydayRun, SavingsTransaction, UserSettings
from tests.concurrency.conftest import Race
from tests.db.factories import installment

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

OPENING = Decimal("10000.00")


@pytest.fixture
def demo_client(race: Race) -> Iterator[TestClient]:
    """An app with the demo endpoint, wired to the race harness's session and mocks."""
    demo_app = create_app(Settings(demo_endpoints_enabled=True))
    demo_app.dependency_overrides.update(app.dependency_overrides)
    with TestClient(demo_app) as client:
        yield client


def setup(race: Race, monthly: str) -> None:
    """The race user (budget 9,000.00, auto-save on with consent) opts in to leftover
    saving and owes `monthly` in November 2026."""
    with race.session() as s, s.begin():
        s.execute(
            update(UserSettings)
            .where(UserSettings.user_id == race.user)
            .values(leftover_saving_enabled=True)
        )
        s.add(
            installment(
                user_id=race.user,
                contract_id=race.id(str(uuid.uuid4())),
                principal=Decimal(monthly),
                monthly_amount=Decimal(monthly),
                months=1,
                first_due_date=date(2026, 11, 1),
            )
        )


def run_8(race: Race, client: TestClient) -> list[httpx.Response]:
    def payday() -> httpx.Response:
        return client.post(
            "/demo/payday", json={"month": "2026-11"}, headers={"X-Demo-User": race.user}
        )

    return race.parallel([payday for _ in range(8)])


def counts(race: Race) -> tuple[int, int, list[Decimal]]:
    with race.session() as s:
        user = race.user
        runs = s.scalar(select(func.count()).where(PaydayRun.user_id == user))
        alerts = s.scalar(select(func.count()).where(Notification.user_id == user))
        saved = s.scalars(
            select(SavingsTransaction.amount).where(
                SavingsTransaction.user_id == user, SavingsTransaction.type == "leftover_save"
            )
        ).all()
        assert check_user_invariants(s, user) == []
        return runs or 0, alerts or 0, list(saved)


def test_PD_03_over_budget_8_times_concurrently_alerts_once(
    race: Race, demo_client: TestClient
) -> None:
    setup(race, "9500.00")

    responses = run_8(race, demo_client)

    assert Counter(r.status_code for r in responses) == {201: 1, 200: 7}
    assert {r.json()["outcome"] for r in responses} == {"over_budget"}
    assert counts(race) == (1, 1, [])
    assert len(race.push.attempts) == 1


def test_PD_03_leftover_8_times_concurrently_saves_once(
    race: Race, demo_client: TestClient
) -> None:
    setup(race, "7000.00")

    responses = run_8(race, demo_client)

    assert Counter(r.status_code for r in responses) == {201: 1, 200: 7}
    assert {r.json()["amount"] for r in responses} == {"2000.00"}
    assert counts(race) == (1, 1, [Decimal("2000.00")])
    assert race.bank.get_balance(race.user) == OPENING - Decimal("2000.00")  # debited once
