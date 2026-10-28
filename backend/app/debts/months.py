"""GET /debts/months: each month from now with its total and the installments due in
it (Session 15A, the "ภาระผ่อนรายเดือน" screen and Home's month card).

The same counted set and the same month_totals as the L65 verdict and the payoff
plan, so a month here always matches "เช็กก่อนผ่อน" and the plan. Read-only.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.affordability.months import Month, Scheduled, month_totals, over_budget, over_one_third
from app.affordability.service import counted_installments, require_profile, schedule_of
from app.api_body import QueryInt
from app.assistant.plan import HORIZON_CAP
from app.models import Installment


class MonthsQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    count: Annotated[QueryInt, Field(ge=1, le=HORIZON_CAP)] | None = None


class _Out(BaseModel):
    # Decimals serialise as JSON strings (L49).
    model_config = ConfigDict(frozen=True)


class MonthInstallment(_Out):
    installment_id: uuid.UUID
    item_name: str
    monthly_amount: Decimal
    installment_no: int = Field(description='"งวดที่ x": 1 in its first due month.')
    installments_total: int = Field(description='"จาก y": the installment\'s months.')
    is_last: bool = Field(description="This is its last due month.")


class MonthDetail(_Out):
    month: str = Field(description='Calendar month, "YYYY-MM".')
    total: Decimal = Field(description="Installments due that month (the L65 total).")
    budget: Decimal
    over_budget: bool
    over_one_third: bool
    installments: list[MonthInstallment] = Field(description="Due that month, in recorded order.")


class MonthsOut(_Out):
    months: list[MonthDetail] = Field(
        description="From the current month: `count` months, or else to the last month an "
        f"owed installment is due (at least one month, at most {HORIZON_CAP})."
    )
    months_truncated: bool = Field(description=f"True when months stops at {HORIZON_CAP}.")


@dataclass(frozen=True)
class _Due:
    row: Installment
    schedule: Scheduled


def _line(due: _Due, month: Month) -> MonthInstallment:
    return MonthInstallment(
        installment_id=due.row.id,
        item_name=due.row.item_name,
        monthly_amount=due.row.monthly_amount,
        installment_no=month.index - due.schedule.first_month.index + 1,
        installments_total=due.schedule.months,
        is_last=month == due.schedule.last_month,
    )


def months_view(session: Session, user_id: str, *, today: date, count: int | None) -> MonthsOut:
    """Raises affordability.service.SettingsRequiredError without an income and
    budget: the flags need them and never guess them."""
    profile = require_profile(session, user_id)
    rows = counted_installments(session, user_id)
    schedules = [schedule_of(row) for row in rows]
    dues = [_Due(row, s) for row, s in zip(rows, schedules, strict=True)]
    now = Month.of(today)
    if count is None:
        last = max((s.last_month.index for s in schedules), default=now.index)
        span = max(last - now.index + 1, 1)
        shown, truncated = min(span, HORIZON_CAP), span > HORIZON_CAP
    else:
        shown, truncated = count, False
    return MonthsOut(
        months=[
            MonthDetail(
                month=str(t.month),
                total=t.total,
                budget=profile.budget,
                over_budget=over_budget(t.total, profile.budget),
                over_one_third=over_one_third(t.total, profile.income),
                installments=[_line(d, t.month) for d in dues if d.schedule.due_in(t.month)],
            )
            for t in month_totals(schedules, first=now, count=shown)
        ],
        months_truncated=truncated,
    )
