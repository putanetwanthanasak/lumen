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
from tests.db.factories import installment, savings_tx, webhook_event
from tests.processing.conftest import USER, VENDOR, auto_saves, count, created, opt_in, run

pytestmark = pytest.mark.db


def violations(session: Session, user: str = USER) -> list[str]:
    return reconcile.check_user_invariants(session, user)


@pytest.fixture
def history(db_session: Session, bank: MockBankAccountProvider) -> Session:
    """Purchases, cash events and an ID-05 resend for one user, all through the processor."""
    opt_in(db_session)
    run(db_session, created("evt_1", "c_1", "800.00"), bank)
    run(db_session, created("evt_2", "c_2", "50.00"), bank)
    run(db_session, created("evt_3", "c_3", "15000.00", event_type="cash_withdrawal_created"), bank)
    run(db_session, created("evt_4", "c_4", "9000.00", event_type="cash_loan_created"), bank)
    run(db_session, created("evt_5", "c_1", "800.00"), bank)  # ID-05 resend
    return db_session


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
        savings_tx(user_id=USER, type="withdrawal", source_vendor=None, source_event_id=None)
    )
    history.flush()
    assert violations(history) == ["INV-1"]
    history.execute(
        update(UserBalance)
        .where(UserBalance.user_id == USER)
        .values(savings_balance=Decimal("50.00"))  # 80 + 10 - 40
    )
    assert violations(history) == []


def test_INV_2_negative_balance(history: Session) -> None:
    history.execute(
        text("ALTER TABLE user_balances DROP CONSTRAINT ck_user_balances_savings_balance_nonneg")
    )
    history.add(
        savings_tx(
            user_id=USER,
            type="withdrawal",
            amount=Decimal("100.00"),
            source_vendor=None,
            source_event_id=None,
        )
    )
    history.execute(
        update(UserBalance)
        .where(UserBalance.user_id == USER)
        .values(savings_balance=Decimal("-10.00"))
    )
    assert violations(history) == ["INV-2"]


def test_INV_3_two_auto_saves_from_one_event(history: Session) -> None:
    history.execute(text("DROP INDEX uq_savings_transactions_auto_save_source_event"))
    history.execute(text("DROP INDEX uq_savings_transactions_auto_save_installment_id"))
    [first] = auto_saves(history, USER)[:1]
    history.add(
        savings_tx(
            user_id=USER,
            amount=Decimal("10.00"),
            source_event_id=first.source_event_id,
            installment_id=first.installment_id,
        )
    )
    history.execute(
        update(UserBalance)
        .where(UserBalance.user_id == USER)
        .values(savings_balance=Decimal("100.00"))
    )
    assert violations(history) == ["INV-3"]


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


def test_RS_02_violation_rolls_back_whole_event_and_logs(
    db_session: Session,
    bank: MockBankAccountProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A simulated bug: the balance is credited one baht too much."""
    opt_in(db_session)
    real_credit = savings._credit
    monkeypatch.setattr(
        savings,
        "_credit",
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
