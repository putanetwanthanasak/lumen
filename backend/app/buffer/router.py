"""GET /buffer and POST /buffer/move-to-main (L66).

The move is 201 when made, 200 with the same body for a repeat of the same request
(nothing moves again), 409 for the same client_request_id with another amount, and
422 AMOUNT_ABOVE_BALANCE when the buffer holds less. Moving out is never blocked
otherwise: no safety net, no limit, no waiting period.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.affordability.router import SETTINGS_REQUIRED_ERROR
from app.affordability.service import SettingsRequiredError
from app.api_body import json_body
from app.assistant.service import buffer_shortfalls
from app.buffer import service
from app.buffer.schemas import BufferOut, MovedOut, MoveIn, ShortfallsOut
from app.clock import today
from app.db import get_session
from app.errors import coded
from app.providers import get_bank_provider
from app.providers.base import BankAccountProvider
from app.users import demo_user

router = APIRouter()

UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {"description": "No or malformed X-Demo-User"}
}
ABOVE_BALANCE = coded(422, "AMOUNT_ABOVE_BALANCE", "the buffer holds less than this amount")


@router.get("/buffer", responses=UNAUTHORIZED)
def read_buffer(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
) -> BufferOut:
    buffer = service.read(session, user_id)
    return BufferOut(
        balance=buffer.balance,
        monthly_total=buffer.monthly_total,
        months_covered=buffer.months_covered,
    )


@router.get(
    "/buffer/shortfalls",
    responses=UNAUTHORIZED
    | {409: {"description": "SETTINGS_REQUIRED: no income and budget to compare against"}},
)
def read_shortfalls(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
    day: Annotated[date, Depends(today)],
) -> ShortfallsOut:
    """The current and upcoming months over budget, with how much of each the buffer
    covers, months in date order. Advice only: nothing moves (L66). Writes nothing."""
    try:
        return ShortfallsOut.of(buffer_shortfalls(session, user_id, today=day))
    except SettingsRequiredError:
        raise SETTINGS_REQUIRED_ERROR from None


@router.post(
    "/buffer/move-to-main",
    status_code=201,
    responses=UNAUTHORIZED
    | {
        200: {"description": "The same request again: the first move, not repeated"},
        409: {"description": "client_request_id already used with another amount"},
        422: {"description": "Invalid body, or AMOUNT_ABOVE_BALANCE"},
    },
)
def move_to_main(
    user_id: Annotated[str, Depends(demo_user)],
    request: Annotated[MoveIn, Depends(json_body(MoveIn))],
    session: Annotated[Session, Depends(get_session)],
    bank: Annotated[BankAccountProvider, Depends(get_bank_provider)],
) -> JSONResponse:
    result = service.move_to_main(session, user_id=user_id, request=request)
    if result is None:
        raise ABOVE_BALANCE  # nothing was written
    session.commit()  # the conflict's audit row commits too
    if result.outcome == service.Outcome.CONFLICT:
        raise HTTPException(status_code=409, detail="client_request_id reused with another amount")
    # After the commit, and on a repeat too: see service.move_to_main.
    service.transfer_to_main(bank, user_id=user_id, request=request, moved=result)
    body = MovedOut(
        transaction_id=result.transaction_id,
        status=result.outcome.value,
        amount=result.amount,
        balance=service.balance(session, user_id),
    )
    status_code = 201 if result.outcome == service.Outcome.CREATED else 200
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
