"""The buffer (L66): the user's savings balance, and moving it back to the main
account. A move is always the user's own action; nothing here runs on its own.

Moving money out is never blocked (L9 in the planning docs, 05 SV-04). An amount
above the balance is refused (05 SV-05, INV-2): that is not a block, there is
simply not that much to move.
"""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Select, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

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


def _locked_balance(session: Session, user_id: str) -> Decimal | None:
    """SELECT ... FOR UPDATE the user's balance row; None if the user has none. A
    concurrent move for the same user waits here until this one commits."""
    return session.execute(
        select(UserBalance.savings_balance).where(UserBalance.user_id == user_id).with_for_update()
    ).scalar_one_or_none()


def move_to_main(
    session: Session, *, user_id: str, request: MoveIn, bank: BankAccountProvider
) -> Moved | None:
    """Move `request.amount` from the buffer to the main account, once per
    (user, client_request_id). None, with nothing written, when the buffer holds
    less. The caller commits (also after a CONFLICT, for its audit row). Raises
    reconcile.InvariantViolationError after rolling back."""
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
        detail={"client_request_id": request.client_request_id, "amount": str(request.amount)},
    )
    try:
        reconcile.assert_user_invariants(session, user_id)
    except reconcile.InvariantViolationError as exc:
        session.rollback()
        logger.error("reconcile failed, move to main rolled back: %s", exc)
        raise

    # Money moves only once the ledger rows have passed reconcile.
    bank.transfer_from_savings(
        user_id,
        request.amount,
        idempotency_key=savings.move_key(user_id, request.client_request_id),
    )
    return Moved(Outcome.CREATED, transaction_id, request.amount)


def _earlier(user_id: str, client_request_id: str) -> Select[SavingsTransaction]:
    return select(SavingsTransaction).where(
        SavingsTransaction.user_id == user_id,
        SavingsTransaction.client_request_id == client_request_id,
    )


def _resubmitted(
    session: Session, *, user_id: str, request: MoveIn, earlier: SavingsTransaction
) -> Moved:
    """The same amount gets the first answer again; another amount is a conflict
    (as L55), audited."""
    if earlier.amount != request.amount:
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
    return Moved(Outcome.DUPLICATE, earlier.id, earlier.amount)
