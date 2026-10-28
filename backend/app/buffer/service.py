"""The buffer (L66): the user's savings balance, and moving it back to the main
account. A move is always the user's own action; nothing here runs on its own.

Moving money out is never blocked (L9 in the planning docs, 05 SV-04). An amount
above the balance is refused (05 SV-05, INV-2): that is not a block, there is
simply not that much to move.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import cast

from sqlalchemy import Select, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.affordability.months import Month
from app.audit import service as audit
from app.buffer.schemas import MoveIn
from app.debts.service import summary
from app.ledger import reconcile
from app.models import Actor, SavingsTransaction, SavingsType, UserBalance
from app.providers.base import BankAccountProvider
from app.savings import service as savings

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Buffer:
    balance: Decimal
    monthly_total: Decimal
    months_covered: int | None


def balance(session: Session, user_id: str) -> Decimal:
    """The savings balance, 0.00 for a user who never saved."""
    found = session.execute(
        select(UserBalance.savings_balance).where(UserBalance.user_id == user_id)
    ).scalar_one_or_none()
    return ZERO if found is None else found


def read(session: Session, user_id: str) -> Buffer:
    """The buffer and how many whole months of current installments it covers. The
    total is the L43 monthly total, which is at least the current calendar month's,
    so the months covered are never overstated (Session 13, open question 3)."""
    current = balance(session, user_id)
    total = summary(session, user_id).monthly_total
    # Both positive, so // is the floor; Decimal throughout, no float.
    covered = int(current // total) if total > ZERO else None
    return Buffer(current, total, covered)


class Outcome(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"  # the same request again: nothing moves
    CONFLICT = "conflict"  # the same client_request_id with another amount


@dataclass(frozen=True)
class Moved:
    outcome: Outcome
    transaction_id: uuid.UUID
    amount: Decimal = ZERO
    for_month: date | None = None


def prepared_by_month(session: Session, user_id: str, *, since: Month) -> dict[Month, Decimal]:
    """What the user moved to the main account for each month from `since` on
    (Session 17). Earlier months are over and prepare nothing any more."""
    found = session.execute(
        select(SavingsTransaction.for_month, func.sum(SavingsTransaction.amount))
        .where(
            SavingsTransaction.user_id == user_id,
            SavingsTransaction.type == SavingsType.WITHDRAWAL,
            SavingsTransaction.for_month >= since.first_day(),
        )
        .group_by(SavingsTransaction.for_month)
    ).all()
    # The WHERE leaves out the NULL months of free moves.
    return {Month.of(cast(date, month)): total for month, total in found}


def _locked_balance(session: Session, user_id: str) -> Decimal | None:
    """SELECT ... FOR UPDATE the user's balance row; None if the user has none. A
    concurrent move for the same user waits here until this one commits."""
    return session.execute(
        select(UserBalance.savings_balance).where(UserBalance.user_id == user_id).with_for_update()
    ).scalar_one_or_none()


def move_to_main(session: Session, *, user_id: str, request: MoveIn) -> Moved | None:
    """Record moving `request.amount` from the buffer, once per (user,
    client_request_id). None, with nothing written, when the buffer holds less.
    Raises reconcile.InvariantViolationError after rolling back.

    The caller commits (also after a CONFLICT, for its audit row), then calls
    transfer_to_main for CREATED and DUPLICATE. The ledger commits first: if the
    commit were lost after the bank call, the main account would hold money the
    ledger never withdrew, and a later move could withdraw it again (review round 2
    F1). A bank call that fails after the commit is repeated by the client's retry,
    which gets DUPLICATE, under the same key."""
    current = _locked_balance(session, user_id)
    # The request is looked up first: a repeat of a move that emptied the buffer
    # must get its first answer back, not "above balance".
    earlier = session.execute(_earlier(user_id, request.client_request_id)).scalar_one_or_none()
    if earlier is not None:
        return _resubmitted(session, user_id=user_id, request=request, earlier=earlier)
    if current is None or request.amount > current:
        return None

    # Under the balance lock no other move for this user can be in between; the
    # partial UNIQUE index is the second layer if that ever stops being true.
    transaction_id = session.execute(
        pg_insert(SavingsTransaction)
        .values(
            user_id=user_id,
            type=SavingsType.WITHDRAWAL,
            amount=request.amount,
            client_request_id=request.client_request_id,
            for_month=request.for_month,
        )
        .on_conflict_do_nothing(
            index_elements=[SavingsTransaction.user_id, SavingsTransaction.client_request_id],
            index_where=text("client_request_id IS NOT NULL"),
        )
        .returning(SavingsTransaction.id)
    ).scalar_one_or_none()
    if transaction_id is None:
        earlier = session.execute(_earlier(user_id, request.client_request_id)).scalar_one()
        return _resubmitted(session, user_id=user_id, request=request, earlier=earlier)

    savings.adjust_balance(session, user_id, -request.amount)
    audit.record(
        session,
        actor=Actor.USER,
        action="buffer_moved_to_main",
        user_id=user_id,
        ref_type="savings_transaction",
        ref_id=str(transaction_id),
        detail={
            "client_request_id": request.client_request_id,
            "amount": str(request.amount),
            "for_month": None if request.for_month is None else str(Month.of(request.for_month)),
        },
    )
    try:
        reconcile.assert_user_invariants(session, user_id)
    except reconcile.InvariantViolationError as exc:
        session.rollback()
        logger.error("reconcile failed, move to main rolled back: %s", exc)
        raise
    return Moved(Outcome.CREATED, transaction_id, request.amount, request.for_month)


def transfer_to_main(
    bank: BankAccountProvider, *, user_id: str, request: MoveIn, moved: Moved
) -> None:
    """Credit the main account for a committed move. The key is the request's, so a
    repeat (DUPLICATE) moves nothing more if the first call got through."""
    bank.transfer_from_savings(
        user_id, moved.amount, idempotency_key=savings.move_key(user_id, request.client_request_id)
    )


def _earlier(user_id: str, client_request_id: str) -> Select[SavingsTransaction]:
    return select(SavingsTransaction).where(
        SavingsTransaction.user_id == user_id,
        SavingsTransaction.client_request_id == client_request_id,
    )


def _resubmitted(
    session: Session, *, user_id: str, request: MoveIn, earlier: SavingsTransaction
) -> Moved:
    """The same amount and month get the first answer again; another amount or
    another month is a conflict (as L55), audited."""
    if (earlier.amount, earlier.for_month) != (request.amount, request.for_month):
        audit.record(
            session,
            actor=Actor.USER,
            action="client_request_id_reused",
            user_id=user_id,
            ref_type="savings_transaction",
            ref_id=str(earlier.id),
            detail={"client_request_id": request.client_request_id},
        )
        return Moved(Outcome.CONFLICT, earlier.id)
    return Moved(Outcome.DUPLICATE, earlier.id, earlier.amount, earlier.for_month)
