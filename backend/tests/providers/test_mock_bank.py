"""MockBankAccountProvider (04 section 8, decision D2). No database."""

import threading
from decimal import Decimal

import pytest

from app.providers import get_bank_provider
from app.providers.mock_bank import DEFAULT_OPENING_BALANCE, MockBankAccountProvider


def test_unseen_user_opens_with_default_balance() -> None:
    assert MockBankAccountProvider().get_balance("anyone") == Decimal("10000.00")


def test_set_balance_seeds_one_user() -> None:
    bank = MockBankAccountProvider()
    bank.set_balance("u1", Decimal("505.00"))
    assert bank.get_balance("u1") == Decimal("505.00")
    assert bank.get_balance("u2") == DEFAULT_OPENING_BALANCE


def test_transfers_move_exact_amounts() -> None:
    bank = MockBankAccountProvider(Decimal("100.00"))
    bank.transfer_to_savings("u1", Decimal("30.01"))
    assert bank.get_balance("u1") == Decimal("69.99")
    bank.transfer_from_savings("u1", Decimal("0.01"))
    assert bank.get_balance("u1") == Decimal("70.00")
    bank.transfer_to_savings("u1", Decimal("70.00"))  # down to exactly zero
    assert bank.get_balance("u1") == Decimal("0.00")


def test_transfer_beyond_balance_rejected_and_nothing_moves() -> None:
    bank = MockBankAccountProvider(Decimal("10.00"))
    with pytest.raises(ValueError, match="insufficient funds"):
        bank.transfer_to_savings("u1", Decimal("10.01"))
    assert bank.get_balance("u1") == Decimal("10.00")


@pytest.mark.parametrize(
    "amount",
    [0.5, 1, "1.00", Decimal("1.001"), Decimal("NaN"), Decimal("Infinity")],
    ids=["float", "int", "str", "3dp", "nan", "inf"],
)
def test_non_money_amount_rejected(amount: object) -> None:
    bank = MockBankAccountProvider()
    for call in (bank.transfer_to_savings, bank.transfer_from_savings, bank.set_balance):
        with pytest.raises(ValueError, match="amount"):
            call("u1", amount)  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("-1.00")])
def test_transfer_amount_must_be_positive(amount: Decimal) -> None:
    bank = MockBankAccountProvider()
    with pytest.raises(ValueError, match="> 0"):
        bank.transfer_to_savings("u1", amount)
    with pytest.raises(ValueError, match="> 0"):
        bank.transfer_from_savings("u1", amount)


def test_negative_balance_cannot_be_seeded() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        MockBankAccountProvider(Decimal("-0.01"))


def test_concurrent_transfers_lose_nothing() -> None:
    bank = MockBankAccountProvider(Decimal("1000.00"))
    threads = [
        threading.Thread(target=bank.transfer_to_savings, args=("u1", Decimal("1.00")))
        for _ in range(200)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert bank.get_balance("u1") == Decimal("800.00")


def test_app_uses_one_shared_mock_in_mock_mode() -> None:
    assert isinstance(get_bank_provider(), MockBankAccountProvider)
    assert get_bank_provider() is get_bank_provider()
