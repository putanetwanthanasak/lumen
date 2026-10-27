"""The payday run (L67), once per user per month, in the caller's one transaction.

(a) The month's installment total is over the budget: store an alert with the
    shortfall and the buffer balance.
(b) Otherwise, if the user opted in to leftover saving and auto-save is on with
    consent: save budget - total when it is above 0, under the 500.00 safety net,
    all or nothing.

The month total is the L65 one (affordability.months), so the verdict before
buying and the payday outcome count the same installments.

Idempotency: the balance row lock serialises runs (and every money move) for one
user, a run already stored for the month is returned as it is, and the
payday_runs primary key with ON CONFLICT is the second layer. A second run of the
month changes nothing, even if it would now decide differently.
"""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.affordability.months import Month, month_totals
from app.affordability.service import counted_schedules, require_profile
from app.audit import service as audit
from app.buffer.service import balance
from app.ledger import reconcile
from app.models import (
    Actor,
    PaydayOutcome,
    PaydayRun,
    SavingsTransaction,
    SavingsType,
    UserSettings,
)
from app.notifications import service as notifications
from app.notifications.copy import leftover_saved_alert, payday_shortfall_alert
from app.providers.base import BankAccountProvider
from app.rules.config import load_rules
from app.rules.engine import ZERO, compute_leftover_saving
from app.savings import service as savings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Payday:
    month: Month
    created: bool  # False: the month already ran, and this run changed nothing
    outcome: PaydayOutcome
    month_total: Decimal
    budget: Decimal
    amount: Decimal  # the shortfall (over budget) or the saving (leftover saved)
    buffer_balance: Decimal  # after the run
    # The alert this call stored, to push after commit. None on a repeat.
    notification_id: uuid.UUID | None = None


def run(session: Session, *, user_id: str, month: Month, bank: BankAccountProvider) -> Payday:
    """Run payday for (user, month). Raises SettingsRequiredError when the user has
    no income and budget, with nothing written. The caller commits, then pushes.
    Raises reconcile.InvariantViolationError after rolling back."""
    profile = require_profile(session, user_id)
    savings.lock_balance(session, user_id)
    stored = session.execute(_stored(user_id, month)).scalar_one_or_none()
    if stored is not None:
        return _repeat(stored, month)

    [row] = month_totals(counted_schedules(session, user_id), first=month, count=1)
    total, budget = row.total, profile.budget
    key = savings.leftover_key(user_id, str(month))
    amount, outcome = ZERO, PaydayOutcome.LEFTOVER_OFF
    if (moved := bank.applied_to_savings(user_id, key)) is not None:
        # An earlier attempt moved the leftover, then lost its commit. Record what
        # moved: deciding again would see a bank balance that already reflects it
        # (and maybe a changed month total), and could skip or ask for another amount.
        # The run, its response and its alert carry that attempt's decision, whose
        # total was budget - leftover (the month's first decision stands, Session 13
        # open question 7). max() only guards a budget lowered in between.
        amount, outcome = moved, PaydayOutcome.LEFTOVER_SAVED
        total = max(budget - moved, ZERO)
    elif total > budget:
        amount, outcome = total - budget, PaydayOutcome.OVER_BUDGET
    elif total == budget:
        outcome = PaydayOutcome.NO_LEFTOVER
    elif _opted_in(session.get(UserSettings, user_id)):
        amount = compute_leftover_saving(
            budget=budget,
            month_total=total,
            bank_balance=bank.get_balance(user_id),  # read under the balance lock (R3)
            protected_min=load_rules().safety_net.protected_min_balance,
        )
        outcome = PaydayOutcome.LEFTOVER_SAVED if amount > ZERO else PaydayOutcome.SAFETY_NET

    buffer_after = balance(session, user_id) + (
        amount if outcome == PaydayOutcome.LEFTOVER_SAVED else ZERO
    )
    claimed = session.execute(
        pg_insert(PaydayRun)
        .values(
            user_id=user_id,
            month=month.first_day(),
            month_total=total,
            budget=budget,
            outcome=outcome,
            amount=amount,
            buffer_balance=buffer_after,
        )
        .on_conflict_do_nothing(index_elements=[PaydayRun.user_id, PaydayRun.month])
        .returning(PaydayRun.user_id)
    ).scalar_one_or_none()
    if claimed is None:  # the lock makes this a second layer; the key decides
        return _repeat(session.execute(_stored(user_id, month)).scalar_one(), month)

    notification_id = None
    if outcome == PaydayOutcome.OVER_BUDGET:
        kind, title, body = payday_shortfall_alert(
            month=month, total=total, shortfall=amount, buffer=buffer_after
        )
        notification_id = notifications.store_payday_alert(
            session, user_id=user_id, kind=kind, title=title, body=body
        )
    elif outcome == PaydayOutcome.LEFTOVER_SAVED:
        saving = SavingsTransaction(
            user_id=user_id,
            type=SavingsType.LEFTOVER_SAVE,
            amount=amount,
            payday_month=month.first_day(),
        )
        session.add(saving)
        session.flush()
        savings.adjust_balance(session, user_id, amount)
        audit.record(
            session,
            actor=Actor.SYSTEM,
            action="leftover_saved",
            user_id=user_id,
            ref_type="savings_transaction",
            ref_id=str(saving.id),
            detail={"month": str(month), "amount": str(amount), "recovered": moved is not None},
        )
        kind, title, body = leftover_saved_alert(month=month, total=total, leftover=amount)
        notification_id = notifications.store_payday_alert(
            session, user_id=user_id, kind=kind, title=title, body=body
        )

    try:
        reconcile.assert_user_invariants(session, user_id)
    except reconcile.InvariantViolationError as exc:
        session.rollback()
        logger.error("reconcile failed, payday run rolled back: %s", exc)
        raise

    # Money moves only once the ledger rows have passed reconcile.
    if outcome == PaydayOutcome.LEFTOVER_SAVED:
        bank.transfer_to_savings(user_id, amount, idempotency_key=key)
    return Payday(month, True, outcome, total, budget, amount, buffer_after, notification_id)


def _opted_in(settings: UserSettings | None) -> bool:
    """L67: leftover saving on, and auto-save on with consent."""
    return (
        settings is not None
        and settings.leftover_saving_enabled
        and settings.auto_save_enabled
        and settings.consent_at is not None
    )


def _stored(user_id: str, month: Month) -> Select[PaydayRun]:
    return select(PaydayRun).where(
        PaydayRun.user_id == user_id, PaydayRun.month == month.first_day()
    )


def _repeat(row: PaydayRun, month: Month) -> Payday:
    """The stored outcome of the month's run, returned as it is."""
    return Payday(
        month,
        False,
        PaydayOutcome(row.outcome),
        row.month_total,
        row.budget,
        row.amount,
        row.buffer_balance,
    )
