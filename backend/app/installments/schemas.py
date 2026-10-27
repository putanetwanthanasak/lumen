"""Request and response bodies for POST /installments (L62).

Strict like the webhook schemas: unknown keys are rejected, money is a JSON string
with at most 2 places (L49, never rounded), and ints are real ints.
"""

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from app.affordability.months import Month, Scheduled
from app.affordability.schemas import VerdictOut
from app.models import InstallmentKind
from app.money import MONEY_MAX, MoneyStr
from app.schemas import MAX_MONTHS, NO_CONTROL_CHARS, Id

MONTH_PATTERN = re.compile(r"([0-9]{4})-(0[1-9]|1[0-2])")
LAST_MONTH_INDEX = 9999 * 12 + 11  # December 9999, as year * 12 + month - 1


def parse_month(value: object) -> date:
    """The first due month, "2026-11", stored as its first day: 2026-11-01."""
    if not isinstance(value, str) or (match := MONTH_PATTERN.fullmatch(value)) is None:
        raise ValueError('must be a month string such as "2026-11"')
    year, month = int(match[1]), int(match[2])
    if year < 1:
        raise ValueError("year must be 0001 or later")
    return date(year, month, 1)


def _recordable_kind(kind: InstallmentKind) -> InstallmentKind:
    """L72: a consolidation loan comes only from an approved consolidation."""
    if kind == InstallmentKind.CONSOLIDATION_LOAN:
        raise ValueError("consolidation_loan is created by an approved consolidation only")
    return kind


class ManualEntryIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # The idempotency key, with the user (L62): a double submit records once.
    client_request_id: Id
    kind: Annotated[InstallmentKind, AfterValidator(_recordable_kind)]
    item_price: Annotated[MoneyStr, Field(gt=Decimal(0))]
    months: Annotated[int, Field(ge=1, le=MAX_MONTHS)]
    monthly_amount: Annotated[MoneyStr, Field(gt=Decimal(0))]
    first_due_month: Annotated[date, BeforeValidator(parse_month)]
    item_name: Annotated[str, Field(max_length=500, pattern=NO_CONTROL_CHARS)] = ""

    @model_validator(mode="after")
    def _schedule_fits(self) -> Self:
        # The schedule total (and so fee_total) must fit Numeric(12,2), or the
        # insert would overflow into a 500 (as S7 for payments).
        if self.months * self.monthly_amount > MONEY_MAX:
            raise ValueError("months * monthly_amount is too large")
        # Review F3: the last due date must exist, or the debt summary cannot compute
        # it (date.max is 9999-12-31).
        first = self.first_due_month
        if first.year * 12 + first.month - 1 + self.months - 1 > LAST_MONTH_INDEX:
            raise ValueError("the schedule ends after 9999-12")
        return self

    @property
    def fee_total(self) -> Decimal:
        """What the schedule adds on top of the price; 0 when it does not cover the
        price (a rounded-down plan such as 3 x 333.33 for 1,000.00)."""
        return max(Decimal("0.00"), self.months * self.monthly_amount - self.item_price)

    @property
    def schedule(self) -> Scheduled:
        """The plan as the affordability check (L65) sees it."""
        return Scheduled(Month.of(self.first_due_month), self.months, self.monthly_amount)


class RecordedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    installment_id: uuid.UUID
    status: Literal["created", "duplicate"]
    saved_amount: Decimal
    monthly_total: Decimal  # L43: every installment owed, this one included
    # L65: the verdict over this entry's term, as the Ledger stands now. Advice only:
    # the entry is recorded whatever it says (rule 6).
    warnings: VerdictOut
