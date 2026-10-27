"""reconcile.assert_user_invariants (04 step 7): INV-1, INV-2, INV-3, INV-5, L51,
and RS-02 (05 section 4.8): a violation rolls back the whole event and is logged.

Each violation test writes the bad state by hand. Where the DB already blocks it
(INV-2 CHECK, INV-3 UNIQUE), the test drops that guard inside its own rolled-back
transaction: reconcile is the second layer and must catch it on its own.
"""

import logging
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.ledger import reconcile
from app.ledger.reconcile import InvariantViolationError, assert_user_invariants
from app.models import (
    AuditLog,
    Installment,
    SavingsTransaction,
    UserBalance,
    UserSettings,
    WebhookEvent,
)
from app.providers.mock_bank import MockBankAccountProvider
from app.savings import service as savings
from tests.db.factories import installment, manual_installment, savings_tx, webhook_event
from tests.processing.conftest import USER, VENDOR, auto_saves, count, created, opt_in, run

pytestmark = pytest.mark.db


def violations(session: Session, user: str = USER) -> list[str]:
    return reconcile.check_user_invariants(session, user)


def _history(session: Session, bank: MockBankAccountProvider) -> Session:
    """Purchases, cash events and an ID-05 resend for one user, all through the processor."""
    opt_in(session)
    run(session, created("evt_1", "c_1", "800.00"), bank)
    run(session, created("evt_2", "c_2", "100.00"), bank)  # 10% (L63): 10.00
    run(session, created("evt_3", "c_3", "15000.00", event_type="cash_withdrawal_created"), bank)
    run(session, created("evt_4", "c_4", "9000.00", event_type="cash_loan_created"), bank)
    run(session, created("evt_5", "c_1", "800.00"), bank)  # ID-05 resend
    return session


@pytest.fixture
def history(db_session: Session, bank: MockBankAccountProvider) -> Session:
    return _history(db_session, bank)


@pytest.fixture
def owner_history(owner_session: Session, bank: MockBankAccountProvider) -> Session:
    """The same history as the schema owner: only the owner can drop a guard (S2)."""
    return _history(owner_session, bank)


def test_INV_1_to_INV_5_hold_after_processing(history: Session) -> None:
    assert len(auto_saves(history)) == 2
    assert violations(history) == []
    assert_user_invariants(history, USER)  # does not raise


def test_invariants_hold_for_user_with_no_rows(db_session: Session) -> None:
    assert violations(db_session, "nobody") == []


def test_INV_1_cached_balance_must_equal_ledger(history: Session) -> None:
    history.execute(
        update(UserBalance).where(UserBalance.user_id == USER).values(savings_balance=Decimal("1"))
    )
    assert violations(history) == ["INV-1"]
    with pytest.raises(InvariantViolationError) as exc:
        assert_user_invariants(history, USER)
    assert (exc.value.user_id, exc.value.violations) == (USER, ["INV-1"])
    assert USER not in str(exc.value)  # S12: the message is logged


def test_INV_1_ledger_row_without_balance_row(db_session: Session) -> None:
    db_session.add(webhook_event(event_id="evt_1", user_id=USER))
    db_session.flush()
    db_session.add(
        savings_tx(user_id=USER, source_event_id="evt_1", installment_id=_inst(db_session))
    )
    db_session.flush()
    assert violations(db_session) == ["INV-1"]


def test_INV_1_withdrawal_counts_against_ledger(history: Session) -> None:
    history.add(
        savings_tx(
            user_id=USER,
            type="withdrawal",
            source_vendor=None,
            source_event_id=None,
            client_request_id="move-1",
        )
    )
    history.flush()
    assert violations(history) == ["INV-1"]
    history.execute(
        update(UserBalance)
        .where(UserBalance.user_id == USER)
        .values(savings_balance=Decimal("50.00"))  # 80 + 10 - 40
    )
    assert violations(history) == []


