"""Webhook processing (04 section 6), inside the caller's single transaction.

Step 4 records the event idempotently, step 5 dispatches the three contract-created
events (5a installment, 5b/5c auto-save), step 6 audits, step 7 reconciles. Payment,
overdue and cancel dispatch (Session 8) and notifications (Session 9) come later.
"""

import hashlib
import json
import logging
from enum import StrEnum
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.ledger import reconcile
from app.ledger import service as ledger
from app.models import Actor, EventStatus, WebhookEvent
from app.providers import get_bank_provider
from app.providers.base import BankAccountProvider
from app.rules.engine import ZERO
from app.savings import service as savings
from app.schemas import CashLoanCreated, CashWithdrawalCreated, InstallmentCreated
from app.schemas import WebhookEvent as Event

logger = logging.getLogger(__name__)


class Outcome(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    PENDING_PARENT = "pending_parent"  # set by dispatch from Session 7 (OR-01)
    CONFLICT = "conflict"  # same (vendor, event_id), different payload
    CONTRACT_CONFLICT = "contract_conflict"  # same (vendor, contract_id), different contract


def payload_hash(payload: Any) -> str:
    """SHA-256 of canonical JSON: sorted keys, no whitespace. JSONB keeps neither
    key order nor spacing, so the stored and received payloads compare this way."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def contract_hash(payload: dict[str, Any]) -> str:
    """What must match for a resent contract to count as the same one (ID-05): the
    contract and the user it belongs to."""
    return payload_hash({"user_ref": payload["user_ref"], "contract": payload["contract"]})


def process_event(
    session: Session,
    *,
    vendor: str,
    event: Event,
    payload: dict[str, Any],
    bank: BankAccountProvider | None = None,
) -> Outcome:
    """Record and apply one verified, validated event. The caller commits.

    Raises reconcile.InvariantViolationError after rolling the session back (RS-02).
    """
    bank = bank if bank is not None else get_bank_provider()
    # Step 4: the DB decides. Of N concurrent copies, exactly one gets a row back (L47).
    inserted = session.execute(
        pg_insert(WebhookEvent)
        .values(
            vendor=vendor,
            event_id=event.event_id,
            event_type=event.event_type,
            user_id=event.user_ref,
            contract_id=event.contract_id,
            payload=payload,
            status=EventStatus.PROCESSED,
        )
        .on_conflict_do_nothing(index_elements=[WebhookEvent.vendor, WebhookEvent.event_id])
        .returning(WebhookEvent.event_id)
    ).scalar_one_or_none()
    ref_id = f"{vendor}:{event.event_id}"

    if inserted is None:
        stored = session.execute(
            select(WebhookEvent.payload).where(
                WebhookEvent.vendor == vendor, WebhookEvent.event_id == event.event_id
            )
        ).scalar_one()
        stored_hash, received_hash = payload_hash(stored), payload_hash(payload)
        if stored_hash == received_hash:
            return Outcome.DUPLICATE
        # Keep the original row untouched; record that the id was reused.
        audit.record(
            session,
            actor=Actor.SYSTEM,
            action="webhook_event_id_reused",
            user_id=event.user_ref,
            ref_type="webhook_event",
            ref_id=ref_id,
            detail={"stored_hash": stored_hash, "received_hash": received_hash},
        )
        return Outcome.CONFLICT

    # Step 5
    saving = ZERO
    if isinstance(event, InstallmentCreated | CashWithdrawalCreated | CashLoanCreated):
        installment_id = ledger.create_installment(session, vendor=vendor, event=event)
        if installment_id is None:
            return _contract_reused(session, vendor=vendor, event=event, payload=payload)
        saving = savings.auto_save(
            session, vendor=vendor, event=event, installment_id=installment_id, bank=bank
        )

    # Step 6
    audit.record(
        session,
        actor=Actor.SYSTEM,
        action="webhook_received",
        user_id=event.user_ref,
        ref_type="webhook_event",
        ref_id=ref_id,
        detail={
            "vendor": vendor,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "contract_id": event.contract_id,
        },
    )

    # Step 7: a violation is a bug. Nothing of this event may persist.
    try:
        reconcile.assert_user_invariants(session, event.user_ref)
    except reconcile.InvariantViolationError as exc:
        session.rollback()
        logger.error(
            "reconcile failed, event rolled back: %s (vendor=%s event_id=%s)",
            exc,
            vendor,
            event.event_id,
        )
        raise

    # Step 5c, last: money moves only once the ledger rows have passed reconcile.
    if saving > ZERO:
        bank.transfer_to_savings(event.user_ref, saving)
    return Outcome.PROCESSED


def _contract_reused(
    session: Session,
    *,
    vendor: str,
    event: ledger.ContractCreated,
    payload: dict[str, Any],
) -> Outcome:
    """ID-05: a new event_id for a contract that already has an installment.

    Nothing new is created and nothing is saved. The new event row stays as
    rejected, so a resend of it is a plain duplicate.
    """
    session.execute(
        update(WebhookEvent)
        .where(WebhookEvent.vendor == vendor, WebhookEvent.event_id == event.event_id)
        .values(status=EventStatus.REJECTED)
        .execution_options(synchronize_session=False)
    )
    # After the status change, so the only processed created event is the original.
    installment_id, original_event_id, original = ledger.find_original(
        session, vendor=vendor, contract_id=event.contract_id
    )
    stored_hash, received_hash = contract_hash(original), contract_hash(payload)
    same = stored_hash == received_hash
    detail: dict[str, Any] = {
        "installment_id": str(installment_id),
        "original_event_id": original_event_id,
        "event_id": event.event_id,
        "same_contract": same,
    }
    if not same:
        detail |= {"stored_hash": stored_hash, "received_hash": received_hash}
    audit.record(
        session,
        actor=Actor.SYSTEM,
        action="contract_id_reused",
        user_id=event.user_ref,
        ref_type="installment",
        ref_id=str(installment_id),
        detail=detail,
    )
    return Outcome.DUPLICATE if same else Outcome.CONTRACT_CONFLICT
