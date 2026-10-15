"""Installment Ledger (04 section 6, steps 5a and 5f later)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import EventStatus, EventType, Installment, WebhookEvent
from app.schemas import CashLoanCreated, CashWithdrawalCreated, InstallmentCreated

ContractCreated = InstallmentCreated | CashWithdrawalCreated | CashLoanCreated

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
