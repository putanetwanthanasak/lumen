"""App API for the user's settings (L63, L64): POST creates, GET reads, PUT replaces.

A budget above one third of income is still saved (200 or 201); the response
carries the warning code instead (L64, advisory only).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api_body import json_body
from app.db import get_session
from app.user_settings import service
from app.user_settings.schemas import SettingsIn, SettingsOut
from app.users import demo_user

router = APIRouter()

NOT_FOUND = HTTPException(status_code=404, detail="settings not found")
UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {"description": "No or malformed X-Demo-User"}
}


@router.post(
    "/settings",
    status_code=201,
    responses=UNAUTHORIZED | {409: {"description": "Settings already exist; use PUT"}},
)
def create_settings(
    user_id: Annotated[str, Depends(demo_user)],
    data: Annotated[SettingsIn, Depends(json_body(SettingsIn))],
    session: Annotated[Session, Depends(get_session)],
) -> SettingsOut:
    row = service.create(session, user_id, data)
    if row is None:
        raise HTTPException(status_code=409, detail="settings already exist")
    out = service.to_out(row)
    session.commit()
    return out


@router.get("/settings", responses=UNAUTHORIZED | {404: {"description": "No settings yet"}})
def read_settings(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
) -> SettingsOut:
    row = service.read(session, user_id)
    if row is None:
        raise NOT_FOUND
    return service.to_out(row)


@router.put("/settings", responses=UNAUTHORIZED | {404: {"description": "No settings yet"}})
def replace_settings(
    user_id: Annotated[str, Depends(demo_user)],
    data: Annotated[SettingsIn, Depends(json_body(SettingsIn))],
    session: Annotated[Session, Depends(get_session)],
) -> SettingsOut:
    row = service.replace(session, user_id, data)
    if row is None:
        raise NOT_FOUND
    out = service.to_out(row)
    session.commit()
    return out
