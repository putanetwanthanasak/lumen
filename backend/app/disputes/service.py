"""L42 "Not me": the user reports an installment as not theirs.

The installment becomes `disputed` with `disputed_at`, the user's alert is marked
`not_me`, an audit row is written, and after commit the platform gets a dispute
signal. Lumen never stops or reverses the platform transaction; it reports, and
gives the user the platform's contact channel.

Status rules (L59 3): active and paid_off become disputed; a cancelled installment
stays cancelled but still records the report (the debt is not owed, the fraud
report must not be lost). disputed_at is set once and never cleared, so a later
cancel keeps the history. There is no undo in this prototype.

L68: a manual entry (L62) has no platform to report to, so "Not me" on one is
refused. Nothing changes and no signal is sent; the attempt is audited.

L60 (2) / S4: the platform signal has its own status. The report sets it to
`pending` in the same transaction; send_signal then tries the platform and stores
`sent` or `failed`. A repeat tap tries again while it is not `sent`.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.db import describe_db_error
from app.ledger.service import lock_contract
from app.models import (
    DISPUTE_ACTION,
    MANUAL_VENDOR,
    NEW_DEBT_KINDS,
    Actor,
    DisputeSignalStatus,
    Installment,
    InstallmentStatus,
    Notification,
    UserResponse,
)
from app.providers.base import PlatformProvider

logger = logging.getLogger(__name__)

MANUAL_REJECTED_ACTION = "not_me_rejected_manual_entry"


@dataclass(frozen=True)
class Disputed:
    installment_id: uuid.UUID
    vendor: str
    contract_id: str
    status: str
    disputed_at: datetime
    signal_status: str
    # True only for the one call that recorded the dispute (and wrote its audit row).
    first_report: bool


@dataclass(frozen=True)
class ManualEntryRejected:
    """L68: the installment is one the user recorded themselves."""

    installment_id: uuid.UUID


def dispute(
    session: Session, *, user_id: str, installment_id: uuid.UUID
) -> Disputed | ManualEntryRejected | None:
    """Record "Not me" for the user's own installment. None if there is no such
    installment for this user (the caller answers 404 either way). The caller commits,
    also after a ManualEntryRejected, so its audit row is kept.

    Idempotent: a repeat, sequential or concurrent, changes nothing and gets the same
    stored values back.
    """
    found = session.execute(
        select(Installment.vendor, Installment.contract_id).where(
            Installment.id == installment_id, Installment.user_id == user_id
        )
    ).one_or_none()
    if found is None:
        return None
    vendor, contract_id = found
    if vendor == MANUAL_VENDOR:
        # L68: no status change, no disputed_at, no alert update and no signal; the
        # user recorded this one and can see it is theirs. Each attempt is audited.
        audit.record(
            session,
            actor=Actor.USER,
            action=MANUAL_REJECTED_ACTION,
            user_id=user_id,
            ref_type="installment",
            ref_id=str(installment_id),
            detail={"vendor": vendor, "contract_id": contract_id},
        )
        return ManualEntryRejected(installment_id)
    # The webhook lock: a payment that read `active` must not later write paid_off
    # over a dispute that committed in between (_settle runs on a stale status).
    lock_contract(session, vendor=vendor, contract_id=contract_id)

    previous = session.execute(
        select(Installment.status).where(Installment.id == installment_id)
    ).scalar_one()
    first_report = (
        session.execute(
            update(Installment)
            .where(Installment.id == installment_id, Installment.disputed_at.is_(None))
            .values(
                disputed_at=func.now(),
                dispute_signal_status=DisputeSignalStatus.PENDING,
                status=case(
                    (Installment.status == InstallmentStatus.CANCELLED, Installment.status),
                    else_=InstallmentStatus.DISPUTED,
                ),
            )
            .returning(Installment.id)
            # Refresh a loaded copy, so this session never writes back a stale status.
            .execution_options(synchronize_session="fetch")
        ).scalar_one_or_none()
        is not None
    )
    if first_report:
        session.execute(
            update(Notification)
            .where(
                Notification.installment_id == installment_id,
                Notification.kind.in_(NEW_DEBT_KINDS),
            )
            .values(user_response=UserResponse.NOT_ME)
            .execution_options(synchronize_session=False)
        )
        audit.record(
            session,
            actor=Actor.USER,
            action=DISPUTE_ACTION,
            user_id=user_id,
            ref_type="installment",
            ref_id=str(installment_id),
            detail={"vendor": vendor, "contract_id": contract_id, "previous_status": previous},
        )
    status, disputed_at, signal_status = session.execute(
        select(
            Installment.status, Installment.disputed_at, Installment.dispute_signal_status
        ).where(Installment.id == installment_id)
    ).one()
    # Not None: set above or by an earlier report, and never cleared.
    return Disputed(
        installment_id,
        vendor,
        contract_id,
        status,
        cast(datetime, disputed_at),
        cast(str, signal_status),
        first_report,
    )


def send_signal(
    session: Session, *, report: Disputed, user_id: str, platform: PlatformProvider
) -> str:
    """Signal the platform unless it already has this report, store the outcome, and
    return the stored status. Runs after the report committed; the caller commits.

    The contract lock is held across the platform call, so of any number of taps
    exactly one sends, and a tap that waited sees `sent` and sends nothing. The cost:
    that contract's webhooks wait for the platform call (a real provider needs a
    timeout; a retry outbox is R4).
    """
    lock_contract(session, vendor=report.vendor, contract_id=report.contract_id)
    current = session.execute(
        select(Installment.dispute_signal_status).where(Installment.id == report.installment_id)
    ).scalar_one()
    if current == DisputeSignalStatus.SENT:
        return current
    try:
        platform.signal_dispute(
            vendor=report.vendor, contract_id=report.contract_id, user_id=user_id
        )
        outcome = DisputeSignalStatus.SENT
    except Exception as exc:
        # S12: the class only; the provider's text may echo the user ref.
        logger.error(
            "dispute signal failed for installment %s: %s",
            report.installment_id,
            describe_db_error(exc),
        )
        outcome = DisputeSignalStatus.FAILED
    session.execute(
        update(Installment)
        .where(Installment.id == report.installment_id)
        .values(dispute_signal_status=outcome)
        .execution_options(synchronize_session=False)
    )
    return outcome
