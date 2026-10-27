"""GET /assistant/plan: the payoff assistant's numbers (L69, L70). Writes nothing.

Every number comes from code (assistant.plan). 409 SETTINGS_REQUIRED without an
income and budget, as the L65 preview.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.affordability.router import SETTINGS_REQUIRED_ERROR
from app.affordability.service import SettingsRequiredError
from app.assistant import service
from app.assistant.schemas import PlanOut
from app.clock import today
from app.config import Settings, get_settings
from app.db import get_session
from app.users import demo_user

router = APIRouter()

RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No or malformed X-Demo-User"},
    409: {"description": "SETTINGS_REQUIRED: no income and budget to plan against"},
}


@router.get("/assistant/plan", responses=RESPONSES)
def read_plan(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
    day: Annotated[date, Depends(today)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PlanOut:
    try:
        plan = service.plan(session, user_id, today=day, settings=settings)
    except SettingsRequiredError:
        raise SETTINGS_REQUIRED_ERROR from None
    return PlanOut.of(plan)
