"""User settings: create, read, replace (L63, L64).

A row from before L63 holds only the auto-save switch and consent, with no profile
and no rule. It counts as "no settings": GET and PUT give 404 and POST fills it in.
"""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import UserSettings
from app.rules.engine import PercentRule
from app.savings.service import saving_rule
from app.user_settings.schemas import (
    FixedRuleBody,
    PercentRuleBody,
    SettingsIn,
    SettingsOut,
    budget_warnings,
)


def _locked(session: Session, user_id: str) -> UserSettings | None:
    return session.get(UserSettings, user_id, with_for_update=True, populate_existing=True)


def _configured(row: UserSettings | None) -> UserSettings | None:
    return row if row is not None and row.saving_mode is not None else None


def read(session: Session, user_id: str) -> UserSettings | None:
    return _configured(session.get(UserSettings, user_id))


def create(session: Session, user_id: str, data: SettingsIn) -> UserSettings | None:
    """Store the user's first settings, or return None if they already have some.

    The bare insert decides between concurrent creates: the second one waits on the
    primary key, does nothing, and then finds the first one's settings under the lock.
    """
    session.execute(pg_insert(UserSettings).values(user_id=user_id).on_conflict_do_nothing())
    row = _locked(session, user_id)
    if row is None or row.saving_mode is not None:
        return None
    return _apply(session, row, data)


def replace(session: Session, user_id: str, data: SettingsIn) -> UserSettings | None:
    """Replace every setting, or return None if the user has none yet."""
    row = _configured(_locked(session, user_id))
    if row is None:
        return None
    return _apply(session, row, data)


def _apply(session: Session, row: UserSettings, data: SettingsIn) -> UserSettings:
    rule = data.saving_rule
    row.income = data.income
    row.payday = data.payday
    row.monthly_installment_budget = data.monthly_installment_budget
    # Switching mode clears the other mode's value (L63: never both).
    row.saving_mode = rule.mode
    row.saving_percent = rule.percent if isinstance(rule, PercentRuleBody) else None
    row.saving_fixed_amount = rule.amount if isinstance(rule, FixedRuleBody) else None
    row.auto_save_enabled = data.auto_save_enabled
    row.leftover_saving_enabled = data.leftover_saving_enabled
    if data.auto_save_enabled and row.consent_at is None:
        row.consent_at = func.now()
    session.flush()
    session.refresh(row)
    return row


def to_out(row: UserSettings) -> SettingsOut:
    """The response body for a configured row."""
    rule = saving_rule(row)
    income, payday, budget = row.income, row.payday, row.monthly_installment_budget
    if rule is None or income is None or payday is None or budget is None:
        raise ValueError("settings row has no profile")  # callers pass configured rows only
    return SettingsOut(
        income=income,
        payday=payday,
        monthly_installment_budget=budget,
        saving_rule=(
            PercentRuleBody(mode="percent", percent=rule.percent)
            if isinstance(rule, PercentRule)
            else FixedRuleBody.model_construct(mode="fixed", amount=rule.amount)
        ),
        auto_save_enabled=row.auto_save_enabled,
        consent_at=row.consent_at,
        leftover_saving_enabled=row.leftover_saving_enabled,
        warnings=budget_warnings(income=income, budget=budget),
    )
