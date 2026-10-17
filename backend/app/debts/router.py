"""App API for debts (04 section 9)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.debts.service import DebtSummary, summary
from app.users import demo_user

router = APIRouter()


@router.get("/debts/summary", responses={401: {"description": "No or malformed X-Demo-User"}})
def debt_summary(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
) -> DebtSummary:
    """Every installment of the user with its status, plus the totals over those still
    owed (`active` or `disputed` with something left to pay).

    `debt_free_date` is the scheduled final due date from the installment plans, not a
    prediction: it does not move with early or late payments.
    """
    return summary(session, user_id)
