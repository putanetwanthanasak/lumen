"""MI-05: a concurrent double submit of one manual entry (L62), through the real HTTP
path, each request on its own thread and its own DB connection.

Demo:  cd backend && uv run pytest -m concurrency -v
"""

from collections import Counter
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select

from app.ledger.reconcile import check_user_invariants
from app.models import Installment, Notification, SavingsTransaction, UserBalance
from tests.concurrency.conftest import Race

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

OPENING = Decimal("10000.00")


def entry(request_id: str, price: str = "800.00") -> dict[str, Any]:
    return {
        "client_request_id": request_id,
        "kind": "purchase",
        "item_price": price,
        "months": 4,
        "monthly_amount": "200.00",
        "first_due_month": "2026-11",
    }


def test_MI_05_same_entry_8_times_concurrently_records_and_saves_once(race: Race) -> None:
    data = entry(race.id("req_same"))

    responses = race.parallel([lambda: race.post_manual(data) for _ in range(8)])

    assert Counter(r.status_code for r in responses) == {201: 1, 200: 7}
    assert len({r.json()["installment_id"] for r in responses}) == 1
    assert {r.json()["saved_amount"] for r in responses} == {"80.00"}
    with race.session() as s:
        user = race.user
        assert s.scalar(select(func.count()).where(Installment.user_id == user)) == 1
        amounts = s.scalars(
            select(SavingsTransaction.amount).where(SavingsTransaction.user_id == user)
        ).all()
        assert amounts == [Decimal("80.00")]
        assert s.scalar(select(func.count()).where(Notification.user_id == user)) == 1
        row = s.execute(select(UserBalance).where(UserBalance.user_id == user)).scalar_one()
        assert (row.savings_balance, row.version) == (Decimal("80.00"), 1)  # INV-1
        assert check_user_invariants(s, user) == []
    assert race.bank.get_balance(race.user) == OPENING - Decimal("80.00")  # moved once
    assert len(race.push.attempts) == 1


def test_MI_05_distinct_entries_concurrently_each_save(race: Race) -> None:
    # 20 different requests at once: none lost, none doubled. Price 1,000 + 10i saves
    # 100.00 + i, so a lost update cannot hide behind equal amounts.
    entries = [entry(race.id(f"req_{i:02}"), f"{1000 + 10 * i}.00") for i in range(20)]
    expected = sum((Decimal("100.00") + i for i in range(20)), Decimal("0.00"))

    responses = race.parallel([lambda data=data: race.post_manual(data) for data in entries])

    assert Counter(r.status_code for r in responses) == {201: 20}
    with race.session() as s:
        user = race.user
        assert s.scalar(select(func.count()).where(Installment.user_id == user)) == 20
        row = s.execute(select(UserBalance).where(UserBalance.user_id == user)).scalar_one()
        assert (row.savings_balance, row.version) == (expected, 20)
        assert check_user_invariants(s, user) == []
    assert race.bank.get_balance(race.user) == OPENING - expected
