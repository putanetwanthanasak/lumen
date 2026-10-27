"""MockConsolidationBank (L71, L72): a fixed decision per reference, and each payout
key paid at most once (as S1). No bank is asked; nothing is sent."""

import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.providers import get_consolidation_bank
from app.providers.base import Application, Payoff
from app.providers.mock_consolidation import MockConsolidationBank, PaidOut

PAYOFF = Payoff(uuid.uuid4(), "shopdemo", "c_1", Decimal("100.00"))


def application(reference: str = "ref-1") -> Application:
    return Application("u", reference, (PAYOFF,), Decimal("0.18"), 24)


def pay(bank: MockConsolidationBank, amount: Any, key: str = "k-1") -> None:
    bank.pay_out(vendor="shopdemo", contract_id="c_1", amount=amount, idempotency_key=key)


def test_CO_11_the_same_reference_gets_the_same_decision() -> None:
    bank = MockConsolidationBank()
    first = bank.decide(application())

    assert bank.decide(application()) is first
    assert (first.approved, first.payoffs) == (True, (PAYOFF,))
    assert bank.decide(application("ref-2")).reference != first.reference


def test_CO_11_decline_approves_no_payoff() -> None:
    decision = MockConsolidationBank("decline").decide(application())

    assert (decision.approved, decision.payoffs) == (False, ())


def test_CO_13_a_payout_key_pays_once() -> None:
    bank = MockConsolidationBank()
    pay(bank, Decimal("100.00"))
    pay(bank, Decimal("100.00"))

    assert bank.payouts == [PaidOut("shopdemo", "c_1", Decimal("100.00"))]


def test_CO_13_a_payout_key_reused_for_another_amount_is_refused() -> None:
    bank = MockConsolidationBank()
    pay(bank, Decimal("100.00"))

    with pytest.raises(ValueError, match="idempotency key reused"):
        pay(bank, Decimal("100.01"))
    assert len(bank.payouts) == 1


@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("-1.00"), 100])
def test_CO_13_a_payout_must_be_a_positive_decimal(amount: Any) -> None:
    bank = MockConsolidationBank()

    with pytest.raises(ValueError, match="positive Decimal"):
        pay(bank, amount)
    assert bank.payouts == []


def test_app_uses_one_shared_consolidation_mock() -> None:
    assert isinstance(get_consolidation_bank(), MockConsolidationBank)
    assert get_consolidation_bank() is get_consolidation_bank()
