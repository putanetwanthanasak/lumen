"""Each test proves the database itself rejects one bad row (defense in depth).

``assert_rejected`` checks the exact constraint name, so a test cannot pass
because some unrelated constraint (e.g. NOT NULL) fired instead.
"""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from tests.db.factories import (
    add_auto_save_parents,
    add_event,
    add_installment,
    installment,
    notification,
    savings_tx,
    user_balance,
    user_settings,
    webhook_event,
)

pytestmark = pytest.mark.db


def assert_rejected(session: Session, row: Base, constraint: str) -> None:
    session.add(row)
    with pytest.raises(IntegrityError) as exc:
        session.flush()
    assert exc.value.orig is not None
    assert exc.value.orig.diag.constraint_name == constraint  # type: ignore[attr-defined]
    session.rollback()


def assert_accepted(session: Session, row: Base) -> None:
    session.add(row)
    session.flush()


# --- Invariants (05 section 3) ---------------------------------------------------


def test_INV_2_savings_balance_never_negative(db_session: Session) -> None:
    assert_accepted(db_session, user_balance(user_id="u-zero", savings_balance=Decimal("0.00")))
    assert_rejected(
        db_session,
        user_balance(savings_balance=Decimal("-0.01")),
        "ck_user_balances_savings_balance_nonneg",
    )


def test_INV_3_auto_save_unique_per_event(db_session: Session) -> None:
    first = add_auto_save_parents(db_session, "evt-1", "c-1")
    other = add_installment(db_session, "c-2")  # different installment: only the event repeats
    assert_accepted(db_session, savings_tx(source_event_id="evt-1", installment_id=first))
    assert_rejected(
        db_session,
        savings_tx(source_event_id="evt-1", installment_id=other, amount=Decimal("10.00")),
        "uq_savings_transactions_auto_save_source_event_id",
    )


def test_INV_3_auto_save_requires_source_event(db_session: Session) -> None:
    inst = add_installment(db_session)
    assert_rejected(
        db_session,
        savings_tx(source_event_id=None, installment_id=inst),
        "ck_savings_transactions_auto_save_has_source_event",
    )


def test_INV_3_withdrawals_are_not_limited_per_event(db_session: Session) -> None:
    # The partial index covers auto_save only; withdrawals carry no event.
    assert_accepted(db_session, savings_tx(type="withdrawal", source_event_id=None))
    assert_accepted(db_session, savings_tx(type="withdrawal", source_event_id=None))


def test_auto_save_source_event_must_exist(db_session: Session) -> None:
    inst = add_installment(db_session)
    assert_rejected(
        db_session,
        savings_tx(source_event_id="evt-missing", installment_id=inst),
        "fk_savings_transactions_source_event_id_webhook_events",
    )


def test_INV_6_paid_amount_le_principal_plus_fee(db_session: Session) -> None:
    total = {"principal": Decimal("2000.00"), "fee_total": Decimal("100.00")}
    assert_accepted(
        db_session, installment(contract_id="c-ok", paid_amount=Decimal("2100.00"), **total)
    )
    assert_rejected(
        db_session,
        installment(paid_amount=Decimal("2100.01"), **total),
        "ck_installments_paid_le_total",
    )


# --- Idempotency keys (05 section 4.4) ---------------------------------------------


def test_ID_01_webhook_event_id_is_primary_key(db_session: Session) -> None:
    add_event(db_session, "evt-dup")
    assert_rejected(db_session, webhook_event(event_id="evt-dup"), "pk_webhook_events")


def test_ID_05_unique_vendor_contract(db_session: Session) -> None:
    assert_accepted(db_session, installment(vendor="shopdemo", contract_id="c-9"))
    assert_accepted(db_session, installment(vendor="othervendor", contract_id="c-9"))
    assert_rejected(
        db_session,
        installment(vendor="shopdemo", contract_id="c-9"),
        "uq_installments_vendor_contract_id",
    )


# --- Ranges ------------------------------------------------------------------------


@pytest.mark.parametrize("rate", ["0.03", "0.05", "0.10"])
def test_save_rate_accepts_bounds(db_session: Session, rate: str) -> None:
    assert_accepted(db_session, user_settings(save_rate=Decimal(rate)))


@pytest.mark.parametrize("rate", ["0.029999", "0.100001", "0.00"])
def test_save_rate_rejects_out_of_range(db_session: Session, rate: str) -> None:
    assert_rejected(
        db_session, user_settings(save_rate=Decimal(rate)), "ck_user_settings_save_rate_range"
    )