def test_INV_2_negative_balance(owner_history: Session) -> None:
    owner_history.execute(
        text("ALTER TABLE user_balances DROP CONSTRAINT ck_user_balances_savings_balance_nonneg")
    )
    owner_history.add(
        savings_tx(
            user_id=USER,
            type="withdrawal",
            amount=Decimal("100.00"),
            source_vendor=None,
            source_event_id=None,
            client_request_id="move-1",
        )
    )
    owner_history.execute(
        update(UserBalance)
        .where(UserBalance.user_id == USER)
        .values(savings_balance=Decimal("-10.00"))
    )
    assert violations(owner_history) == ["INV-2"]


def test_INV_3_two_auto_saves_from_one_event(owner_history: Session) -> None:
    owner_history.execute(text("DROP INDEX uq_savings_transactions_auto_save_source_event"))
    owner_history.execute(text("DROP INDEX uq_savings_transactions_auto_save_installment_id"))
    [first] = auto_saves(owner_history, USER)[:1]
    owner_history.add(
        savings_tx(
            user_id=USER,
            amount=Decimal("10.00"),
            source_event_id=first.source_event_id,
            installment_id=first.installment_id,
        )
    )
    owner_history.execute(
        update(UserBalance)
        .where(UserBalance.user_id == USER)
        .values(savings_balance=Decimal("100.00"))
    )
    assert violations(owner_history) == ["INV-3"]


def _inst(session: Session, contract_id: str = "c_x", kind: str = "purchase") -> uuid.UUID:
    row = installment(user_id=USER, contract_id=contract_id, kind=kind)
    session.add(row)
    session.flush()
    return row.id


def _bad_auto_save(
    session: Session, *, event_type: str, kind: str, event_user: str = USER, saver: str = USER
) -> None:
    session.add(webhook_event(event_id="evt_bad", event_type=event_type, user_id=event_user))
    session.flush()
    session.add(
        savings_tx(
            user_id=saver,
            amount=Decimal("10.00"),
            source_event_id="evt_bad",
            installment_id=_inst(session, "c_bad", kind),
        )
    )
    session.add(UserBalance(user_id=saver, savings_balance=Decimal("10.00")))
    session.flush()


@pytest.mark.parametrize("event_type", ["cash_withdrawal_created", "cash_loan_created"])
def test_INV_5_auto_save_from_cash_event(db_session: Session, event_type: str) -> None:
    _bad_auto_save(db_session, event_type=event_type, kind="purchase")
    assert violations(db_session) == ["INV-5"]


@pytest.mark.parametrize("kind", ["cash_withdrawal", "cash_loan"])
def test_INV_5_auto_save_for_cash_installment(db_session: Session, kind: str) -> None:
    _bad_auto_save(db_session, event_type="installment_created", kind=kind)
    assert violations(db_session) == ["INV-5"]


def test_L51_auto_save_filed_under_another_user(db_session: Session) -> None:
    _bad_auto_save(db_session, event_type="installment_created", kind="purchase", saver="user_b")
    # Found from both sides: the event's user and the user who got the saving.
    assert violations(db_session, USER) == ["L51"]
    assert violations(db_session, "user_b") == ["L51"]


def _manual_auto_save(
    session: Session,
    request_id: str,
    *,
    kind: str = "purchase",
    owner: str = USER,
    saver: str = USER,
    amount: str = "10.00",
) -> None:
    """A manual installment (L62) and an auto_save for it with no source event."""
    row = manual_installment(user_id=owner, client_request_id=request_id, kind=kind)
    session.add(row)
    session.flush()
    session.add(
        savings_tx(
            user_id=saver,
            amount=Decimal(amount),
            source_vendor=None,
            source_event_id=None,
            installment_id=row.id,
        )
    )
    session.flush()


def _set_balance(session: Session, user: str, amount: str) -> None:
    session.add(UserBalance(user_id=user, savings_balance=Decimal(amount)))
    session.flush()


