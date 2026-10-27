"""The L65 affordability check over the Ledger, for a preview or a recorded entry.

Which installments count: the same ones as the L43 monthly total (debts.service:
active or disputed, with something left to pay), so the verdict and the alerts
never disagree about what is owed. Each counts its full monthly amount in every
month of its schedule, even if partly prepaid: a warning should overstate, not
understate (Session 13, open question 1). Every row has a first due date (NOT
NULL); it is placed in the calendar month that date falls in.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.affordability.months import (
    Month,
    MonthTotal,
    Scheduled,
    Verdict,
    month_totals,
    verdict,
)
from app.debts.service import OWED_STATUSES, still_owed, summary
from app.models import Installment, UserSettings

SETTINGS_REQUIRED = "SETTINGS_REQUIRED"


class SettingsRequiredError(Exception):
    """The user has no income and budget to check against. Never guess them."""


@dataclass(frozen=True)
class Profile:
    income: Decimal
    budget: Decimal


@dataclass(frozen=True)
class Assessment:
    verdict: Verdict
    rows: list[MonthTotal]
    profile: Profile
    monthly_total: Decimal  # L43: what is owed per month now


def require_profile(session: Session, user_id: str) -> Profile:
    """The user's income and budget (L63 profile), or SettingsRequiredError when
    there are no settings or only a row from before L63."""
    settings = session.get(UserSettings, user_id)
    if settings is None or settings.income is None or settings.monthly_installment_budget is None:
        raise SettingsRequiredError
    return Profile(settings.income, settings.monthly_installment_budget)


def counted_installments(session: Session, user_id: str) -> list[Installment]:
    """The user's installments that count toward a month total (the L43 owed set)."""
    rows = session.execute(
        select(Installment)
        .where(Installment.user_id == user_id, Installment.status.in_(OWED_STATUSES))
        .order_by(Installment.created_at, Installment.id)
    ).scalars()
    return [row for row in rows if still_owed(row)]


def schedule_of(row: Installment) -> Scheduled:
    return Scheduled(Month.of(row.first_due_date), row.months, row.monthly_amount)


def counted_schedules(session: Session, user_id: str) -> list[Scheduled]:
    """The user's installments that count toward a month total, as plain schedules."""
    return [schedule_of(row) for row in counted_installments(session, user_id)]


def assess(
    session: Session,
    user_id: str,
    term: Scheduled,
    profile: Profile,
    *,
    include_candidate: bool,
) -> Assessment:
    """The verdict over the term of one plan. A preview includes the plan as the
    candidate; a recorded entry is already in the Ledger, so it must not be added
    a second time."""
    candidate = term
    rows = month_totals(
        counted_schedules(session, user_id),
        first=candidate.first_month,
        count=candidate.months,
        candidate=candidate if include_candidate else None,
    )
    return Assessment(
        verdict=verdict(rows, income=profile.income, budget=profile.budget),
        rows=rows,
        profile=profile,
        monthly_total=summary(session, user_id).monthly_total,
    )
