"""Installment Ledger (04 section 6, steps 5a and 5f, payment, overdue and cancel)."""

import uuid
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import EventStatus, EventType, Installment, InstallmentStatus, WebhookEvent
from app.money import MONEY_MAX
from app.schemas import (
    CashLoanCreated,
    CashWithdrawalCreated,
    InstallmentCancelled,
    InstallmentCreated,
    InstallmentOverdue,
    PaymentCollected,
)

ContractCreated = InstallmentCreated | CashWithdrawalCreated | CashLoanCreated
ContractEvent = PaymentCollected | InstallmentOverdue | InstallmentCancelled


class Applied(StrEnum):
    APPLIED = "applied"
    STALE = "stale"  # an overdue older than one already applied: stored, changes nothing
    # Rejections: the event is stored as rejected and audited, the installment untouched.
    USER_MISMATCH = "user_mismatch"
    PAYMENT_EXCEEDS_OWED = "payment_exceeds_owed"  # OR-05, INV-6
    LATE_FEES_BELOW_PAID = "late_fees_below_paid"  # INV-6 from the other side
    # S7: owed() can pass MONEY_MAX; storing more would overflow Numeric(12,2) (a 500
    # on every retry). late_fees_accrued is set, not added, and parsed below MONEY_MAX.
    PAID_AMOUNT_TOO_LARGE = "paid_amount_too_large"


REJECTIONS = frozenset(
    {
        Applied.USER_MISMATCH,
        Applied.PAYMENT_EXCEEDS_OWED,
        Applied.LATE_FEES_BELOW_PAID,
        Applied.PAID_AMOUNT_TOO_LARGE,
    }
)

CREATED_EVENT_TYPES = (
    EventType.INSTALLMENT_CREATED,
    EventType.CASH_WITHDRAWAL_CREATED,
    EventType.CASH_LOAN_CREATED,
)


def create_installment(
    session: Session, *, vendor: str, event: ContractCreated
) -> uuid.UUID | None:
    """Insert the installment, or return None if (vendor, contract_id) already has one.

    The UNIQUE constraint decides (ID-05), so two event_ids racing for one contract
    still create a single row. The owner is the event's user (L51).
    """
    contract = event.contract
    return session.execute(
        pg_insert(Installment)
        .values(
            user_id=event.user_ref,
            vendor=vendor,
            contract_id=contract.contract_id,
            kind=contract.kind,
            item_name=contract.item_name,
            principal=contract.principal,
            months=contract.months,
            monthly_amount=contract.monthly_amount,
            fee_total=contract.fee_total,
            first_due_date=contract.first_due_date,
            min_payment=contract.min_payment,
            late_fee_per_period=contract.late_fee_per_period,
            monthly_rate=contract.monthly_rate,
            overdue_days=contract.overdue_days,
        )
        .on_conflict_do_nothing(index_elements=[Installment.vendor, Installment.contract_id])
        .returning(Installment.id)
    ).scalar_one_or_none()


def find_original(
    session: Session, *, vendor: str, contract_id: str
) -> tuple[uuid.UUID, str, dict[str, Any]]:
    """The existing installment id, plus the event_id and payload of the event that created it."""
    installment_id = session.execute(
        select(Installment.id).where(
            Installment.vendor == vendor, Installment.contract_id == contract_id
        )
    ).scalar_one()
    event_id, payload = session.execute(
        select(WebhookEvent.event_id, WebhookEvent.payload).where(
            WebhookEvent.vendor == vendor,
            WebhookEvent.contract_id == contract_id,
            WebhookEvent.event_type.in_(CREATED_EVENT_TYPES),
            WebhookEvent.status == EventStatus.PROCESSED,
        )
    ).one()
    return installment_id, event_id, payload


