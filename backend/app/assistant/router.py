"""GET /assistant/plan: the payoff assistant's numbers (L69, L70), and GET
/assistant/summary: Home's card, those numbers in a few Thai lines (Session 18).
Neither writes anything.

Every number comes from code (assistant.plan); the summary's model only words them,
behind the grounding check (assistant.summary). 409 SETTINGS_REQUIRED without an
income and budget, as the L65 preview.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.affordability.router import SETTINGS_REQUIRED_ERROR
from app.affordability.service import SettingsRequiredError
from app.ai.provider import Writer, get_summary_writer
from app.assistant import service, summary
from app.assistant.schemas import PlanOut, SummaryOut
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


@router.get("/assistant/summary", responses=RESPONSES)
def read_summary(
    user_id: Annotated[str, Depends(demo_user)],
    session: Annotated[Session, Depends(get_session)],
    day: Annotated[date, Depends(today)],
    settings: Annotated[Settings, Depends(get_settings)],
    writer: Annotated[Writer | None, Depends(get_summary_writer)],
    cache: Annotated[summary.SummaryCache, Depends(summary.get_summary_cache)],
) -> SummaryOut:
    """Always 200 with text once settings exist: without a key, on a timeout (8 s), on
    any API error or when the check refuses the model's text, `text` is the fixed
    template from the same numbers. `reason` says which."""
    try:
        facts = summary.load_facts(session, user_id, today=day, settings=settings)
    except SettingsRequiredError:
        raise SETTINGS_REQUIRED_ERROR from None
    # End the read before the model call, so no connection sits idle in a transaction
    # for up to 8 s. Nothing was written: the commit only ends the snapshot.
    session.commit()
    result = summary.summarize(facts, user_id=user_id, writer=writer, cache=cache)
    return SummaryOut(text=result.text, source=result.source, reason=result.reason)
