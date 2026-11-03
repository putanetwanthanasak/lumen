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
    bank.transfer_to_savings("u1", Decimal("30.01"), idempotency_key="k1")
    assert bank.get_balance("u1") == Decimal("69.99")
    bank.transfer_from_savings("u1", Decimal("0.01"), idempotency_key="m1")
    assert bank.get_balance("u1") == Decimal("70.00")
    bank.transfer_to_savings("u1", Decimal("70.00"), idempotency_key="k2")  # down to zero
    assert bank.get_balance("u1") == Decimal("0.00")


def test_transfer_beyond_balance_rejected_and_nothing_moves() -> None:
    bank = MockBankAccountProvider(Decimal("10.00"))
    with pytest.raises(ValueError, match="insufficient funds"):
        bank.transfer_to_savings("u1", Decimal("10.01"), idempotency_key="k1")
    assert bank.get_balance("u1") == Decimal("10.00")


@pytest.mark.parametrize(
    "amount",
    [0.5, 1, "1.00", Decimal("1.001"), Decimal("NaN"), Decimal("Infinity")],
    ids=["float", "int", "str", "3dp", "nan", "inf"],
)
def test_non_money_amount_rejected(amount: object) -> None:
    bank = MockBankAccountProvider()
    with pytest.raises(ValueError, match="amount"):
        bank.transfer_to_savings("u1", amount, idempotency_key="k1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="amount"):
        bank.transfer_from_savings("u1", amount, idempotency_key="m1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="amount"):
        bank.set_balance("u1", amount)  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("-1.00")])
def test_transfer_amount_must_be_positive(amount: Decimal) -> None:
    bank = MockBankAccountProvider()
    with pytest.raises(ValueError, match="> 0"):
        bank.transfer_to_savings("u1", amount, idempotency_key="k1")
    with pytest.raises(ValueError, match="> 0"):
        bank.transfer_from_savings("u1", amount, idempotency_key="m1")


def test_negative_balance_cannot_be_seeded() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        MockBankAccountProvider(Decimal("-0.01"))


