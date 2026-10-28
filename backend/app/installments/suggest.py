"""The 0% monthly amount the "เช็กก่อนผ่อน" form suggests (Session 15A). Pure.

price / months rounded UP to the satang, so the payments never add up to less than
the price. It is only a starting value: the user types what their app charges.
"""

from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api_body import QueryInt
from app.money import MONEY_MAX, MoneyStr
from app.schemas import MAX_MONTHS

CENT = Decimal("0.01")


def suggested_monthly(price: Decimal, months: int) -> Decimal:
    """price / months, rounded UP to 0.01. An inexact quotient is at least
    1/600 satang above the satang below it, well inside 28 digits for any
    Numeric(12,2) price, so ROUND_CEILING always sees it."""
    with localcontext() as ctx:
        ctx.prec = 28
        return (price / months).quantize(CENT, rounding=ROUND_CEILING)


class SuggestIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    item_price: Annotated[MoneyStr, Field(gt=Decimal(0))]
    months: Annotated[QueryInt, Field(ge=1, le=MAX_MONTHS)]

    @model_validator(mode="after")
    def _recordable(self) -> Self:
        # The suggestion must be something POST /installments accepts (its own check).
        if self.months * suggested_monthly(self.item_price, self.months) > MONEY_MAX:
            raise ValueError("months * monthly_amount is too large")
        return self


class SuggestedMonthlyOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    monthly_amount: Decimal = Field(description="item_price / months, rounded UP to 0.01.")
