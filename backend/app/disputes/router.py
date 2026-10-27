"""POST /debts/{installment_id}/not-me (L42).

04 section 9 puts "Not me" on /notifications/{id}/not-me. It is per installment here
(user decision, Session 9): a debt can be reported even if its alert was never seen.
The installment's alert is still marked not_me.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_session
from app.disputes.service import Disputed, ManualEntryRejected, dispute, send_signal
from app.errors import coded
from app.models import DisputeSignalStatus
from app.notifications.copy import vendor_name
from app.providers import get_platform_provider
from app.providers.base import PlatformProvider
from app.users import demo_user

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

# L60 (3), exact wording, chosen by the stored signal status (L60 2). Neither one
# claims Lumen can stop or cancel the platform transaction (L42).
MESSAGE_SENT = (
    "บันทึกการแจ้งของคุณแล้ว และส่งเรื่องให้ {vendor} ตรวจสอบแล้ว "
    "Lumen ยกเลิกรายการแทนคุณไม่ได้ "
    "โปรดติดต่อ {vendor} โดยตรงเพื่อยืนยันว่าไม่ใช่รายการของคุณ"
)
MESSAGE_NOT_SENT = (
    "บันทึกการแจ้งของคุณแล้ว แต่ยังส่งเรื่องให้ {vendor} ไม่สำเร็จ "
    "Lumen ยกเลิกรายการแทนคุณไม่ได้ "
    "โปรดติดต่อ {vendor} โดยตรงโดยเร็ว"
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
    platform_signal: str  # sent / failed (pending only if storing the outcome failed)
    message: str
    contact: Contact


NOT_FOUND = HTTPException(status_code=404, detail="installment not found")
MANUAL_ENTRY = coded(
    409,
    "NOT_ME_UNAVAILABLE_FOR_MANUAL_ENTRY",
    "you recorded this installment yourself; there is no platform to report it to",
)


def _response(result: Disputed, signal_status: str) -> NotMeResponse:
    name = vendor_name(result.vendor)
    contact = MOCK_CONTACTS.get(result.vendor, {})
    sent = signal_status == DisputeSignalStatus.SENT
    return NotMeResponse(
        installment_id=result.installment_id,
        status=result.status,
        disputed_at=result.disputed_at,
        platform_signal=signal_status,
        message=(MESSAGE_SENT if sent else MESSAGE_NOT_SENT).format(vendor=name),
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
        409: {"description": "NOT_ME_UNAVAILABLE_FOR_MANUAL_ENTRY: an entry you recorded (L68)"},
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
    if isinstance(result, ManualEntryRejected):
        session.commit()  # the attempt's audit row
        raise MANUAL_ENTRY
    session.commit()  # the report is recorded even if the platform is down
    signal_status = result.signal_status
    if signal_status != DisputeSignalStatus.SENT:
        # First tap, or a repeat while the platform has not got it (S4): try now.
        signal_status = send_signal(session, report=result, user_id=user_id, platform=platform)
        session.commit()
    return _response(result, signal_status)
