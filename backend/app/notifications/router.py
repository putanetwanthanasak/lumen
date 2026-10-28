"""GET /notifications: the user's alerts, newest first (Session 15A). Writes nothing.

There is no read or unread state: the count is how many alerts the user has.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import NotificationKind
from app.notifications.service import INBOX_LIMIT, inbox
from app.users import demo_user

router = APIRouter()


class NotificationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    kind: NotificationKind
    title: str = Field(description="Thai text as stored (notifications/copy.py).")
    body: str
    installment_id: uuid.UUID | None = Field(description="Null for payday alerts.")
    created_at: datetime


class NotificationsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    notifications: list[NotificationOut] = Field(
        description=f"Newest first, at most the {INBOX_LIMIT} newest."
    )
    count: int = Field(description="How many alerts the user has in all.")


@router.get("/notifications", responses={401: {"description": "No or malformed X-Demo-User"}})
def read_notifications(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
) -> NotificationsOut:
    rows, count = inbox(session, user_id)
    return NotificationsOut(
        notifications=[
            NotificationOut(
                id=row.id,
                kind=NotificationKind(row.kind),
                title=row.title,
                body=row.body,
                installment_id=row.installment_id,
                created_at=row.created_at,
            )
            for row in rows
        ],
        count=count,
    )
