"""Webhook processing (04 section 6), inside the caller's single transaction.

Session 6 covers step 4 (record the event idempotently) and step 6 (audit).
Step 5 (dispatch to installments, savings, notifications) slots in where marked,
so the router does not change.
"""

import hashlib
import json
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.models import Actor, EventStatus, WebhookEvent
from app.schemas import WebhookEvent as Event


class Outcome(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    PENDING_PARENT = "pending_parent"  # set by dispatch from Session 7 (OR-01)
    CONFLICT = "conflict"  # same (vendor, event_id), different payload


def payload_hash(payload: Any) -> str:
    """SHA-256 of canonical JSON: sorted keys, no whitespace. JSONB keeps neither
    key order nor spacing, so the stored and received payloads compare this way."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def process_event(
    session: Session, *, vendor: str, event: Event, payload: dict[str, Any]
) -> Outcome:
    """Record one verified, validated event. The caller commits."""
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

    # Step 5 (Session 7): dispatch(session, vendor, event) goes here and may return
    # Outcome.PENDING_PARENT.

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
    return Outcome.PROCESSED
