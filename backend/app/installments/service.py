"""Manual installment entry (L62), in the caller's single transaction.

The same steps as a webhook contract (04 section 6): insert idempotently, auto-save
by the user's rule (L63), store the alert with the L43 monthly total, audit,
reconcile, and only then move the money. The caller commits and then pushes.
"""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.debts.service import summary
from app.installments.schemas import ManualEntryIn
from app.ledger import reconcile
from app.models import MANUAL_VENDOR, Actor, Installment, SavingsTransaction, SavingsType
from app.notifications import service as notifications
from app.providers.base import BankAccountProvider
from app.rules.engine import ZERO
from app.savings import service as savings

logger = logging.getLogger(__name__)


class Outcome(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"  # the same request again: nothing new is written
    CONFLICT = "conflict"  # the same client_request_id with different fields


@dataclass(frozen=True)
class Recorded:
    outcome: Outcome
    installment_id: uuid.UUID
    saved_amount: Decimal = ZERO
    monthly_total: Decimal = ZERO
    # The alert this call stored, to push after commit. None on a replay.
    notification_id: uuid.UUID | None = None


def record(
    session: Session, *, user_id: str, entry: ManualEntryIn, bank: BankAccountProvider
) -> Recorded:
    """Record one manual entry. Raises reconcile.InvariantViolationError after rolling
    the session back, as the webhook path does (RS-02)."""
    # The partial UNIQUE index decides: of N concurrent submits, one gets a row back
    # and the others wait for its commit, then find it.
    installment_id = session.execute(
        pg_insert(Installment)
        .values(
            user_id=user_id,
            vendor=MANUAL_VENDOR,
            contract_id=str(uuid.uuid4()),
            client_request_id=entry.client_request_id,
            kind=entry.kind,
            item_name=entry.item_name,
            principal=entry.item_price,
            months=entry.months,
            monthly_amount=entry.monthly_amount,
            fee_total=entry.fee_total,
            first_due_date=entry.first_due_month,
        )
        .on_conflict_do_nothing(
            index_elements=[Installment.user_id, Installment.client_request_id],
            index_where=text("client_request_id IS NOT NULL"),
        )
        .returning(Installment.id)
    ).scalar_one_or_none()
    if installment_id is None:
        return _resubmitted(session, user_id=user_id, entry=entry)

    saving = savings.auto_save(
        session,
        user_id=user_id,
        kind=entry.kind,
        item_price=entry.item_price,
        installment_id=installment_id,
        source=None,
        bank=bank,
    )
    notification_id = notifications.notify_manual_entry(
        session,
        user_id=user_id,
        installment_id=installment_id,
        kind=entry.kind,
        item_name=entry.item_name,
        item_price=entry.item_price,
        months=entry.months,
        monthly_amount=entry.monthly_amount,
    )
    audit.record(
        session,
        actor=Actor.USER,
        action="installment_recorded",
        user_id=user_id,
        ref_type="installment",
        ref_id=str(installment_id),
        detail={"client_request_id": entry.client_request_id, "kind": entry.kind},
    )
    try:
        reconcile.assert_user_invariants(session, user_id)
    except reconcile.InvariantViolationError as exc:
        session.rollback()
        logger.error("reconcile failed, manual entry rolled back: %s", exc)
        raise

    # Money moves only once the ledger rows have passed reconcile.
    if saving > ZERO:
        bank.transfer_to_savings(
            user_id,
            saving,
            idempotency_key=savings.manual_transfer_key(user_id, entry.client_request_id),
        )
    return Recorded(
        Outcome.CREATED,
        installment_id,
        saving,
        summary(session, user_id).monthly_total,
        notification_id,
    )


def _same(row: Installment, entry: ManualEntryIn) -> bool:
    return (row.kind, row.item_name, row.principal, row.months, row.monthly_amount) == (
        entry.kind,
        entry.item_name,
        entry.item_price,
        entry.months,
        entry.monthly_amount,
    ) and row.first_due_date == entry.first_due_month


def _resubmitted(session: Session, *, user_id: str, entry: ManualEntryIn) -> Recorded:
    """The user already sent this client_request_id. The same fields get the first
    answer again and nothing is written; different fields are a conflict (as L55)."""
    row = session.execute(
        select(Installment).where(
            Installment.user_id == user_id,
            Installment.client_request_id == entry.client_request_id,
        )
    ).scalar_one()
    if not _same(row, entry):
        audit.record(
            session,
            actor=Actor.USER,
            action="client_request_id_reused",
            user_id=user_id,
            ref_type="installment",
            ref_id=str(row.id),
            detail={"client_request_id": entry.client_request_id},
        )
        return Recorded(Outcome.CONFLICT, row.id)
    saved = session.execute(
        select(SavingsTransaction.amount).where(
            SavingsTransaction.installment_id == row.id,
            SavingsTransaction.type == SavingsType.AUTO_SAVE,
        )
    ).scalar_one_or_none()
    return Recorded(
        Outcome.DUPLICATE,
        row.id,
        saved if saved is not None else ZERO,
        summary(session, user_id).monthly_total,
    )
