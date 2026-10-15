"""ID-02 and ID-03 (05 section 4.4): concurrent webhooks through the real HTTP path,
each request on its own thread and its own DB connection.

Demo:  cd backend && uv run pytest -m concurrency -v
"""

from collections import Counter
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ledger.reconcile import check_user_invariants
from app.models import Installment, SavingsTransaction, UserBalance, WebhookEvent
from tests.concurrency.conftest import Race
from tests.processing.conftest import created

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

OPENING = Decimal("10000.00")


def test_ID_02_same_event_8_times_concurrently_saves_once(race: Race) -> None:
    event = created("evt_same", "c_same", "800.00", user=race.user)

    responses = race.fire([event] * 8)

    outcomes = Counter((r.status_code, r.json()["status"]) for r in responses)
    assert outcomes == {(200, "processed"): 1, (200, "duplicate"): 7}
    with race.session() as s:
        user = race.user
        assert s.scalar(select(func.count()).where(WebhookEvent.user_id == user)) == 1
        assert s.scalar(select(func.count()).where(Installment.user_id == user)) == 1
        amounts = s.scalars(
            select(SavingsTransaction.amount).where(SavingsTransaction.user_id == user)
        ).all()
        assert amounts == [Decimal("80.00")]
        row = s.execute(select(UserBalance).where(UserBalance.user_id == user)).scalar_one()
        assert (row.savings_balance, row.version) == (Decimal("80.00"), 1)  # INV-1
        assert check_user_invariants(s, user) == []
    assert race.bank.get_balance(race.user) == OPENING - Decimal("80.00")  # moved once


def test_ID_03_50_distinct_events_concurrently_for_one_user(race: Race) -> None:
    # Principal 1,000 + 10i saves 100.00 + i: distinct amounts, so a lost update
    # cannot hide behind equal values.
    events = [
        created(f"evt_{i:02}", f"c_{i:02}", f"{1000 + 10 * i}.00", user=race.user)
        for i in range(50)
    ]
    expected = sum((Decimal("100.00") + i for i in range(50)), Decimal("0.00"))
    assert expected == Decimal("6225.00")

    responses = race.fire(events)

    assert Counter((r.status_code, r.json()["status"]) for r in responses) == {
        (200, "processed"): 50
    }
    with race.session() as s:
        user = race.user
        amounts = s.scalars(
            select(SavingsTransaction.amount).where(SavingsTransaction.user_id == user)
        ).all()
        assert len(amounts) == 50
        assert sum(amounts, Decimal("0.00")) == expected
        row = s.execute(select(UserBalance).where(UserBalance.user_id == user)).scalar_one()
        assert (row.savings_balance, row.version) == (expected, 50)  # INV-1, no lost update
        assert check_user_invariants(s, user) == []
    assert race.bank.get_balance(race.user) == OPENING - expected