def test_INV_3_manual_auto_saves_without_event_are_not_repeats(db_session: Session) -> None:
    # Two manual savings both have a NULL source pair. GROUP BY puts NULLs in one
    # group, so the per-event check must leave them out.
    _manual_auto_save(db_session, "req-1")
    _manual_auto_save(db_session, "req-2", amount="20.00")
    _set_balance(db_session, USER, "30.00")
    assert violations(db_session) == []


def test_INV_3_two_manual_auto_saves_for_one_installment(owner_session: Session) -> None:
    owner_session.execute(text("DROP INDEX uq_savings_transactions_auto_save_installment_id"))
    _manual_auto_save(owner_session, "req-1")
    installment_id = owner_session.execute(
        text("SELECT installment_id FROM savings_transactions")
    ).scalar_one()
    owner_session.add(
        savings_tx(
            user_id=USER,
            amount=Decimal("10.00"),
            source_vendor=None,
            source_event_id=None,
            installment_id=installment_id,
        )
    )
    _set_balance(owner_session, USER, "20.00")
    assert violations(owner_session) == ["INV-3"]


@pytest.mark.parametrize("kind", ["cash_withdrawal", "cash_loan"])
def test_INV_5_manual_auto_save_for_cash_installment(db_session: Session, kind: str) -> None:
    _manual_auto_save(db_session, "req-1", kind=kind)
    _set_balance(db_session, USER, "10.00")
    assert violations(db_session) == ["INV-5"]


def test_L51_manual_auto_save_filed_under_another_user(db_session: Session) -> None:
    _manual_auto_save(db_session, "req-1", saver="user_b")
    _set_balance(db_session, "user_b", "10.00")
    # No event to compare with: the installment's owner is what counts.
    assert violations(db_session, USER) == ["L51"]
    assert violations(db_session, "user_b") == ["L51"]


def test_RS_02_violation_rolls_back_whole_event_and_logs(
    db_session: Session,
    bank: MockBankAccountProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A simulated bug: the balance is credited one baht too much."""
    opt_in(db_session)
    real_credit = savings.adjust_balance
    monkeypatch.setattr(
        savings,
        "adjust_balance",
        lambda session, user_id, amount: real_credit(session, user_id, amount + Decimal(1)),
    )

    with caplog.at_level(logging.ERROR), pytest.raises(InvariantViolationError) as exc:
        run(db_session, created("evt_1", "c_1", "800.00"), bank)

    assert exc.value.violations == ["INV-1"]
    for model in (
        WebhookEvent,
        Installment,
        SavingsTransaction,
        UserBalance,
        AuditLog,
        UserSettings,
    ):
        assert count(db_session, model) == 0, model.__name__
    assert bank.get_balance(USER) == Decimal("10000.00")  # no money moved
    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert "reconcile failed" in record.getMessage()
    assert "INV-1" in record.getMessage()
    assert f"vendor={VENDOR} event_id=evt_1" in record.getMessage()
    assert USER not in record.getMessage()  # S12: no user ref in the server log


def test_INV_6_paid_more_than_owed(owner_history: Session) -> None:
    owner_history.execute(
        text("ALTER TABLE installments DROP CONSTRAINT ck_installments_paid_le_total")
    )
    owner_history.execute(
        update(Installment)
        .where(Installment.user_id == USER)
        .values(
            paid_amount=Installment.principal
            + Installment.fee_total
            + Installment.late_fees_accrued
            + Decimal("0.01")
        )
    )
    assert violations(owner_history) == ["INV-6"]


def test_INV_6_paid_exactly_what_is_owed_holds(history: Session) -> None:
    history.execute(
        update(Installment)
        .where(Installment.user_id == USER)
        .values(late_fees_accrued=Decimal("150.00"))
        .values(paid_amount=Installment.principal + Installment.fee_total + Decimal("150.00"))
    )
    assert violations(history) == []
