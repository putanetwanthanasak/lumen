"""Bodies for the buffer API (L66). Money is a JSON string with at most 2 places
(L49, never rounded); unknown keys are rejected."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from app.assistant.plan import Shortfalls
from app.money import MoneyStr
from app.schemas import Id


class BufferOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: Decimal = Field(description="The savings balance: the buffer (L66).")
    monthly_total: Decimal = Field(description="What is owed per month now (L43).")
    months_covered: int | None = Field(
        description="Whole months of current installments the buffer covers; null when "
        "nothing is owed."
    )


class MoveIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # The idempotency key, with the user: a double submit moves the money once.
    client_request_id: Id
    amount: Annotated[MoneyStr, Field(gt=Decimal(0))]


class MovedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: uuid.UUID
    status: Literal["created", "duplicate"]
    amount: Decimal
    balance: Decimal = Field(description="The buffer after the move, as it is now.")


class ShortfallMonthOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    month: str = Field(description='Calendar month, "YYYY-MM".')
    total: Decimal = Field(description="Installments due that month (the L65 total).")
    budget: Decimal
    shortfall: Decimal = Field(description="total - budget.")
    covered_by_buffer: Decimal = Field(
        description="The buffer spent on this month, months in date order."
    )
    still_short: Decimal = Field(description="shortfall - covered_by_buffer.")


class ShortfallsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: Decimal = Field(description="The buffer (savings balance, L66).")
    shortfall: Decimal = Field(description="Sum of total - budget over every month over budget.")
    covered: bool = Field(description="The buffer covers the whole shortfall.")
    still_short: Decimal = Field(description="max(0, shortfall - balance).")
    months: list[ShortfallMonthOut] = Field(
        description="Each month over budget from the current one, at most 600. The totals "
        "above cover every month, shown or not."
    )
    months_truncated: bool

    @classmethod
    def of(cls, result: Shortfalls) -> Self:
        return cls(
            balance=result.buffer.balance,
            shortfall=result.buffer.shortfall,
            covered=result.buffer.covered,
            still_short=result.buffer.still_short,
            months=[
                ShortfallMonthOut(
                    month=str(m.month),
                    total=m.total,
                    budget=result.budget,
                    shortfall=m.shortfall,
                    covered_by_buffer=m.covered_by_buffer,
                    still_short=m.still_short,
                )
                for m in result.months
            ],
            months_truncated=result.months_truncated,
        )
