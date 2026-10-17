"""POST /debts/{installment_id}/not-me (L42).

04 section 9 puts "Not me" on /notifications/{id}/not-me. It is per installment here
(user decision, Session 9): a debt can be reported even if its alert was never seen.
The installment's alert is still marked not_me.
"""

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_session
from app.disputes.service import Disputed, dispute
from app.notifications.copy import vendor_name
from app.providers import get_platform_provider
from app.providers.base import PlatformProvider
from app.users import demo_user

logger = logging.getLogger(__name__)

router = APIRouter()

MOCK_LABEL = "MOCK DATA for the Lumen prototype. Not a real contact channel."

# Clearly fake: a reserved .example domain and an all-zero number.
MOCK_CONTACTS = {
    "shopdemo": {
        "phone": "000-000-0000",
        "url": "https://help.shopdemo.example/report",
        "hours": "ทุกวัน 09:00-18:00 (mock)",
    },
}

MESSAGE = (
    "บันทึกแล้วว่ารายการนี้ไม่ใช่คุณ และส่งเรื่องให้ {vendor} ตรวจสอบแล้ว "
    "Lumen หยุดหรือยกเลิกรายการแทนไม่ได้ กรุณาติดต่อ {vendor} โดยตรงตามช่องทางด้านล่าง"
)


class Contact(BaseModel):
    model_config = ConfigDict(frozen=True)

    mock: bool = True
    label: str = MOCK_LABEL
    vendor: str
    phone: str | None
    url: str | None
    hours: str | None


class NotMeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    installment_id: uuid.UUID
    status: str
    disputed_at: datetime
    message: str
    contact: Contact


NOT_FOUND = HTTPException(status_code=404, detail="installment not found")


def _response(result: Disputed) -> NotMeResponse:
    name = vendor_name(result.vendor)
    contact = MOCK_CONTACTS.get(result.vendor, {})
    return NotMeResponse(
        installment_id=result.installment_id,
        status=result.status,
        disputed_at=result.disputed_at,
        message=MESSAGE.format(vendor=name),
        contact=Contact(
            vendor=name,
            phone=contact.get("phone"),
            url=contact.get("url"),
            hours=contact.get("hours"),
        ),
    )


@router.post(
    "/debts/{installment_id}/not-me",
    responses={
        401: {"description": "No or malformed X-Demo-User"},
        404: {"description": "No such installment for this user (another user's looks the same)"},
    },
)
def not_me(
    installment_id: str,
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
    platform: Annotated[PlatformProvider, Depends(get_platform_provider)],
) -> NotMeResponse:
    """Report the installment as not yours. Repeats return the same answer.

    Lumen tells the platform and shows its contact channel; it cannot stop or reverse
    the platform transaction.
    """
    try:
        parsed = uuid.UUID(installment_id)
    except ValueError:
        raise NOT_FOUND from None  # same answer as an unknown id: nothing to probe
    result = dispute(session, user_id=user_id, installment_id=parsed)
    if result is None:
        raise NOT_FOUND
    session.commit()
    if result.first_report:
        # After commit, once: the report is recorded even if the platform is down.
        try:
            platform.signal_dispute(
                vendor=result.vendor, contract_id=result.contract_id, user_id=user_id
            )
        except Exception:
            logger.exception("dispute signal failed for installment %s", result.installment_id)
    return _response(result)