def lock_contract(session: Session, *, vendor: str, contract_id: str) -> None:
    """Serialise every event of one contract until commit.

    Without it, a payment racing its own created event could be stored as
    pending_parent while the created transaction, which cannot see that uncommitted
    row, finds nothing to replay: the payment would wait forever. A hash collision
    only serialises two unrelated contracts.
    """
    key = func.hashtextextended(f"{vendor}:{contract_id}", 0)
    session.execute(select(func.pg_advisory_xact_lock(key)))


def find_installment(session: Session, *, vendor: str, contract_id: str) -> Installment | None:
    return session.execute(
        select(Installment).where(
            Installment.vendor == vendor, Installment.contract_id == contract_id
        )
    ).scalar_one_or_none()


def owed(installment: Installment) -> Decimal:
    """The most that may ever be paid (INV-6, L48)."""
    return installment.principal + installment.fee_total + installment.late_fees_accrued


def apply_event(
    session: Session, *, vendor: str, installment: Installment, event: ContractEvent
) -> Applied:
    """Apply a payment, overdue or cancel to its installment. The caller holds
    lock_contract and has already stored the event."""
    if event.user_ref != installment.user_id:
        return Applied.USER_MISMATCH
    match event:
        case PaymentCollected():
            paid = installment.paid_amount + event.amount
            if paid > owed(installment):
                return Applied.PAYMENT_EXCEEDS_OWED
            if paid > MONEY_MAX:
                return Applied.PAID_AMOUNT_TOO_LARGE
            installment.paid_amount = paid
        case InstallmentOverdue():
            if _is_stale(session, vendor=vendor, event=event):
                return Applied.STALE
            total = installment.principal + installment.fee_total + event.late_fees_accrued
            if installment.paid_amount > total:
                return Applied.LATE_FEES_BELOW_PAID
            # L55: the platform sends the cumulative total. Set it, never add it.
            installment.late_fees_accrued = event.late_fees_accrued
            installment.overdue_days = event.overdue_days
        case _:  # InstallmentCancelled, the last member of ContractEvent
            # INV-7: savings are not touched; what was saved stays saved (rule 6).
            installment.status = InstallmentStatus.CANCELLED
    _settle(installment)
    session.flush()
    return Applied.APPLIED


def _settle(installment: Installment) -> None:
    """active <-> paid_off as the amount owed is reached or grows again (late fees).
    Cancelled and disputed are never changed here."""
    paid_up = installment.paid_amount == owed(installment)
    if installment.status == InstallmentStatus.ACTIVE and paid_up:
        installment.status = InstallmentStatus.PAID_OFF
    elif installment.status == InstallmentStatus.PAID_OFF and not paid_up:
        installment.status = InstallmentStatus.ACTIVE


def _is_stale(session: Session, *, vendor: str, event: InstallmentOverdue) -> bool:
    """True if an overdue that occurred later was already applied to this contract.

    Each overdue carries a cumulative total, so only the latest by occurred_at may
    win. A late-delivered older one would otherwise lower late_fees_accrued.
    """
    latest = session.execute(
        select(
            func.max(WebhookEvent.payload["occurred_at"].astext.cast(DateTime(timezone=True)))
        ).where(
            WebhookEvent.vendor == vendor,
            WebhookEvent.contract_id == event.contract_id,
            WebhookEvent.event_type == EventType.INSTALLMENT_OVERDUE,
            WebhookEvent.status == EventStatus.PROCESSED,
            WebhookEvent.event_id != event.event_id,
        )
    ).scalar_one()
    return latest is not None and event.occurred_at < latest


def pending_payloads(session: Session, *, vendor: str, contract_id: str) -> list[dict[str, Any]]:
    """Events stored before their installment existed (5f), oldest first."""
    occurred = WebhookEvent.payload["occurred_at"].astext.cast(DateTime(timezone=True))
    return list(
        session.execute(
            select(WebhookEvent.payload)
            .where(
                WebhookEvent.vendor == vendor,
                WebhookEvent.contract_id == contract_id,
                WebhookEvent.status == EventStatus.PENDING_PARENT,
            )
            .order_by(occurred, WebhookEvent.event_id)
        ).scalars()
    )
