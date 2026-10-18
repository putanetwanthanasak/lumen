"""L42 "Not me": the user reports an installment as not theirs.

The installment becomes `disputed` with `disputed_at`, the user's alert is marked
`not_me`, an audit row is written, and after commit the platform gets a dispute
signal. Lumen never stops or reverses the platform transaction; it reports, and
gives the user the platform's contact channel.

Status rules (L59 3): active and paid_off become disputed; a cancelled installment
stays cancelled but still records the report (the debt is not owed, the fraud
report must not be lost). disputed_at is set once and never cleared, so a later
cancel keeps the history. There is no undo in this prototype.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.ledger.service import lock_contract
from app.models import (
    DISPUTE_ACTION,
    NEW_DEBT_KINDS,
    Actor,
    Installment,
    InstallmentStatus,
    Notification,
    UserResponse,
)


@dataclass(frozen=True)
class Disputed:
    installment_id: uuid.UUID
    vendor: str
    contract_id: str
    status: str
    disputed_at: datetime
    # True only for the one call that recorded the dispute: it alone signals the platform.
    first_report: bool


def dispute(session: Session, *, user_id: str, installment_id: uuid.UUID) -> Disputed | None:
    """Record "Not me" for the user's own installment. None if there is no such
    installment for this user (the caller answers 404 either way). The caller commits.

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
    status, disputed_at = session.execute(
        select(Installment.status, Installment.disputed_at).where(Installment.id == installment_id)
    ).one()
    # Not None: set above or by an earlier report, and never cleared.
    return Disputed(
        installment_id, vendor, contract_id, status, cast(datetime, disputed_at), first_report
    )
