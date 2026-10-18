"""Payment, overdue and cancel (04 section 6 step 5, 05 section 4.5 OR-01..OR-05),
L48 / INV-6, L55 (cumulative late fees) and INV-7 (cancel leaves savings alone).

Every test ends with reconcile clean for the user.
"""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger.reconcile import check_user_invariants
from app.models import AuditLog, Installment, WebhookEvent
from app.providers.mock_bank import DEFAULT_OPENING_BALANCE, MockBankAccountProvider
from app.webhooks.processor import Outcome
from tests.processing.conftest import USER, auto_saves, balance, created, opt_in, run
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db

CONTRACT = "c_1"


def event(event_type: str, event_id: str, *, hour: int = 10, **fields: Any) -> dict[str, Any]:
    """A payment, overdue or cancel for CONTRACT; `hour` sets occurred_at on 2026-10-12."""
    return payload(
        event_type,
        event_id=event_id,
        contract_id=fields.pop("contract_id", CONTRACT),
        occurred_at=f"2026-10-12T{hour:02}:00:00Z",
        **fields,
    )


def pay(event_id: str, amount: str, **kw: Any) -> dict[str, Any]:
    return event("installment_payment_collected", event_id, amount=amount, **kw)


def overdue(event_id: str, late_fees: str, days: int = 3, **kw: Any) -> dict[str, Any]:
    return event(
        "installment_overdue", event_id, late_fees_accrued=late_fees, overdue_days=days, **kw
    )


def cancel(event_id: str, **kw: Any) -> dict[str, Any]:
    return event("installment_cancelled", event_id, **kw)


def purchase(principal: str = "1000.00", **contract: Any) -> dict[str, Any]:
    return created("evt_c", CONTRACT, principal, **contract)


def installment(session: Session) -> Installment:
    session.expire_all()
    return session.execute(
        select(Installment).where(Installment.contract_id == CONTRACT)
    ).scalar_one()


def status_of(session: Session, event_id: str) -> str:
    return session.execute(
        select(WebhookEvent.status).where(WebhookEvent.event_id == event_id)
    ).scalar_one()


def results(session: Session, action: str) -> list[str]:
    rows = session.execute(select(AuditLog.detail).where(AuditLog.action == action)).scalars()
    return [row["result"] for row in rows]


@pytest.fixture(autouse=True)
def _invariants_hold_after_each_test(db_session: Session) -> Any:
    yield
    assert check_user_invariants(db_session, USER) == []


# --- payment ---------------------------------------------------------------------------


def test_payments_add_up(db_session: Session, bank: MockBankAccountProvider) -> None:
    run(db_session, purchase(), bank)

    assert run(db_session, pay("evt_p1", "300.00"), bank) == Outcome.PROCESSED
    assert run(db_session, pay("evt_p2", "200.50", installment_no=2), bank) == Outcome.PROCESSED

    inst = installment(db_session)
    assert (inst.paid_amount, inst.status) == (Decimal("500.50"), "active")
    assert results(db_session, "webhook_event_applied") == ["applied", "applied"]


def test_OR_04_paid_in_full_is_paid_off(db_session: Session, bank: MockBankAccountProvider) -> None:
    run(db_session, purchase("1000.00", fee_total="60.00"), bank)
    for n in range(1, 4):
        run(db_session, pay(f"evt_p{n}", "353.33", installment_no=n), bank)
    assert installment(db_session).status == "active"  # 1,059.99 of 1,060.00

    run(db_session, pay("evt_p4", "0.01", installment_no=4), bank)

    inst = installment(db_session)
    assert (inst.paid_amount, inst.status) == (Decimal("1060.00"), "paid_off")


def test_OR_05_payment_over_amount_owed_rejected_and_audited(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase("1000.00"), bank)
    run(db_session, pay("evt_p1", "999.99"), bank)

    assert run(db_session, pay("evt_p2", "0.02"), bank) == Outcome.REJECTED

    inst = installment(db_session)
    assert (inst.paid_amount, inst.status) == (Decimal("999.99"), "active")
    assert status_of(db_session, "evt_p2") == "rejected"
    entry = db_session.execute(
        select(AuditLog).where(AuditLog.action == "webhook_event_rejected")
    ).scalar_one()
    assert entry.ref_id == str(inst.id)
    assert entry.detail == {
        "event_id": "evt_p2",
        "event_type": "installment_payment_collected",
        "result": "payment_exceeds_owed",
    }
    # L59 (1): a resend gets the same rejection and writes nothing.
    assert run(db_session, pay("evt_p2", "0.02"), bank) == Outcome.REJECTED
    assert results(db_session, "webhook_event_rejected") == ["payment_exceeds_owed"]


