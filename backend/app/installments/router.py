"""POST /installments: the user records an installment before buying (L62).

201 for a new entry, 200 with the same body for a repeat of the same request
(nothing new is saved or pushed), 409 for the same client_request_id with
different fields. Recording never depends on affordability (rule 6).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api_body import json_body
from app.db import get_session
from app.installments.schemas import ManualEntryIn, RecordedOut
from app.installments.service import Outcome, record
from app.notifications import service as notifications
from app.providers import get_bank_provider, get_push_provider
from app.providers.base import BankAccountProvider, PushProvider
from app.users import demo_user

router = APIRouter()

RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"description": "The same request again: the first entry, unchanged"},
    401: {"description": "No or malformed X-Demo-User"},
    409: {"description": "client_request_id already used with different fields"},
}


@router.post("/installments", status_code=201, responses=RESPONSES)
def record_installment(
    user_id: Annotated[str, Depends(demo_user)],
    entry: Annotated[ManualEntryIn, Depends(json_body(ManualEntryIn))],
    session: Annotated[Session, Depends(get_session)],
    bank: Annotated[BankAccountProvider, Depends(get_bank_provider)],
    push: Annotated[PushProvider, Depends(get_push_provider)],
) -> JSONResponse:
    result = record(session, user_id=user_id, entry=entry, bank=bank)
    session.commit()  # the conflict's audit row commits too
    if result.outcome == Outcome.CONFLICT:
        raise HTTPException(status_code=409, detail="client_request_id reused with other fields")
    if result.notification_id is not None:
        # After commit. Never raises: the entry is already recorded (RS-03).
        notifications.deliver(session, result.notification_id, push)
    body = RecordedOut(
        installment_id=result.installment_id,
        status=result.outcome.value,
        saved_amount=result.saved_amount,
        monthly_total=result.monthly_total,
    )
    status_code = 201 if result.outcome == Outcome.CREATED else 200
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
