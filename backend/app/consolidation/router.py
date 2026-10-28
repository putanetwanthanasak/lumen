"""POST /consolidation/requests: ask the (mock) bank to consolidate (L70, L71, L72).

201 with the decision for the request's first submit; 200 with the same body for a
repeat (nothing is decided or paid again); 409 for the same client_request_id with
other payoffs, for NOT_ELIGIBLE (with the reason) and for SETTINGS_REQUIRED; 422
for an invalid body, including consent that is not true. Advice only elsewhere: this
is the user's own request, made with consent, and nothing else is ever blocked.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.affordability.router import SETTINGS_REQUIRED_ERROR
from app.affordability.service import SettingsRequiredError
from app.api_body import json_body
from app.clock import today
from app.config import Settings, get_settings
from app.consolidation import service
from app.consolidation.schemas import (
    ConsolidationOut,
    ConsolidationRequestIn,
    LoanOut,
    PayoutOut,
    month_of,
)
from app.db import get_session
from app.debts.service import summary
from app.errors import coded
from app.notifications import service as notifications
from app.providers import get_consolidation_bank, get_push_provider
from app.providers.base import ConsolidationBankProvider, PushProvider
from app.users import demo_user

router = APIRouter()

REUSED = coded(409, "CLIENT_REQUEST_ID_REUSED", "client_request_id already used with other payoffs")
RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"description": "The same request again: its first decision, nothing repeated"},
    401: {"description": "No or malformed X-Demo-User"},
    409: {
        "description": "NOT_ELIGIBLE (with the reason), CLIENT_REQUEST_ID_REUSED, "
        "or SETTINGS_REQUIRED"
    },
    422: {"description": "Invalid body, or consent is not true"},
}


def not_eligible(reason: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "NOT_ELIGIBLE",
            "message": "consolidation is not available now",
            "reason": reason,
        },
    )


@router.post("/consolidation/requests", status_code=201, responses=RESPONSES)
def submit_request(
    user_id: Annotated[str, Depends(demo_user)],
    body: Annotated[ConsolidationRequestIn, Depends(json_body(ConsolidationRequestIn))],
    session: Annotated[Session, Depends(get_session)],
    day: Annotated[date, Depends(today)],
    settings: Annotated[Settings, Depends(get_settings)],
    bank: Annotated[ConsolidationBankProvider, Depends(get_consolidation_bank)],
    push: Annotated[PushProvider, Depends(get_push_provider)],
) -> JSONResponse:
    try:
        result = service.submit(
            session, user_id=user_id, body=body, today=day, settings=settings, bank=bank
        )
    except SettingsRequiredError:
        raise SETTINGS_REQUIRED_ERROR from None
    session.commit()  # a refusal's audit row commits too
    if isinstance(result, service.Conflict):
        raise REUSED
    if isinstance(result, service.NotEligible):
        raise not_eligible(result.reason)
    # The alert first: deliver never raises, and a payout that fails must not drop the
    # alert for a new debt (review F1).
    if result.notification_id is not None:
        notifications.deliver(session, result.notification_id, push)
    # After the commit, and on a repeat too: see the service module.
    service.pay_out(bank, result.payouts)
    request, loan = result.request, result.loan
    out = ConsolidationOut(
        request_id=request.id,
        client_request_id=request.client_request_id,
        status="created" if result.created else "duplicate",
        decision="approved" if loan is not None else "declined",
        loan=None
        if loan is None
        else LoanOut(
            installment_id=loan.id,
            principal=loan.principal,
            annual_rate=request.annual_rate.normalize(),  # 0.180000 -> 0.18
            term_months=loan.months,
            first_due_month=month_of(loan.first_due_date),
            monthly_payment=loan.monthly_amount,
            total_cost=request.total_cost,
        ),
        payouts=[
            PayoutOut(
                installment_id=p.installment_id,
                vendor=p.vendor,
                contract_id=p.contract_id,
                amount=p.amount,
            )
            for p in sorted(result.payouts, key=lambda p: str(p.installment_id))
        ],
        monthly_total=summary(session, user_id).monthly_total,
    )
    return JSONResponse(
        status_code=201 if result.created else 200, content=out.model_dump(mode="json")
    )
