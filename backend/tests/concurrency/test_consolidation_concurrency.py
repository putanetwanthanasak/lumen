"""CO-09: consolidation requests at the same instant (L70, L72), through HTTP, each on
its own thread and its own DB connection.

The same client_request_id 8 times: one approval, the others get its stored answer.
Two different ids at once: the per-user lock serialises them, so the second sees the
first's loan, is no longer eligible, and makes no second loan.
"""

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from app.clock import today
from app.ledger.reconcile import check_user_invariants
from app.main import app
from app.models import ConsolidationPayout, ConsolidationRequest, Installment
from app.providers import get_consolidation_bank
from app.providers.base import Application, Decision
from app.providers.mock_consolidation import MockConsolidationBank
from tests.concurrency.conftest import Race
from tests.consolidation.conftest import TODAY
from tests.db.factories import manual_installment

pytestmark = [pytest.mark.db, pytest.mark.concurrency]


def setup(race: Race) -> tuple[MockConsolidationBank, list[dict[str, str]]]:
    """6,000.00 and 4,000.00 a month for 3 months against a 9,000.00 budget: eligible.
    Returns the bank and the payoffs that match the counted set."""
    bank = MockConsolidationBank()
    app.dependency_overrides[today] = lambda: TODAY
    app.dependency_overrides[get_consolidation_bank] = lambda: bank
    payoffs = []
    with race.session() as s, s.begin():
        for monthly in ("6000.00", "4000.00"):
            row = manual_installment(
                user_id=race.user,
                contract_id=race.id(str(uuid.uuid4())),
                client_request_id=race.id(monthly),
                principal=Decimal(monthly) * 3,
                monthly_amount=Decimal(monthly),
                months=3,
                first_due_date=date(2026, 11, 1),
            )
            s.add(row)
            s.flush()
            payoffs.append(
                {"installment_id": str(row.id), "payoff_amount": str(Decimal(monthly) * 3)}
            )
    return bank, payoffs


def request(
    race: Race, client_request_id: str, payoffs: list[dict[str, str]]
) -> Callable[[], httpx.Response]:
    def call() -> httpx.Response:
        return race.client.post(
            "/consolidation/requests",
            json={"client_request_id": client_request_id, "consent": True, "payoffs": payoffs},
            headers={"X-Demo-User": race.user},
        )

    return call


def stored(race: Race) -> tuple[int, int, int]:
    with race.session() as s:
        user = race.user
        requests = s.scalar(select(func.count()).where(ConsolidationRequest.user_id == user))
        loans = s.scalar(
            select(func.count()).where(
                Installment.user_id == user, Installment.kind == "consolidation_loan"
            )
        )
        payouts = s.scalar(select(func.count()).where(ConsolidationPayout.user_id == user))
        assert check_user_invariants(s, user) == []
        return requests or 0, loans or 0, payouts or 0


def test_CO_09_the_same_request_8_times_concurrently_approves_once(race: Race) -> None:
    bank, payoffs = setup(race)

    responses = race.parallel([request(race, "req-1", payoffs) for _ in range(8)])

    assert Counter(r.status_code for r in responses) == {201: 1, 200: 7}
    assert len({r.json()["request_id"] for r in responses}) == 1
    assert len({r.json()["loan"]["installment_id"] for r in responses}) == 1
    assert stored(race) == (1, 1, 2)
    # Every response paid out after its commit under the same keys: each platform once.
    assert sorted(p.amount for p in bank.payouts) == [Decimal("12000.00"), Decimal("18000.00")]


def test_CO_09_two_different_requests_concurrently_make_one_loan(race: Race) -> None:
    bank, payoffs = setup(race)

    responses = race.parallel([request(race, "req-a", payoffs), request(race, "req-b", payoffs)])

    assert sorted(r.status_code for r in responses) == [201, 409]
    [refused] = [r for r in responses if r.status_code == 409]
    # The loan alone is 1,497.73 a month: nothing is over budget any more.
    assert refused.json()["detail"] == {
        "code": "NOT_ELIGIBLE",
        "message": "consolidation is not available now",
        "reason": "NOT_NEEDED",
    }
    assert stored(race) == (1, 1, 2)
    assert len(bank.payouts) == 2


class ContractProbingBank(MockConsolidationBank):
    """While deciding, tries each paid-off contract's lock from another connection and
    records whether it was held: a platform event for that contract must wait for the
    approval to commit instead of writing over `consolidated` (review F3)."""

    def __init__(self, race: Race) -> None:
        super().__init__()
        self.race = race
        self.held: list[bool] = []

    def decide(self, application: Application) -> Decision:
        for payoff in application.payoffs:
            key = func.hashtextextended(f"{payoff.vendor}:{payoff.contract_id}", 0)
            with self.race.session() as other, other.begin():
                got = other.execute(select(func.pg_try_advisory_xact_lock(key))).scalar_one()
                self.held.append(not got)
        return super().decide(application)


def test_CO_09_every_paid_off_contract_is_locked_before_the_bank_decides(race: Race) -> None:
    """Deterministic: the webhook processor and "Not me" take the same contract lock
    (ledger.lock_contract), so they wait for the approval."""
    _, payoffs = setup(race)
    bank = ContractProbingBank(race)
    app.dependency_overrides[get_consolidation_bank] = lambda: bank

    response = request(race, "req-1", payoffs)()

    assert response.status_code == 201
    assert bank.held == [True, True]