def test_concurrent_transfers_lose_nothing() -> None:
    bank = MockBankAccountProvider(Decimal("1000.00"))
    threads = [
        threading.Thread(
            target=bank.transfer_to_savings,
            args=("u1", Decimal("1.00")),
            kwargs={"idempotency_key": f"k{i}"},
        )
        for i in range(200)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert bank.get_balance("u1") == Decimal("800.00")


def test_S1_same_key_debits_once() -> None:
    bank = MockBankAccountProvider(Decimal("100.00"))
    for _ in range(3):
        bank.transfer_to_savings("u1", Decimal("10.00"), idempotency_key="evt-1")
    assert bank.get_balance("u1") == Decimal("90.00")
    bank.transfer_to_savings("u1", Decimal("10.00"), idempotency_key="evt-2")  # a new key
    assert bank.get_balance("u1") == Decimal("80.00")


@pytest.mark.parametrize(
    ("user", "amount"), [("u2", Decimal("10.00")), ("u1", Decimal("10.01"))], ids=["user", "amount"]
)
def test_S1_key_reused_for_a_different_transfer_rejected(user: str, amount: Decimal) -> None:
    bank = MockBankAccountProvider(Decimal("100.00"))
    bank.transfer_to_savings("u1", Decimal("10.00"), idempotency_key="evt-1")
    with pytest.raises(ValueError, match="idempotency key reused"):
        bank.transfer_to_savings(user, amount, idempotency_key="evt-1")
    assert (bank.get_balance("u1"), bank.get_balance("u2")) == (Decimal("90.00"), Decimal("100.00"))


def test_S1_a_failed_transfer_does_not_burn_its_key() -> None:
    bank = MockBankAccountProvider(Decimal("5.00"))
    with pytest.raises(ValueError, match="insufficient funds"):
        bank.transfer_to_savings("u1", Decimal("10.00"), idempotency_key="evt-1")
    bank.set_balance("u1", Decimal("50.00"))
    bank.transfer_to_savings("u1", Decimal("10.00"), idempotency_key="evt-1")
    assert bank.get_balance("u1") == Decimal("40.00")


def test_S1_concurrent_retries_with_one_key_debit_once() -> None:
    bank = MockBankAccountProvider(Decimal("1000.00"))
    threads = [
        threading.Thread(
            target=bank.transfer_to_savings,
            args=("u1", Decimal("1.00")),
            kwargs={"idempotency_key": "evt-1"},
        )
        for _ in range(50)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert bank.get_balance("u1") == Decimal("999.00")


def test_app_uses_one_shared_mock_in_mock_mode() -> None:
    assert isinstance(get_bank_provider(), MockBankAccountProvider)
    assert get_bank_provider() is get_bank_provider()


def test_S1_move_to_main_applies_each_key_once() -> None:
    # L66: a retry of the same move after a lost commit credits the main account once.
    bank = MockBankAccountProvider(Decimal("100.00"))
    for _ in range(2):
        bank.transfer_from_savings("u1", Decimal("40.00"), idempotency_key="m1")
    assert bank.get_balance("u1") == Decimal("140.00")
    bank.transfer_from_savings("u1", Decimal("40.00"), idempotency_key="m2")
    assert bank.get_balance("u1") == Decimal("180.00")


@pytest.mark.parametrize(
    ("direction", "user", "amount"),
    [
        ("to_savings", "u1", "40.00"),
        ("from_savings", "u2", "40.00"),
        ("from_savings", "u1", "41.00"),
    ],
)
def test_S1_key_reused_for_another_transfer_is_refused(
    direction: str, user: str, amount: str
) -> None:
    bank = MockBankAccountProvider(Decimal("100.00"))
    bank.transfer_from_savings("u1", Decimal("40.00"), idempotency_key="k")
    transfer = bank.transfer_to_savings if direction == "to_savings" else bank.transfer_from_savings
    with pytest.raises(ValueError, match="reused"):
        transfer(user, Decimal(amount), idempotency_key="k")
    assert bank.get_balance("u1") == Decimal("140.00")


def test_LO_06_applied_to_savings_reports_what_a_key_moved() -> None:
    bank = MockBankAccountProvider(Decimal("100.00"))
    assert bank.applied_to_savings("u1", "k1") is None
    bank.transfer_to_savings("u1", Decimal("30.01"), idempotency_key="k1")
    assert bank.applied_to_savings("u1", "k1") == Decimal("30.01")
    assert bank.applied_to_savings("u1", "k2") is None


@pytest.mark.parametrize("move", ["other_user", "from_savings"])
def test_LO_06_applied_to_savings_refuses_a_key_used_for_another_transfer(move: str) -> None:
    bank = MockBankAccountProvider()
    if move == "other_user":
        bank.transfer_to_savings("u2", Decimal("1.00"), idempotency_key="k1")
    else:
        bank.transfer_from_savings("u1", Decimal("1.00"), idempotency_key="k1")
    with pytest.raises(ValueError, match="idempotency key reused"):
        bank.applied_to_savings("u1", "k1")


# --- KD-04 (Session 21): restoring a credit the ledger already holds ----------------------


def test_KD_04_mark_credited_moves_nothing_and_a_retry_under_its_key_moves_nothing() -> None:
    # The KidNee serve opens a fresh bank from the savings rows: a move to main already
    # in the rows is marked credited, so its retry (a DUPLICATE) is not credited again.
    bank = MockBankAccountProvider(Decimal("100.00"))
    bank.mark_credited("u1", Decimal("40.00"), idempotency_key="m1")
    assert bank.get_balance("u1") == Decimal("100.00")
    bank.transfer_from_savings("u1", Decimal("40.00"), idempotency_key="m1")
    assert bank.get_balance("u1") == Decimal("100.00")
    bank.mark_credited("u1", Decimal("40.00"), idempotency_key="m1")  # again: the same, fine
    bank.transfer_from_savings("u1", Decimal("40.00"), idempotency_key="m2")
    assert bank.get_balance("u1") == Decimal("140.00")


@pytest.mark.parametrize(("user", "amount"), [("u2", "40.00"), ("u1", "41.00")])
def test_KD_04_mark_credited_refuses_a_key_used_for_another_transfer(
    user: str, amount: str
) -> None:
    bank = MockBankAccountProvider()
    bank.transfer_from_savings("u1", Decimal("40.00"), idempotency_key="m1")
    with pytest.raises(ValueError, match="different transfer"):
        bank.mark_credited(user, Decimal(amount), idempotency_key="m1")
    with pytest.raises(ValueError, match="amount must be > 0"):
        bank.mark_credited("u1", Decimal("0.00"), idempotency_key="m9")
