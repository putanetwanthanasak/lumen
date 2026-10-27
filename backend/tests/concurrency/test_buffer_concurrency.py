"""BF-06 and BF-07: concurrent moves from the buffer to the main account (L66), each
request on its own thread and its own DB connection.

The balance row lock serialises moves for one user: a repeat waits and then finds
the first move; a different move waits and then sees the reduced balance.
"""

from collections import Counter
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.ledger.reconcile import check_user_invariants
from app.models import SavingsTransaction, UserBalance
from tests.concurrency.conftest import Race
from tests.concurrency.test_manual_entry_concurrency import entry

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

OPENING = Decimal("10000.00")


def saved_500(race: Race) -> None:
    """The race user saves 10%: a 5,000.00 entry puts 500.00 in the buffer."""
    response = race.post_manual(entry(race.id("req_seed"), "5000.00"))
    assert response.status_code == 201
    assert response.json()["saved_amount"] == "500.00"


def move(race: Race, request_id: str, amount: str) -> httpx.Response:
    body: dict[str, Any] = {"client_request_id": request_id, "amount": amount}
    return race.client.post("/buffer/move-to-main", json=body, headers={"X-Demo-User": race.user})


def withdrawals(race: Race) -> list[Decimal]:
    with race.session() as s:
        return list(
            s.scalars(
                select(SavingsTransaction.amount).where(
                    SavingsTransaction.user_id == race.user,
                    SavingsTransaction.type == "withdrawal",
                )
            )
        )


def test_BF_06_same_move_8_times_concurrently_moves_once(race: Race) -> None:
    saved_500(race)
    request_id = race.id("move_same")

    responses = race.parallel([lambda: move(race, request_id, "300.00") for _ in range(8)])

    assert Counter(r.status_code for r in responses) == {201: 1, 200: 7}
    assert len({r.json()["transaction_id"] for r in responses}) == 1
    assert withdrawals(race) == [Decimal("300.00")]
    with race.session() as s:
        balance = s.scalar(
            select(UserBalance.savings_balance).where(UserBalance.user_id == race.user)
        )
        assert balance == Decimal("200.00")
        assert check_user_invariants(s, race.user) == []  # INV-1, INV-2
    assert race.bank.get_balance(race.user) == OPENING - Decimal("500.00") + Decimal("300.00")


def test_BF_07_different_moves_over_the_balance_only_the_ones_that_fit_succeed(
    race: Race,
) -> None:
    # 05 SV-06: 8 moves of 150.00 against 500.00: exactly 3 fit, 50.00 stays.
    saved_500(race)

    responses = race.parallel(
        [lambda i=i: move(race, race.id(f"move_{i}"), "150.00") for i in range(8)]
    )

    assert Counter(r.status_code for r in responses) == {201: 3, 422: 5}
    assert withdrawals(race) == [Decimal("150.00")] * 3
    with race.session() as s:
        balance = s.scalar(
            select(UserBalance.savings_balance).where(UserBalance.user_id == race.user)
        )
        assert balance == Decimal("50.00")
        assert check_user_invariants(s, race.user) == []
    assert race.bank.get_balance(race.user) == OPENING - Decimal("500.00") + Decimal("450.00")
