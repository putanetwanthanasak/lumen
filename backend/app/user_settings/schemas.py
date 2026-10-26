"""Request and response bodies for /settings (L63, L64).

Strict like the webhook schemas: unknown keys are rejected, money goes through
app.money (a JSON string with at most 2 places, never rounded, L49), and ints are
real ints (10, not "10", 10.0 or true).
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.money import MoneyStr

BUDGET_ABOVE_ONE_THIRD_OF_INCOME = "BUDGET_ABOVE_ONE_THIRD_OF_INCOME"


class _Body(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PercentRuleBody(_Body):
    mode: Literal["percent"]
    percent: Annotated[int, Field(ge=1, le=100)]


class FixedRuleBody(_Body):
    mode: Literal["fixed"]
    amount: Annotated[MoneyStr, Field(gt=Decimal(0))]


# L63: exactly one mode. Each variant forbids the other's key, so a body that sends
# both a percent and an amount is a 422, never a rule with both active.
SavingRuleBody = Annotated[PercentRuleBody | FixedRuleBody, Field(discriminator="mode")]


class SettingsIn(_Body):
    income: Annotated[MoneyStr, Field(gt=Decimal(0))]
    payday: Annotated[int, Field(ge=1, le=31)]  # day of month
    monthly_installment_budget: MoneyStr
    saving_rule: SavingRuleBody
    auto_save_enabled: bool
    # Turning auto-save on needs explicit consent in the same request (L46 consent).
    auto_save_consent: bool = False
    leftover_saving_enabled: bool  # stored only; its behaviour comes in a later session

    @model_validator(mode="after")
    def _consent_to_auto_save(self) -> Self:
        if self.auto_save_enabled and not self.auto_save_consent:
            raise ValueError("auto_save_enabled requires auto_save_consent")
        return self


class SettingsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    income: Decimal
    payday: int
    monthly_installment_budget: Decimal
    saving_rule: SavingRuleBody
    auto_save_enabled: bool
    consent_at: datetime | None
    leftover_saving_enabled: bool
    warnings: list[str]


def budget_warnings(*, income: Decimal, budget: Decimal) -> list[str]:
    """L64: warn when the monthly installment budget is above one third of income.

    Source: Bank of Thailand financial-literacy guidance that total debt payments
    should not exceed one third of monthly income. It is guidance, not a regulation,
    so the settings are saved either way. Compared as budget * 3 > income, with no
    division to round; exactly one third does not warn.
    """
    return [BUDGET_ABOVE_ONE_THIRD_OF_INCOME] if budget * 3 > income else []
