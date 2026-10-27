"""The payoff plan over the Ledger: loads what assistant.plan needs, nothing more.

Read-only: nothing here writes, so the router never commits.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.affordability.months import Month
from app.affordability.service import counted_installments, require_profile, schedule_of
from app.assistant.plan import Debt, Plan, build
from app.buffer.service import balance
from app.config import Settings
from app.debts.service import remaining
from app.models import CONSOLIDATION_VENDOR, MANUAL_VENDOR, Installment, InstallmentStatus

# No platform reports payments on these, so their earlier months are taken as paid
# (open question 2): a manual entry, and the consolidation loan (review F2).
NO_PAYMENTS_REPORTED = (MANUAL_VENDOR, CONSOLIDATION_VENDOR)


def debt_of(row: Installment) -> Debt:
    return Debt(
        schedule=schedule_of(row),
        ledger_remaining=remaining(row),
        manual=row.vendor in NO_PAYMENTS_REPORTED,
        overdue=row.overdue_days > 0,
        disputed=row.status == InstallmentStatus.DISPUTED,
    )


def debts(session: Session, user_id: str) -> list[Debt]:
    """The counted installments (the L43 owed set, as the L65 verdict counts them)."""
    return [debt_of(row) for row in counted_installments(session, user_id)]


def plan(session: Session, user_id: str, *, today: date, settings: Settings) -> Plan:
    """Raises affordability.service.SettingsRequiredError without an income and
    budget: the plan never guesses them."""
    profile = require_profile(session, user_id)
    return build(
        debts(session, user_id),
        now=Month.of(today),
        income=profile.income,
        budget=profile.budget,
        buffer_balance=balance(session, user_id),
        annual_rate=settings.consolidation_example_annual_rate,
        term=settings.consolidation_example_term_months,
    )
