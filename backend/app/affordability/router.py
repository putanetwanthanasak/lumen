"""POST /installments/preview: "think before you buy" (L65). Writes nothing.

The same body as POST /installments, so a client can preview exactly what it is
about to record. The verdict is advice only; recording never depends on it (rule 6).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.affordability.schemas import PreviewOut, VerdictOut
from app.affordability.service import (
    SETTINGS_REQUIRED,
    SettingsRequiredError,
    assess,
    require_profile,
)
from app.api_body import json_body
from app.db import get_session
from app.errors import coded
from app.installments.schemas import ManualEntryIn
from app.installments.service import reported_saving
from app.providers import get_bank_provider
from app.providers.base import BankAccountProvider
from app.savings.service import manual_transfer_key, would_save
from app.users import demo_user

router = APIRouter()

SETTINGS_REQUIRED_ERROR = coded(
    409, SETTINGS_REQUIRED, "set income and budget with POST /settings first"
)
RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No or malformed X-Demo-User"},
    409: {"description": "SETTINGS_REQUIRED: no income and budget to check against"},
}


@router.post("/installments/preview", responses=RESPONSES)
def preview_installment(
    user_id: Annotated[str, Depends(demo_user)],
    entry: Annotated[ManualEntryIn, Depends(json_body(ManualEntryIn))],
    session: Annotated[Session, Depends(get_session)],
    bank: Annotated[BankAccountProvider, Depends(get_bank_provider)],
) -> PreviewOut:
    """The month-by-month verdict if this entry were recorded, and what recording it
    would save. Nothing is written: the session is never committed."""
    try:
        profile = require_profile(session, user_id)
    except SettingsRequiredError:
        raise SETTINGS_REQUIRED_ERROR from None
    verdict = VerdictOut.of(
        assess(session, user_id, entry.schedule, profile, include_candidate=True)
    )
    # A repeat of a recorded request saves nothing new: POST reports its first answer.
    saving = reported_saving(session, user_id=user_id, entry=entry)
    if saving is None:
        saving = would_save(
            session,
            user_id=user_id,
            kind=entry.kind,
            item_price=entry.item_price,
            transfer_key=manual_transfer_key(user_id, entry.client_request_id),
            bank=bank,
        )
    return PreviewOut(**verdict.model_dump(), saving_if_recorded=saving)