def test_OR_05_any_payment_after_paid_off_rejected(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase("100.00"), bank)
    run(db_session, pay("evt_p1", "100.00"), bank)

    assert run(db_session, pay("evt_p2", "0.01"), bank) == Outcome.REJECTED
    assert installment(db_session).paid_amount == Decimal("100.00")


def test_L48_payment_may_cover_late_fees(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase("1000.00"), bank)
    run(db_session, overdue("evt_o1", "50.00"), bank)

    assert run(db_session, pay("evt_p1", "1050.00"), bank) == Outcome.PROCESSED

    inst = installment(db_session)
    assert (inst.paid_amount, inst.status) == (Decimal("1050.00"), "paid_off")


@pytest.mark.parametrize("make", [pay, overdue, cancel], ids=["pay", "overdue", "cancel"])
def test_event_for_another_users_installment_rejected(
    db_session: Session, bank: MockBankAccountProvider, make: Any
) -> None:
    run(db_session, purchase(), bank)
    args = ("evt_x", "10.00") if make is not cancel else ("evt_x",)

    assert run(db_session, make(*args, user_ref="user_b"), bank) == Outcome.REJECTED

    inst = installment(db_session)
    assert (inst.paid_amount, inst.late_fees_accrued, inst.status) == (
        Decimal("0.00"),
        Decimal("0.00"),
        "active",
    )
    assert results(db_session, "webhook_event_rejected") == ["user_mismatch"]


# --- overdue (L55) ---------------------------------------------------------------------


def test_L55_overdue_sets_cumulative_late_fee_never_adds(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)

    run(db_session, overdue("evt_o1", "50.00", days=3, hour=11), bank)
    run(db_session, overdue("evt_o2", "80.00", days=10, hour=12), bank)

    inst = installment(db_session)
    assert inst.late_fees_accrued == Decimal("80.00")  # not 130.00
    assert inst.overdue_days == 10


def test_L55_older_overdue_delivered_late_changes_nothing(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)
    run(db_session, overdue("evt_o2", "80.00", days=10, hour=12), bank)

    assert run(db_session, overdue("evt_o1", "50.00", days=3, hour=11), bank) == Outcome.PROCESSED

    inst = installment(db_session)
    assert (inst.late_fees_accrued, inst.overdue_days) == (Decimal("80.00"), 10)
    assert status_of(db_session, "evt_o1") == "processed"
    assert results(db_session, "webhook_event_applied") == ["applied", "stale"]


def test_L55_platform_may_lower_late_fees(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)
    run(db_session, overdue("evt_o1", "80.00", hour=11), bank)

    run(db_session, overdue("evt_o2", "20.00", hour=12), bank)  # e.g. partly waived

    assert installment(db_session).late_fees_accrued == Decimal("20.00")


def test_INV_6_late_fees_lowered_below_what_was_paid_rejected(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase("1000.00"), bank)
    run(db_session, overdue("evt_o1", "80.00", hour=11), bank)
    run(db_session, pay("evt_p1", "1050.00", hour=12), bank)

    assert run(db_session, overdue("evt_o2", "20.00", hour=13), bank) == Outcome.REJECTED

    inst = installment(db_session)
    assert (inst.late_fees_accrued, inst.paid_amount) == (Decimal("80.00"), Decimal("1050.00"))
    assert results(db_session, "webhook_event_rejected") == ["late_fees_below_paid"]


def test_late_fee_after_paid_off_reopens_installment(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase("100.00"), bank)
    run(db_session, pay("evt_p1", "100.00"), bank)
    assert installment(db_session).status == "paid_off"

    run(db_session, overdue("evt_o1", "25.00"), bank)
    assert installment(db_session).status == "active"

    run(db_session, pay("evt_p2", "25.00"), bank)
    assert installment(db_session).status == "paid_off"