def test_per_item_cap_at_least_min_saving(db_session: Session) -> None:
    assert_accepted(db_session, user_settings(user_id="u-cap", per_item_cap=Decimal("10.00")))
    assert_rejected(
        db_session,
        user_settings(per_item_cap=Decimal("9.99")),
        "ck_user_settings_per_item_cap_ge_min_saving",
    )


def test_user_settings_defaults(db_session: Session) -> None:
    row = user_settings()
    assert_accepted(db_session, row)
    db_session.refresh(row)
    assert row.auto_save_enabled is False
    assert row.consent_at is None
    assert row.save_rate == Decimal("0.05")
    assert row.per_item_cap == Decimal("100.00")
    assert row.monthly_installment_cap is None


def test_installment_defaults(db_session: Session) -> None:
    row = installment(fee_total=None, paid_amount=None)
    del row.fee_total, row.paid_amount  # let the server defaults apply
    assert_accepted(db_session, row)
    db_session.refresh(row)
    assert row.status == "active"
    assert row.overdue_days == 0
    assert row.fee_total == Decimal("0.00")
    assert row.paid_amount == Decimal("0.00")


# One bad value per CHECK constraint: (factory, overrides, constraint name).
CHECK_CASES: list[tuple[Any, dict[str, Any], str]] = [
    (installment, {"kind": "credit_card"}, "ck_installments_kind_valid"),
    (installment, {"status": "deleted"}, "ck_installments_status_valid"),
    (installment, {"principal": Decimal("0.00")}, "ck_installments_principal_positive"),
    (installment, {"months": 0}, "ck_installments_months_positive"),
    (installment, {"monthly_amount": Decimal("-1.00")}, "ck_installments_monthly_amount_nonneg"),
    (installment, {"fee_total": Decimal("-1.00")}, "ck_installments_fee_total_nonneg"),
    (installment, {"paid_amount": Decimal("-0.01")}, "ck_installments_paid_amount_nonneg"),
    (installment, {"min_payment": Decimal("-1.00")}, "ck_installments_min_payment_nonneg"),
    (installment, {"late_fee_per_period": Decimal("-1.00")}, "ck_installments_late_fee_nonneg"),
    (installment, {"monthly_rate": Decimal("-0.000001")}, "ck_installments_monthly_rate_nonneg"),
    (installment, {"overdue_days": -1}, "ck_installments_overdue_days_nonneg"),
    (webhook_event, {"event_type": "installment_deleted"}, "ck_webhook_events_event_type_valid"),
    (webhook_event, {"status": "duplicate"}, "ck_webhook_events_status_valid"),
    (savings_tx, {"type": "refund"}, "ck_savings_transactions_type_valid"),
    (savings_tx, {"amount": Decimal("0.00")}, "ck_savings_transactions_amount_positive"),
    (user_balance, {"version": -1}, "ck_user_balances_version_nonneg"),
    (
        user_settings,
        {"monthly_installment_cap": Decimal("-1.00")},
        "ck_user_settings_monthly_cap_nonneg",
    ),
    (notification, {"kind": "promo"}, "ck_notifications_kind_valid"),
    (notification, {"delivery_status": "sent"}, "ck_notifications_delivery_status_valid"),
    (notification, {"user_response": "maybe"}, "ck_notifications_user_response_valid"),
    (notification, {"push_attempts": -1}, "ck_notifications_push_attempts_nonneg"),
]


@pytest.mark.parametrize(
    ("factory", "overrides", "constraint"), CHECK_CASES, ids=[c[2] for c in CHECK_CASES]
)
def test_check_constraint_rejects_bad_value(
    db_session: Session, factory: Any, overrides: dict[str, Any], constraint: str
) -> None:
    if factory is savings_tx:
        overrides = {"installment_id": add_auto_save_parents(db_session)} | overrides
    assert_rejected(db_session, factory(**overrides), constraint)


@pytest.mark.parametrize("kind", ["purchase", "cash_withdrawal", "cash_loan"])
def test_installment_accepts_every_kind(db_session: Session, kind: str) -> None:
    assert_accepted(db_session, installment(kind=kind))


@pytest.mark.parametrize("kind", ["new_debt", "cash_withdrawal", "cash_loan", "over_cap"])
def test_notification_accepts_every_kind(db_session: Session, kind: str) -> None:
    assert_accepted(db_session, notification(kind=kind))
