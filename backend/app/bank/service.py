"""The main account's recent movements (Session 21): money the system moved between
the user's main account and the buffer. Read only.

Every row of savings_transactions is a transfer that happened: a skipped saving
(safety net, consent off, cash kinds) writes no row. Salary is not recorded anywhere,
so it is not listed.
"""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SavingsTransaction, SavingsType

MOVEMENTS_LIMIT = 20


class Direction(StrEnum):
    IN = "in"  # into the main account
    OUT = "out"  # out of the main account


# Auto-save and the payday leftover take from the main account into the buffer; a
# withdrawal from the buffer (POST /buffer/move-to-main, L66) lands in the main account.
DIRECTION: dict[SavingsType, Direction] = {
    SavingsType.AUTO_SAVE: Direction.OUT,
    SavingsType.LEFTOVER_SAVE: Direction.OUT,
    SavingsType.WITHDRAWAL: Direction.IN,
}


@dataclass(frozen=True)
class Movements:
    rows: list[SavingsTransaction]
    truncated: bool


def movements(session: Session, user_id: str, *, limit: int = MOVEMENTS_LIMIT) -> Movements:
    """The user's newest `limit` movements, newest first, and whether there are more."""
    rows = list(
        session.execute(
            select(SavingsTransaction)
            .where(SavingsTransaction.user_id == user_id)
            .order_by(SavingsTransaction.created_at.desc(), SavingsTransaction.id.desc())
            .limit(limit + 1)
        ).scalars()
    )
    return Movements(rows=rows[:limit], truncated=len(rows) > limit)
