"""Auto-save on contract-created events: SV-01, SV-02, SV-03, SV-03a (05 section 4.6),
INV-4 and the safety net through the bank provider (L46 + L52), L51."""

from decimal import Decimal

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import ORMExecuteState, Session

from app.models import Installment, UserBalance
from app.providers.mock_bank import MockBankAccountProvider
from app.savings import service as savings
from app.webhooks.processor import Outcome
from tests.processing.conftest import (
    USER,
    VENDOR,
    auto_saves,
    balance,
    created,
    opt_in,
    run,
)

pytestmark = pytest.mark.db

OPENING = Decimal("10000.00")


def test_auto_save_recorded_with_source_installment_and_balance(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    assert run(db_session, created("evt_1", "c_1", "800.00"), bank) == Outcome.PROCESSED

    [tx] = auto_saves(db_session)
    installment_id = db_session.execute(select(Installment.id)).scalar_one()
    assert (tx.type, tx.amount, tx.user_id) == ("auto_save", Decimal("80.00"), USER)
    assert (tx.source_vendor, tx.source_event_id, tx.installment_id) == (
        VENDOR,
        "evt_1",
        installment_id,
    )
    assert balance(db_session) == (Decimal("80.00"), 1)
    assert bank.get_balance(USER) == OPENING - Decimal("80.00")


def test_second_purchase_adds_to_balance(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    run(db_session, created("evt_1", "c_1", "800.00"), bank)
    run(db_session, created("evt_2", "c_2", "2000.00"), bank)

    assert sorted(tx.amount for tx in auto_saves(db_session)) == [
        Decimal("80.00"),
        Decimal("200.00"),
    ]
    assert balance(db_session) == (Decimal("280.00"), 2)
    assert bank.get_balance(USER) == OPENING - Decimal("280.00")


@pytest.mark.parametrize(
    ("principal", "expected"),
    [
        ("50.00", "10.00"),  # 5.00 raised to the 10.00 minimum
        ("100.05", "10.01"),  # 10.005 rounds half up
        ("4999.99", "500.00"),
        ("20000.00", "500.00"),  # capped at 500.00
    ],
)
def test_INV_4_auto_save_within_min_and_max(
    db_session: Session, bank: MockBankAccountProvider, principal: str, expected: str
) -> None:
    opt_in(db_session)
    run(db_session, created("evt_1", "c_1", principal), bank)

    [tx] = auto_saves(db_session)
    assert tx.amount == Decimal(expected)
    assert Decimal("10.00") <= tx.amount <= Decimal("500.00")


def assert_nothing_saved(db_session: Session, bank: MockBankAccountProvider) -> None:
    assert auto_saves(db_session) == []
    assert balance(db_session) is None
    assert bank.get_balance(USER) == OPENING
    # The debt is still recorded: only the saving is skipped.
    assert db_session.execute(select(Installment.contract_id)).scalar_one() == "c_1"


def test_SV_01_auto_save_disabled_no_saving(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session, enabled=False)
    assert run(db_session, created("evt_1", "c_1"), bank) == Outcome.PROCESSED
    assert_nothing_saved(db_session, bank)


def test_SV_01_never_opted_in_no_saving(db_session: Session, bank: MockBankAccountProvider) -> None:
    # No user_settings row at all: auto-save defaults to off (04 section 4.5).
    assert run(db_session, created("evt_1", "c_1"), bank) == Outcome.PROCESSED
    assert_nothing_saved(db_session, bank)


def test_SV_02_enabled_without_consent_no_saving(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session, consent=False)
    assert run(db_session, created("evt_1", "c_1"), bank) == Outcome.PROCESSED
    assert_nothing_saved(db_session, bank)


def test_SV_03_cash_withdrawal_never_saves(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    data = created("evt_1", "c_1", "15000.00", event_type="cash_withdrawal_created")
    assert run(db_session, data, bank) == Outcome.PROCESSED
    assert_nothing_saved(db_session, bank)
    assert db_session.execute(select(Installment.kind)).scalar_one() == "cash_withdrawal"


def test_SV_03a_cash_loan_never_saves(db_session: Session, bank: MockBankAccountProvider) -> None:
    opt_in(db_session)
    data = created("evt_1", "c_1", "15000.00", event_type="cash_loan_created")
    assert run(db_session, data, bank) == Outcome.PROCESSED
    assert_nothing_saved(db_session, bank)
    # Counted in the debt overview like any other installment.
    assert db_session.execute(select(Installment.kind)).scalar_one() == "cash_loan"


def test_RE_07_safety_net_reads_balance_from_bank_provider(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    bank.set_balance(USER, Decimal("579.99"))  # 579.99 - 80.00 < 500.00: skip, no partial
    assert run(db_session, created("evt_1", "c_1", "800.00"), bank) == Outcome.PROCESSED
    assert auto_saves(db_session) == []
    assert bank.get_balance(USER) == Decimal("579.99")


def test_RE_07_safety_net_saves_at_exact_protected_min(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    bank.set_balance(USER, Decimal("580.00"))  # leaves exactly 500.00
    run(db_session, created("evt_1", "c_1", "800.00"), bank)
    assert [tx.amount for tx in auto_saves(db_session)] == [Decimal("80.00")]
    assert bank.get_balance(USER) == Decimal("500.00")


def test_L51_saving_belongs_to_event_user(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session, "user_b")
    opt_in(db_session, USER)
    run(db_session, created("evt_1", "c_1", "800.00", user="user_b"), bank)

    assert [tx.user_id for tx in auto_saves(db_session, "user_b")] == ["user_b"]
    assert auto_saves(db_session, USER) == []
    assert balance(db_session, "user_b") == (Decimal("80.00"), 1)
    assert bank.get_balance("user_b") == OPENING - Decimal("80.00")
    assert bank.get_balance(USER) == OPENING


def test_balance_contention_gives_up_after_max_attempts(
    db_session: Session, bank: MockBankAccountProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    opt_in(db_session)
    monkeypatch.setattr(savings, "MAX_CREDIT_ATTEMPTS", 0)
    with pytest.raises(savings.BalanceContentionError) as exc:
        run(db_session, created("evt_1", "c_1"), bank)
    assert USER not in str(exc.value)  # S12: the message reaches the server log
    assert bank.get_balance(USER) == OPENING  # raised before any money moved


def test_INV_1_credit_retries_when_another_writer_wins(db_session: Session) -> None:
    """Deterministic lost-update check: another writer commits between this
    transaction's read and its UPDATE. The version check must make the UPDATE miss,
    re-read, and apply on top of the other write instead of overwriting it."""
    db_session.add(UserBalance(user_id=USER, savings_balance=Decimal("100.00"), version=3))
    db_session.flush()
    interfered = False

    def other_writer_first(state: ORMExecuteState) -> None:
        nonlocal interfered
        if state.is_update and not interfered:
            interfered = True
            state.session.connection().execute(
                text(
                    "UPDATE user_balances SET savings_balance = savings_balance + 5,"
                    " version = version + 1 WHERE user_id = :user"
                ),
                {"user": USER},
            )

    event.listen(db_session, "do_orm_execute", other_writer_first)
    try:
        savings._credit(db_session, USER, Decimal("80.00"))
    finally:
        event.remove(db_session, "do_orm_execute", other_writer_first)

    assert interfered
    assert balance(db_session) == (Decimal("185.00"), 5)  # 100 + 5 + 80; nothing lost
