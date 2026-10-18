"""Invariant checks run inside the transaction before commit (04 step 7, 05 section 3).

A violation means a bug, not bad input: the caller rolls back the whole transaction
and logs it (RS-02). INV-1, 2, 3, 5 and 6 are checked; INV-4 is enforced by the rule
engine and INV-7 needs a before-and-after, so tests check both. INV-5 and "auto-save
user = event user" live here, not in the DB (L51).
"""

from decimal import Decimal

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models import (
    EventType,
    Installment,
    SavingsTransaction,
    SavingsType,
    UserBalance,
    WebhookEvent,
)
from app.rules.config import NEVER_SAVE_KINDS

CASH_EVENT_TYPES = (EventType.CASH_WITHDRAWAL_CREATED, EventType.CASH_LOAN_CREATED)


class InvariantViolationError(Exception):
    def __init__(self, user_id: str, violations: list[str]) -> None:
        # S12: the message is logged, so it names the invariants, never the user.
        super().__init__(f"invariants violated: {', '.join(violations)}")
        self.user_id = user_id
        self.violations = violations


def check_user_invariants(session: Session, user_id: str) -> list[str]:
    """The IDs of every invariant that does not hold for this user; empty if all hold."""
    session.flush()
    violations: list[str] = []

    # INV-1 and INV-2 in one statement, so both sides come from one snapshot. Two
    # statements could straddle another transaction's commit under READ COMMITTED
    # and report a mismatch that never existed.
    tx = SavingsTransaction
    ledger_total = (
        select(
            func.coalesce(
                func.sum(case((tx.type == SavingsType.AUTO_SAVE, tx.amount), else_=-tx.amount)),
                0,
            )
        )
        .where(tx.user_id == user_id)
        .scalar_subquery()
    )
    cached = (
        select(UserBalance.savings_balance).where(UserBalance.user_id == user_id).scalar_subquery()
    )
    balance, total = session.execute(
        select(func.coalesce(cached, literal(Decimal("0.00"))), ledger_total)
    ).one()
    if balance != total:
        violations.append("INV-1")
    if balance < 0:
        violations.append("INV-2")

    # INV-3: one event creates at most one auto_save.
    auto_save = and_(tx.user_id == user_id, tx.type == SavingsType.AUTO_SAVE)
    repeated = session.execute(
        select(tx.source_vendor, tx.source_event_id)
        .where(auto_save)
        .group_by(tx.source_vendor, tx.source_event_id)
        .having(func.count() > 1)
        .limit(1)
    ).first()
    if repeated is not None:
        violations.append("INV-3")

    # INV-5: no auto_save from a cash event or a cash installment.
    from_cash = session.execute(
        select(tx.id)
        .join(
            WebhookEvent,
            and_(
                WebhookEvent.vendor == tx.source_vendor,
                WebhookEvent.event_id == tx.source_event_id,
            ),
        )
        .outerjoin(Installment, Installment.id == tx.installment_id)
        .where(
            auto_save,
            or_(
                WebhookEvent.event_type.in_(CASH_EVENT_TYPES),
                Installment.kind.in_(NEVER_SAVE_KINDS),
            ),
        )
        .limit(1)
    ).first()
    if from_cash is not None:
        violations.append("INV-5")

    # L51: an auto_save belongs to the user its event belongs to. Matched from both
    # sides, so a saving filed under the wrong user is found from the event's user too.
    other_user = session.execute(
        select(tx.id)
        .join(
            WebhookEvent,
            and_(
                WebhookEvent.vendor == tx.source_vendor,
                WebhookEvent.event_id == tx.source_event_id,
            ),
        )
        .where(
            tx.type == SavingsType.AUTO_SAVE,
            or_(tx.user_id == user_id, WebhookEvent.user_id == user_id),
            WebhookEvent.user_id != tx.user_id,
        )
        .limit(1)
    ).first()
    if other_user is not None:
        violations.append("L51")

    # INV-6 (L48): never paid more than is owed, late fees included. The DB CHECK
    # paid_le_total enforces it too; this names it in the RS-02 log.
    inst = Installment
    overpaid = session.execute(
        select(inst.id)
        .where(
            inst.user_id == user_id,
            inst.paid_amount > inst.principal + inst.fee_total + inst.late_fees_accrued,
        )
        .limit(1)
    ).first()
    if overpaid is not None:
        violations.append("INV-6")

    return violations


def assert_user_invariants(session: Session, user_id: str) -> None:
    """Raise InvariantViolationError if any invariant fails for this user."""
    violations = check_user_invariants(session, user_id)
    if violations:
        raise InvariantViolationError(user_id, violations)
