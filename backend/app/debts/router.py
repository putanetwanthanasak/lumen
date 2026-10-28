"""App API for debts (04 section 9)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.affordability.router import SETTINGS_REQUIRED_ERROR
from app.affordability.service import SettingsRequiredError
from app.api_body import query_params
from app.clock import today
from app.db import get_session
from app.debts.months import MonthsOut, MonthsQuery, months_view
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


@router.get(
    "/debts/months",
    responses={
        401: {"description": "No or malformed X-Demo-User"},
        409: {"description": "SETTINGS_REQUIRED: no income and budget for the flags"},
        422: {"description": "count is not a whole number from 1 to 600"},
    },
)
def debt_months(
    user_id: Annotated[str, Depends(demo_user)],
    query: Annotated[MonthsQuery, Depends(query_params(MonthsQuery))],
    session: Annotated[Session, Depends(get_session)],
    day: Annotated[date, Depends(today)],
) -> MonthsOut:
    """Each month from the current one with its total, its L65 flags and the
    installments due in it. Writes nothing."""
    try:
        return months_view(session, user_id, today=day, count=query.count)
    except SettingsRequiredError:
        raise SETTINGS_REQUIRED_ERROR from None
