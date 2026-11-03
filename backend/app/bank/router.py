"""GET /bank/main-account: the caller's main account balance and the movements the
system made between it and the buffer (Session 21). Writes nothing."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.affordability.months import Month
from app.bank import service
from app.bank.schemas import MainAccountOut, MovementOut
from app.clock import BANGKOK
from app.db import get_session
from app.models import SavingsTransaction, SavingsType
from app.providers import get_bank_provider
from app.providers.base import BankAccountProvider
from app.users import demo_user

router = APIRouter()


def _month(day: date | None) -> str | None:
    return None if day is None else str(Month.of(day))


def _movement(row: SavingsTransaction) -> MovementOut:
    kind = SavingsType(row.type)
    # Only a withdrawal carries for_month and only a leftover saving a payday month
    # (CHECKs on savings_transactions), so at most one of the two is set.
    return MovementOut(
        id=row.id,
        at=row.created_at.astimezone(BANGKOK),
        kind=kind,
        direction=service.DIRECTION[kind],
        amount=row.amount,
        for_month=_month(row.for_month or row.payday_month),
    )


@router.get("/bank/main-account", responses={401: {"description": "No or malformed X-Demo-User"}})
def read_main_account(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
    bank: Annotated[BankAccountProvider, Depends(get_bank_provider)],
) -> MainAccountOut:
    found = service.movements(session, user_id)
    return MainAccountOut(
        balance=bank.get_balance(user_id),
        movements=[_movement(row) for row in found.rows],
        movements_truncated=found.truncated,
    )
