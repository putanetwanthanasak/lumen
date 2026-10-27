"""Alerts: new debt (04 section 6, steps 5e and 9; 05 NT-01..NT-04, RS-03) and
payday (L67).

5e runs inside the webhook transaction, so the alert row commits or rolls back with
the installment. Step 9, the push, runs only after commit: a push can never be
undone, and a failing push must never fail the webhook (RS-03). The row is the
record; the push is only a delivery attempt.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import describe_db_error
from app.debts.service import summary
from app.ledger.service import ContractCreated
from app.models import (
    NEW_DEBT_KIND_SQL,
    DeliveryStatus,
    InstallmentKind,
    Notification,
    NotificationKind,
)
from app.notifications.copy import manual_entry_alert, new_debt_alert
from app.providers.base import PushProvider
from app.rules.config import load_rules

logger = logging.getLogger(__name__)


def notify_new_debt(
    session: Session, *, vendor: str, event: ContractCreated, installment_id: uuid.UUID
) -> uuid.UUID | None:
    """Store the new-debt alert for this installment and return its id, or None if the
    installment already has one.

    Called after 5f, so the L43 monthly total is what the summary shows at commit,
    even when a replayed cancel or payment has already changed this installment.
    Every new installment alerts regardless of its status (L58).
    """
    contract = event.contract
    kind, title, body = new_debt_alert(
        kind=contract.kind,
        vendor=vendor,
        amount=contract.principal,
        months=contract.months,
        monthly_total=summary(session, event.user_ref).monthly_total,
    )
    return _store(session, event.user_ref, installment_id, kind, title, body)


def notify_manual_entry(
    session: Session,
    *,
    user_id: str,
    installment_id: uuid.UUID,
    kind: InstallmentKind,
    item_name: str,
    item_price: Decimal,
    months: int,
    monthly_amount: Decimal,
) -> uuid.UUID | None:
    """As notify_new_debt, for an installment the user recorded (L62). The body still
    carries the monthly total including this installment (L43)."""
    kind_, title, body = manual_entry_alert(
        kind=kind,
        item_name=item_name,
        item_price=item_price,
        months=months,
        monthly_amount=monthly_amount,
        monthly_total=summary(session, user_id).monthly_total,
    )
    return _store(session, user_id, installment_id, kind_, title, body)


def _store(
    session: Session,
    user_id: str,
    installment_id: uuid.UUID,
    kind: NotificationKind,
    title: str,
    body: str,
) -> uuid.UUID | None:
    # The UNIQUE index decides: of any number of attempts, one gets a row back.
    return session.execute(
        pg_insert(Notification)
        .values(
            user_id=user_id,
            installment_id=installment_id,
            kind=kind,
            title=title,
            body=body,
        )
        .on_conflict_do_nothing(
            index_elements=[Notification.installment_id],
            index_where=text(NEW_DEBT_KIND_SQL),
        )
        .returning(Notification.id)
    ).scalar_one_or_none()


def store_payday_alert(
    session: Session, *, user_id: str, kind: NotificationKind, title: str, body: str
) -> uuid.UUID:
    """Store a payday alert (L67); not tied to an installment. Once per month is
    the payday run's own key (payday_runs), so this plain insert is not deduplicated."""
    row = Notification(user_id=user_id, kind=kind, title=title, body=body)
    session.add(row)
    session.flush()
    return row.id


def deliver(session: Session, notification_id: uuid.UUID, push: PushProvider) -> None:
    """Step 9, after commit: push up to push_max_attempts times, then record the
    result. Never raises. If this fails or the process stops, the row stays
    `pending` and remains in the inbox (known gap, as for the R4 outbox)."""
    try:
        row = session.execute(
            select(Notification).where(Notification.id == notification_id)
        ).scalar_one()
        user_id, title, body = row.user_id, row.title, row.body
        max_attempts = load_rules().alerts.push_max_attempts
        attempts, delivered = 0, False
        while attempts < max_attempts and not delivered:
            attempts += 1
            delivered = _try_push(push, user_id, title, body)
        status = DeliveryStatus.PUSHED if delivered else DeliveryStatus.INBOX_ONLY
        session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(delivery_status=status, push_attempts=attempts)
            .execution_options(synchronize_session=False)
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        # S12: no traceback; a DB error's text quotes the row (user ref, alert body).
        logger.error(
            "push delivery failed for notification %s: %s",
            notification_id,
            describe_db_error(exc),
        )


def _try_push(push: PushProvider, user_id: str, title: str, body: str) -> bool:
    try:
        return push.send(user_id, title, body)
    except Exception:
        logger.warning("push attempt raised", exc_info=True)
        return False