# --- cancel (INV-7) --------------------------------------------------------------------


def test_OR_02_INV_7_cancel_keeps_savings(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    run(db_session, purchase("800.00"), bank)
    before = (balance(db_session), len(auto_saves(db_session)), bank.get_balance(USER))
    assert before == ((Decimal("80.00"), 1), 1, DEFAULT_OPENING_BALANCE - Decimal("80.00"))

    assert run(db_session, cancel("evt_x"), bank) == Outcome.PROCESSED

    assert installment(db_session).status == "cancelled"
    assert (balance(db_session), len(auto_saves(db_session)), bank.get_balance(USER)) == before


def test_OR_03_same_cancel_twice_is_duplicate(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)

    assert run(db_session, cancel("evt_x"), bank) == Outcome.PROCESSED
    assert run(db_session, cancel("evt_x"), bank) == Outcome.DUPLICATE

    assert results(db_session, "webhook_event_applied") == ["applied"]


def test_second_cancel_with_new_event_id_changes_nothing(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)
    run(db_session, cancel("evt_x1"), bank)

    assert run(db_session, cancel("evt_x2"), bank) == Outcome.PROCESSED
    assert installment(db_session).status == "cancelled"


def test_cancel_after_paid_off_and_payment_after_cancel(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    """Cancelled is final for status; a payment the platform reports is still recorded."""
    run(db_session, purchase("100.00"), bank)
    run(db_session, pay("evt_p1", "40.00"), bank)
    run(db_session, cancel("evt_x"), bank)

    assert run(db_session, pay("evt_p2", "60.00"), bank) == Outcome.PROCESSED

    inst = installment(db_session)
    assert (inst.paid_amount, inst.status) == (Decimal("100.00"), "cancelled")


# --- pending_parent (OR-01, 04 step 5f) ------------------------------------------------


def test_OR_01_events_before_installment_applied_when_it_arrives(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    # Delivered newest first; replay must follow occurred_at.
    assert run(db_session, overdue("evt_o2", "80.00", days=9, hour=14), bank) == (
        Outcome.PENDING_PARENT
    )
    assert run(db_session, pay("evt_p1", "300.00", hour=11), bank) == Outcome.PENDING_PARENT
    assert run(db_session, overdue("evt_o1", "50.00", days=2, hour=12), bank) == (
        Outcome.PENDING_PARENT
    )
    assert db_session.execute(select(Installment)).first() is None

    assert run(db_session, purchase("1000.00"), bank) == Outcome.PROCESSED

    inst = installment(db_session)
    assert (inst.paid_amount, inst.late_fees_accrued, inst.overdue_days) == (
        Decimal("300.00"),
        Decimal("80.00"),
        9,
    )
    for event_id in ("evt_p1", "evt_o1", "evt_o2"):
        assert status_of(db_session, event_id) == "processed"
    assert results(db_session, "webhook_event_applied") == ["applied", "applied", "applied"]


def test_OR_01_pending_resend_still_pending(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, pay("evt_p1", "300.00"), bank)
    assert run(db_session, pay("evt_p1", "300.00"), bank) == Outcome.PENDING_PARENT

    run(db_session, purchase(), bank)

    assert run(db_session, pay("evt_p1", "300.00"), bank) == Outcome.DUPLICATE
    assert installment(db_session).paid_amount == Decimal("300.00")  # applied once


def test_OR_01_pending_cancel_before_installment(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    """The saving still happens on the created event; cancel never reverses it (rule 6)."""
    opt_in(db_session)
    run(db_session, cancel("evt_x"), bank)

    run(db_session, purchase("800.00"), bank)

    assert installment(db_session).status == "cancelled"
    assert balance(db_session) == (Decimal("80.00"), 1)


def test_OR_01_pending_overpayment_rejected_on_replay(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, pay("evt_p1", "600.00", hour=11), bank)
    run(db_session, pay("evt_p2", "600.00", hour=12), bank)

    assert run(db_session, purchase("1000.00"), bank) == Outcome.PROCESSED

    assert installment(db_session).paid_amount == Decimal("600.00")
    assert (status_of(db_session, "evt_p1"), status_of(db_session, "evt_p2")) == (
        "processed",
        "rejected",
    )


def test_OR_01_pending_event_of_another_user_rejected_on_replay(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, pay("evt_p1", "100.00", user_ref="user_b"), bank)

    run(db_session, purchase(), bank)

    assert installment(db_session).paid_amount == Decimal("0.00")
    assert status_of(db_session, "evt_p1") == "rejected"
    assert check_user_invariants(db_session, "user_b") == []


def test_pending_is_per_vendor(db_session: Session, bank: MockBankAccountProvider) -> None:
    """Same contract_id at another vendor is another contract (L47, ID-05)."""
    run(db_session, pay("evt_p1", "100.00"), bank, vendor="othervendor")

    run(db_session, purchase(), bank)

    assert installment(db_session).paid_amount == Decimal("0.00")
    assert status_of(db_session, "evt_p1") == "pending_parent"


# --- duplicates (ID-01 for payment, overdue, cancel) -----------------------------------


def test_ID_01_same_payment_twice_applied_once(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)

    assert run(db_session, pay("evt_p1", "300.00"), bank) == Outcome.PROCESSED
    assert run(db_session, pay("evt_p1", "300.00"), bank) == Outcome.DUPLICATE

    assert installment(db_session).paid_amount == Decimal("300.00")
    assert results(db_session, "webhook_event_applied") == ["applied"]


def test_ID_01_same_overdue_twice_applied_once(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)

    run(db_session, overdue("evt_o1", "50.00"), bank)
    assert run(db_session, overdue("evt_o1", "50.00"), bank) == Outcome.DUPLICATE

    assert installment(db_session).late_fees_accrued == Decimal("50.00")
    assert results(db_session, "webhook_event_applied") == ["applied"]


# --- S10: audit rows are filed under the owner -------------------------------------------


def audit_rows(session: Session, action: str) -> list[tuple[str, dict[str, Any]]]:
    rows = session.execute(
        select(AuditLog.user_id, AuditLog.detail).where(AuditLog.action == action)
    )
    return [(user_id, detail) for user_id, detail in rows]


def no_installment_rows_for(session: Session, user: str) -> bool:
    """What a per-user audit view would show `user` about installments: nothing."""
    return not session.execute(
        select(AuditLog.id).where(AuditLog.user_id == user, AuditLog.ref_type == "installment")
    ).first()


@pytest.mark.parametrize("make", [pay, overdue, cancel])
def test_S10_user_mismatch_audited_under_the_owner_with_the_claim_in_detail(
    db_session: Session, bank: MockBankAccountProvider, make: Any
) -> None:
    run(db_session, purchase(), bank)
    args = ("evt_x", "10.00") if make is not cancel else ("evt_x",)

    assert run(db_session, make(*args, user_ref="user_b"), bank) == Outcome.REJECTED

    [(user_id, detail)] = audit_rows(db_session, "webhook_event_rejected")
    assert (user_id, detail["claimed_user_ref"]) == (USER, "user_b")
    assert no_installment_rows_for(db_session, "user_b")


def test_S10_applied_event_has_no_claim(db_session: Session, bank: MockBankAccountProvider) -> None:
    run(db_session, purchase(), bank)
    run(db_session, pay("evt_p", "10.00"), bank)

    [(user_id, detail)] = audit_rows(db_session, "webhook_event_applied")
    assert user_id == USER
    assert "claimed_user_ref" not in detail


def test_S10_contract_reused_by_another_user_audited_under_the_owner(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)

    outcome = run(db_session, created("evt_c2", CONTRACT, "1000.00", user="user_b"), bank)

    assert outcome == Outcome.CONTRACT_CONFLICT
    [(user_id, detail)] = audit_rows(db_session, "contract_id_reused")
    assert (user_id, detail["claimed_user_ref"]) == (USER, "user_b")
    assert no_installment_rows_for(db_session, "user_b")


def test_S10_event_id_reused_audited_under_the_stored_events_user(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, purchase(), bank)
    run(db_session, pay("evt_p", "10.00"), bank)

    assert run(db_session, pay("evt_p", "10.00", user_ref="user_b"), bank) == Outcome.CONFLICT

    [(user_id, detail)] = audit_rows(db_session, "webhook_event_id_reused")
    assert (user_id, detail["claimed_user_ref"]) == (USER, "user_b")
