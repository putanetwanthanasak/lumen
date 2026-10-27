"""POST /demo/payday: run payday (L67) for the X-Demo-User user and a given month.

A demo trigger, not a product endpoint: the router is mounted only when
DEMO_ENDPOINTS_ENABLED is true, so by default the path does not exist (404). 201
for the month's first run, 200 with the stored outcome for any later one (nothing
changes), 409 SETTINGS_REQUIRED without an income and budget.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict
from sqlalchemy.orm import Session

from app.affordability.months import Month
from app.affordability.router import SETTINGS_REQUIRED_ERROR
from app.affordability.service import SettingsRequiredError
from app.api_body import json_body
from app.db import get_session
from app.installments.schemas import parse_month
from app.models import PaydayOutcome
from app.notifications import service as notifications
from app.payday.service import run
from app.providers import get_bank_provider, get_push_provider
from app.providers.base import BankAccountProvider, PushProvider
from app.users import demo_user

router = APIRouter()


class PaydayIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    month: Annotated[date, BeforeValidator(parse_month)]  # "2026-11"


class PaydayOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    month: str
    status: Literal["created", "duplicate"]
    outcome: PaydayOutcome
    month_total: Decimal
    budget: Decimal
    amount: Decimal
    buffer_balance: Decimal


RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"description": "The month already ran: its stored outcome, nothing changed"},
    401: {"description": "No or malformed X-Demo-User"},
    409: {"description": "SETTINGS_REQUIRED: no income and budget"},
}


@router.post("/demo/payday", status_code=201, responses=RESPONSES)
def demo_payday(
    user_id: Annotated[str, Depends(demo_user)],
    body: Annotated[PaydayIn, Depends(json_body(PaydayIn))],
    session: Annotated[Session, Depends(get_session)],
    bank: Annotated[BankAccountProvider, Depends(get_bank_provider)],
    push: Annotated[PushProvider, Depends(get_push_provider)],
) -> JSONResponse:
    try:
        result = run(session, user_id=user_id, month=Month.of(body.month), bank=bank)
    except SettingsRequiredError:
        raise SETTINGS_REQUIRED_ERROR from None
    session.commit()
    if result.notification_id is not None:
        # After commit. Never raises: the run is already recorded (RS-03).
        notifications.deliver(session, result.notification_id, push)
    out = PaydayOut(
        month=str(result.month),
        status="created" if result.created else "duplicate",
        outcome=result.outcome,
        month_total=result.month_total,
        budget=result.budget,
        amount=result.amount,
        buffer_balance=result.buffer_balance,
    )
    return JSONResponse(
        status_code=201 if result.created else 200, content=out.model_dump(mode="json")
    )
