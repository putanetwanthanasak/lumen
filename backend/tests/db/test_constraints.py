"""Each test proves the database itself rejects one bad row (defense in depth).

``assert_rejected`` checks the exact constraint name, so a test cannot pass
because some unrelated constraint (e.g. NOT NULL) fired instead.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import PaydayRun
from tests.db.factories import (
    USER,
    VENDOR,
    add_auto_save_parents,
    add_event,
    add_installment,
    audit_log,
    installment,
    manual_installment,
    notification,
    profile,
    savings_tx,
    user_balance,
    user_settings,
    webhook_event,
)

OTHER_VENDOR = "othervendor"

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
        "uq_savings_transactions_auto_save_source_event",
    )


def test_INV_3_same_event_id_under_two_vendors_saves_once_each(db_session: Session) -> None:
    # L47: INV-3 is per (vendor, event_id); another vendor's evt-1 is a different event.
    ours = add_auto_save_parents(db_session, "evt-1", "c-1")
    theirs = add_auto_save_parents(db_session, "evt-1", "c-1", vendor=OTHER_VENDOR)
    assert_accepted(db_session, savings_tx(source_event_id="evt-1", installment_id=ours))
    assert_accepted(
        db_session,
        savings_tx(source_vendor=OTHER_VENDOR, source_event_id="evt-1", installment_id=theirs),
    )


def test_INV_3_manual_auto_save_needs_no_source_event(db_session: Session) -> None:
    # L62: a manual entry has no webhook event. One auto_save per installment is
    # still the DB's rule, through the per-installment partial UNIQUE index.
    row = manual_installment()
    assert_accepted(db_session, row)
    no_event = {"source_vendor": None, "source_event_id": None, "installment_id": row.id}
    assert_accepted(db_session, savings_tx(**no_event))
    assert_rejected(
        db_session,
        savings_tx(**no_event, amount=Decimal("1.00")),
        "uq_savings_transactions_auto_save_installment_id",
    )


@pytest.mark.parametrize(("vendor", "event_id"), [(VENDOR, None), (None, "evt-1")])
def test_source_event_pair_must_be_complete(
    db_session: Session, vendor: str | None, event_id: str | None
) -> None:
    # A composite FK with one NULL column is not checked at all (MATCH SIMPLE).
    add_event(db_session)
    assert_rejected(
        db_session,
        savings_tx(
            type="withdrawal",
            source_vendor=vendor,
            source_event_id=event_id,
            client_request_id="move-1",
        ),
        "ck_savings_transactions_source_event_pair_complete",
    )


def test_INV_3_withdrawals_are_not_limited_per_event(db_session: Session) -> None:
    # The partial index covers auto_save only; withdrawals carry no event.
    for n in range(2):
        assert_accepted(
            db_session,
            savings_tx(
                type="withdrawal",
                source_vendor=None,
                source_event_id=None,
                client_request_id=f"move-{n}",
            ),
        )


@pytest.mark.parametrize(("vendor", "event_id"), [(VENDOR, "evt-missing"), (OTHER_VENDOR, "evt-1")])
def test_auto_save_source_event_must_exist(db_session: Session, vendor: str, event_id: str) -> None:
    # (othervendor, evt-1) does not exist even though (shopdemo, evt-1) does.
    inst = add_auto_save_parents(db_session)
    assert_rejected(
        db_session,
        savings_tx(source_vendor=vendor, source_event_id=event_id, installment_id=inst),
        "fk_savings_transactions_source_vendor_webhook_events",
    )


OWED = {
    "principal": Decimal("2000.00"),
    "fee_total": Decimal("100.00"),
    "late_fees_accrued": Decimal("50.00"),
}


def test_INV_6_paid_amount_le_principal_plus_fee_plus_late_fees(db_session: Session) -> None:
    assert_accepted(
        db_session, installment(contract_id="c-ok", paid_amount=Decimal("2150.00"), **OWED)
    )
    assert_rejected(
        db_session,
        installment(paid_amount=Decimal("2150.01"), **OWED),
        "ck_installments_paid_le_total",
    )


def test_INV_6_payment_may_cover_late_fees(db_session: Session) -> None:
    # 2,120.00 is above principal + fee (2,100.00): only valid because late fees are owed.
    paid = Decimal("2120.00")
    assert_accepted(db_session, installment(contract_id="c-late", paid_amount=paid, **OWED))
    assert_rejected(
        db_session,
        installment(paid_amount=paid, **(OWED | {"late_fees_accrued": Decimal("0.00")})),
        "ck_installments_paid_le_total",
    )


def test_INV_6_without_late_fees_is_principal_plus_fee(db_session: Session) -> None:
    no_late = OWED | {"late_fees_accrued": Decimal("0.00")}
    assert_accepted(
        db_session, installment(contract_id="c-ok", paid_amount=Decimal("2100.00"), **no_late)
    )
    assert_rejected(
        db_session,
        installment(paid_amount=Decimal("2100.01"), **no_late),
        "ck_installments_paid_le_total",
    )


def test_L41_fields_accept_zero(db_session: Session) -> None:
    # L41 fields are required (no default) but 0 is valid, e.g. 0% BNPL with no late fee.
    row = installment(
        min_payment=Decimal("0.00"),
        late_fee_per_period=Decimal("0.00"),
        monthly_rate=Decimal("0.000000"),
    )
    assert_accepted(db_session, row)
    db_session.refresh(row)
    assert row.min_payment == Decimal("0.00")
    assert row.late_fee_per_period == Decimal("0.00")
    assert row.monthly_rate == Decimal("0.000000")


# --- Idempotency keys (05 section 4.4) ---------------------------------------------


def test_ID_01_webhook_event_key_is_vendor_and_event_id(db_session: Session) -> None:
    add_event(db_session, "evt-dup")
    assert_rejected(db_session, webhook_event(event_id="evt-dup"), "pk_webhook_events")


def test_L47_two_vendors_can_reuse_event_id(db_session: Session) -> None:
    add_event(db_session, "evt-1", vendor=VENDOR)
    add_event(db_session, "evt-1", vendor=OTHER_VENDOR)
    assert_rejected(
        db_session, webhook_event(event_id="evt-1", vendor=OTHER_VENDOR), "pk_webhook_events"
    )


def test_ID_05_unique_vendor_contract(db_session: Session) -> None:
    assert_accepted(db_session, installment(vendor="shopdemo", contract_id="c-9"))
    assert_accepted(db_session, installment(vendor="othervendor", contract_id="c-9"))
    assert_rejected(
        db_session,
        installment(vendor="shopdemo", contract_id="c-9"),
        "uq_installments_vendor_contract_id",
    )


# --- Ranges ------------------------------------------------------------------------


def test_ST_13_user_settings_defaults(db_session: Session) -> None:
    # A bare row is the shape from before L63: no profile, no rule, nothing saved.
    row = user_settings()
    assert_accepted(db_session, row)
    db_session.refresh(row)
    assert row.auto_save_enabled is False
    assert row.leftover_saving_enabled is False
    assert row.consent_at is None
    assert (row.income, row.payday, row.monthly_installment_budget, row.saving_mode) == (
        None,
        None,
        None,
        None,
    )


@pytest.mark.parametrize("rule", [{"percent": 1}, {"percent": 100}, {"fixed": "0.01"}])
def test_ST_13_user_settings_accept_each_mode(db_session: Session, rule: dict[str, Any]) -> None:
    assert_accepted(db_session, user_settings(**profile(**rule)))


# L63 at the DB layer: exactly the chosen mode's value, so both can never be active.
ST_13_CASES: list[tuple[dict[str, Any], str]] = [
    ({"saving_fixed_amount": Decimal("5.00")}, "ck_user_settings_saving_fixed_amount_with_mode"),
    ({"saving_percent": None}, "ck_user_settings_saving_percent_with_mode"),
    # Both values set: whichever mode is chosen, the other one's value is refused.
    (
        {"saving_mode": "fixed", "saving_fixed_amount": Decimal("5.00")},
        "ck_user_settings_saving_percent_with_mode",
    ),
    ({"saving_mode": "both"}, "ck_user_settings_saving_mode_valid"),
    ({"saving_percent": 0}, "ck_user_settings_saving_percent_range"),
    ({"saving_percent": 101}, "ck_user_settings_saving_percent_range"),
    ({"income": None}, "ck_user_settings_profile_all_or_none"),
    ({"payday": None}, "ck_user_settings_profile_all_or_none"),
]


@pytest.mark.parametrize(
    ("overrides", "constraint"), ST_13_CASES, ids=[str(c[0]) for c in ST_13_CASES]
)
def test_ST_13_user_settings_never_hold_both_modes(
    db_session: Session, overrides: dict[str, Any], constraint: str
) -> None:
    assert_rejected(db_session, user_settings(**(profile() | overrides)), constraint)


def test_ST_13_fixed_mode_without_amount_rejected(db_session: Session) -> None:
    row = user_settings(**(profile(fixed="5.00") | {"saving_fixed_amount": None}))
    assert_rejected(db_session, row, "ck_user_settings_saving_fixed_amount_with_mode")


def test_ST_13_rule_without_profile_rejected(db_session: Session) -> None:
    # A rule alone (no income, payday, budget) is not a valid half-filled row.
    row = user_settings(saving_mode="percent", saving_percent=10)
    assert_rejected(db_session, row, "ck_user_settings_profile_all_or_none")


def test_installment_defaults(db_session: Session) -> None:
    row = installment(fee_total=None, paid_amount=None, late_fees_accrued=None)
    del row.fee_total, row.paid_amount, row.late_fees_accrued  # let the server defaults apply
    assert_accepted(db_session, row)
    db_session.refresh(row)
    assert row.status == "active"
    assert row.overdue_days == 0
    assert row.fee_total == Decimal("0.00")
    assert row.paid_amount == Decimal("0.00")
    assert row.late_fees_accrued == Decimal("0.00")


# One bad value per CHECK constraint: (factory, overrides, constraint name).
CHECK_CASES: list[tuple[Any, dict[str, Any], str]] = [
    (installment, {"kind": "credit_card"}, "ck_installments_kind_valid"),
    (installment, {"status": "deleted"}, "ck_installments_status_valid"),
    (installment, {"principal": Decimal("0.00")}, "ck_installments_principal_positive"),
    (installment, {"months": 0}, "ck_installments_months_positive"),
    (installment, {"monthly_amount": Decimal("-1.00")}, "ck_installments_monthly_amount_nonneg"),
    (installment, {"fee_total": Decimal("-1.00")}, "ck_installments_fee_total_nonneg"),
    (installment, {"paid_amount": Decimal("-0.01")}, "ck_installments_paid_amount_nonneg"),
    (
        installment,
        {"late_fees_accrued": Decimal("-0.01")},
        "ck_installments_late_fees_accrued_nonneg",
    ),
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
        profile() | {"monthly_installment_budget": Decimal("-1.00")},
        "ck_user_settings_monthly_budget_nonneg",
    ),
    (user_settings, profile() | {"income": Decimal("0.00")}, "ck_user_settings_income_positive"),
    (user_settings, profile() | {"payday": 0}, "ck_user_settings_payday_day_of_month"),
    (user_settings, profile() | {"payday": 32}, "ck_user_settings_payday_day_of_month"),
    (
        user_settings,
        profile(fixed="5.00") | {"saving_fixed_amount": Decimal("0.00")},
        "ck_user_settings_saving_fixed_amount_positive",
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
    if factory is notification:
        overrides = {"installment_id": add_installment(db_session)} | overrides
    assert_rejected(db_session, factory(**overrides), constraint)


@pytest.mark.parametrize("kind", ["purchase", "cash_withdrawal", "cash_loan"])
def test_installment_accepts_every_kind(db_session: Session, kind: str) -> None:
    assert_accepted(db_session, installment(kind=kind))


@pytest.mark.parametrize("kind", ["new_debt", "cash_withdrawal", "cash_loan", "over_cap"])
def test_notification_accepts_every_kind(db_session: Session, kind: str) -> None:
    assert_accepted(db_session, notification(kind=kind, installment_id=add_installment(db_session)))


@pytest.mark.parametrize("kind", ["new_debt", "cash_withdrawal", "cash_loan"])
def test_NT_04_one_new_debt_notification_per_installment(db_session: Session, kind: str) -> None:
    """The DB guard behind 5e: a second new-debt alert for one installment is refused,
    whichever new-debt kind either row has."""
    installment_id = add_installment(db_session)
    assert_accepted(db_session, notification(installment_id=installment_id))
    assert_rejected(
        db_session,
        notification(installment_id=installment_id, kind=kind),
        "uq_notifications_new_debt_installment_id",
    )


@pytest.mark.parametrize("kind", ["new_debt", "cash_withdrawal", "cash_loan"])
def test_NT_04_new_debt_notification_needs_an_installment(db_session: Session, kind: str) -> None:
    # Without it, rows with a NULL installment_id would never collide in the index above.
    assert_rejected(
        db_session, notification(kind=kind), "ck_notifications_new_debt_has_installment"
    )


def test_over_cap_notifications_are_not_limited_per_installment(db_session: Session) -> None:
    assert_accepted(db_session, notification(kind="over_cap"))
    assert_accepted(db_session, notification(kind="over_cap"))


# --- L42 "Not me" -----------------------------------------------------------------

DISPUTED_AT = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


REPORTED = {"disputed_at": DISPUTED_AT, "dispute_signal_status": "pending"}


def test_L42_disputed_installment_needs_disputed_at(db_session: Session) -> None:
    assert_rejected(
        db_session,
        installment(status="disputed"),
        "ck_installments_disputed_has_disputed_at",
    )
    assert_accepted(db_session, installment(status="disputed", **REPORTED))


@pytest.mark.parametrize("status", ["cancelled", "active", "paid_off"])
def test_L59_3_disputed_at_may_outlive_the_disputed_status(
    db_session: Session, status: str
) -> None:
    # Cancelled after the report keeps disputed_at (L59 3), and so does any later status.
    assert_accepted(db_session, installment(status=status, **REPORTED))


@pytest.mark.parametrize(
    "fields",
    [
        {"disputed_at": DISPUTED_AT},  # a report without a signal status
        {"dispute_signal_status": "sent"},  # a signal status without a report
    ],
)
def test_L60_2_signal_status_exactly_when_reported(
    db_session: Session, fields: dict[str, object]
) -> None:
    assert_rejected(
        db_session,
        installment(**fields),
        "ck_installments_dispute_signal_status_with_report",
    )


def test_L60_2_signal_status_values(db_session: Session) -> None:
    for value in ("pending", "sent", "failed"):
        assert_accepted(
            db_session,
            installment(
                contract_id=f"c-{value}", disputed_at=DISPUTED_AT, dispute_signal_status=value
            ),
        )
    assert_rejected(
        db_session,
        installment(disputed_at=DISPUTED_AT, dispute_signal_status="delivered"),
        "ck_installments_dispute_signal_status_valid",
    )


def test_L42_one_dispute_audit_row_per_installment(db_session: Session) -> None:
    dispute = {"action": "installment_disputed", "actor": "user", "ref_id": "inst-1"}
    assert_accepted(db_session, audit_log(**dispute))
    assert_accepted(db_session, audit_log(**(dispute | {"ref_id": "inst-2"})))
    assert_accepted(db_session, audit_log(action="webhook_event_applied", ref_id="inst-1"))
    assert_rejected(db_session, audit_log(**dispute), "uq_audit_log_installment_disputed")


# --- L62 manual entry -------------------------------------------------------------


def test_MI_10_manual_row_with_unknown_debt_data_accepted(db_session: Session) -> None:
    assert_accepted(db_session, manual_installment())


def test_MI_10_same_request_id_twice_for_one_user_rejected(db_session: Session) -> None:
    # The idempotency key (L62): (user, client_request_id).
    assert_accepted(db_session, manual_installment())
    assert_rejected(db_session, manual_installment(), "uq_installments_user_client_request_id")


def test_MI_10_same_request_id_for_two_users_accepted(db_session: Session) -> None:
    assert_accepted(db_session, manual_installment(user_id="user-1"))
    assert_accepted(db_session, manual_installment(user_id="user-2"))


@pytest.mark.parametrize(
    ("row", "constraint"),
    [
        (
            lambda: manual_installment(client_request_id=None),
            "ck_installments_manual_has_client_request_id",
        ),
        (
            lambda: installment(client_request_id="req-1"),
            "ck_installments_manual_has_client_request_id",
        ),
        (lambda: installment(min_payment=None), "ck_installments_platform_debt_data_complete"),
        (
            lambda: installment(late_fee_per_period=None),
            "ck_installments_platform_debt_data_complete",
        ),
        (lambda: installment(monthly_rate=None), "ck_installments_platform_debt_data_complete"),
    ],
    ids=["manual-without-id", "platform-with-id", "min_payment", "late_fee", "monthly_rate"],
)
def test_MI_10_manual_and_platform_rows_kept_apart(
    db_session: Session, row: Any, constraint: str
) -> None:
    assert_rejected(db_session, row(), constraint)


# --- BF-10: buffer withdrawals (L66, Session 13) ---------------------------------------


def withdrawal(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "type": "withdrawal",
        "source_vendor": None,
        "source_event_id": None,
        "client_request_id": "move-1",
    }
    return savings_tx(**(fields | overrides))


def test_BF_10_withdrawal_needs_a_client_request_id(db_session: Session) -> None:
    assert_rejected(
        db_session,
        withdrawal(client_request_id=None),
        "ck_savings_transactions_withdrawal_has_client_request_id",
    )


def test_BF_10_only_a_withdrawal_carries_a_client_request_id(db_session: Session) -> None:
    inst = add_auto_save_parents(db_session)
    assert_rejected(
        db_session,
        savings_tx(installment_id=inst, client_request_id="move-1"),
        "ck_savings_transactions_withdrawal_has_client_request_id",
    )


def test_BF_10_same_request_id_twice_for_one_user_rejected(db_session: Session) -> None:
    assert_accepted(db_session, withdrawal())
    assert_accepted(db_session, withdrawal(user_id="user-2"))  # per user
    assert_rejected(db_session, withdrawal(), "uq_savings_transactions_user_client_request_id")


# --- PD-07, LO-08: payday runs and leftover saving (L67, Session 13) -------------------


def payday_run(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "user_id": USER,
        "month": date(2026, 11, 1),
        "month_total": Decimal("7200.00"),
        "budget": Decimal("9000.00"),
        "outcome": "leftover_saved",
        "amount": Decimal("1800.00"),
        "buffer_balance": Decimal("1800.00"),
    }
    return PaydayRun(**(fields | overrides))


def test_PD_07_one_run_per_user_per_month(db_session: Session) -> None:
    assert_accepted(db_session, payday_run())
    assert_accepted(db_session, payday_run(month=date(2026, 12, 1)))
    assert_accepted(db_session, payday_run(user_id="user-2"))
    db_session.add(payday_run())
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert exc.value.orig.diag.constraint_name == "pk_payday_runs"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"month": date(2026, 11, 2)}, "ck_payday_runs_month_first_day"),
        # amount 0.00, so only the outcome CHECK is broken, not amount_with_outcome too
        ({"outcome": "maybe", "amount": Decimal("0.00")}, "ck_payday_runs_outcome_valid"),
        ({"month_total": Decimal("-0.01")}, "ck_payday_runs_month_total_nonneg"),
        ({"budget": Decimal("-0.01")}, "ck_payday_runs_budget_nonneg"),
        ({"buffer_balance": Decimal("-0.01")}, "ck_payday_runs_buffer_balance_nonneg"),
        ({"amount": Decimal("0.00")}, "ck_payday_runs_amount_with_outcome"),
        ({"outcome": "safety_net"}, "ck_payday_runs_amount_with_outcome"),
        (
            {"outcome": "over_budget", "amount": Decimal("0.00")},
            "ck_payday_runs_amount_with_outcome",
        ),
        ({"outcome": "no_leftover", "amount": Decimal("-1.00")}, "ck_payday_runs_amount_nonneg"),
    ],
)
def test_PD_07_payday_run_checks(
    db_session: Session, overrides: dict[str, Any], constraint: str
) -> None:
    assert_rejected(db_session, payday_run(**overrides), constraint)


def leftover_save(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "type": "leftover_save",
        "amount": Decimal("1800.00"),
        "source_vendor": None,
        "source_event_id": None,
        "payday_month": date(2026, 11, 1),
    }
    return savings_tx(**(fields | overrides))


def test_LO_08_leftover_save_needs_its_payday_month(db_session: Session) -> None:
    assert_rejected(
        db_session,
        leftover_save(payday_month=None),
        "ck_savings_transactions_leftover_save_has_payday_month",
    )


def test_LO_08_only_a_leftover_save_carries_a_payday_month(db_session: Session) -> None:
    assert_rejected(
        db_session,
        withdrawal(payday_month=date(2026, 11, 1)),
        "ck_savings_transactions_leftover_save_has_payday_month",
    )


def test_LO_08_one_leftover_save_per_user_per_month(db_session: Session) -> None:
    assert_accepted(db_session, leftover_save())
    assert_accepted(db_session, leftover_save(payday_month=date(2026, 12, 1)))
    assert_accepted(db_session, leftover_save(user_id="user-2"))
    assert_rejected(db_session, leftover_save(), "uq_savings_transactions_leftover_save_month")
