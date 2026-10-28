"""Bodies for the buffer API (L66). Money is a JSON string with at most 2 places
(L49, never rounded); unknown keys are rejected."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.assistant.plan import PreparedState, Shortfalls
from app.installments.schemas import parse_month
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


def _optional_month(value: object) -> date | None:
    return None if value is None else parse_month(value)


class MoveIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # The idempotency key, with the user: a double submit moves the money once.
    client_request_id: Id
    amount: Annotated[MoneyStr, Field(gt=Decimal(0))]
    # The month this money is for, "YYYY-MM" (Session 17), stored as its first day.
    # A label only: it never limits or blocks the move (L66). Absent: a free move.
    for_month: Annotated[date | None, BeforeValidator(_optional_month)] = None


class MovedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: uuid.UUID
    status: Literal["created", "duplicate"]
    amount: Decimal
    for_month: str | None = Field(description='"YYYY-MM", or null for a free move.')
    balance: Decimal = Field(description="The buffer after the move, as it is now.")


class ShortfallMonthOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    month: str = Field(description='Calendar month, "YYYY-MM".')
    total: Decimal = Field(description="Installments due that month (the L65 total).")
    budget: Decimal
    shortfall: Decimal = Field(description="total - budget; a move never changes it.")
    prepared: Decimal = Field(description="Moved to the main account for this month.")
    remaining_gap: Decimal = Field(description="max(0, shortfall - prepared).")
    state: PreparedState
    covered_by_buffer: Decimal = Field(
        description="The buffer spent on this month's remaining gap, months in date order."
    )
    still_short: Decimal = Field(description="remaining_gap - covered_by_buffer.")


class ShortfallsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: Decimal = Field(description="The buffer (savings balance, L66).")
    shortfall: Decimal = Field(description="Sum of total - budget over every month over budget.")
    remaining_gap: Decimal = Field(description="shortfall minus what was prepared for it.")
    covered: bool = Field(description="The buffer covers the whole remaining gap.")
    still_short: Decimal = Field(description="max(0, remaining_gap - balance).")
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
            remaining_gap=result.buffer.remaining_gap,
            covered=result.buffer.covered,
            still_short=result.buffer.still_short,
            months=[
                ShortfallMonthOut(
                    month=str(m.month),
                    total=m.total,
                    budget=result.budget,
                    shortfall=m.shortfall,
                    prepared=m.prepared,
                    remaining_gap=m.remaining_gap,
                    state=m.state,
                    covered_by_buffer=m.covered_by_buffer,
                    still_short=m.still_short,
                )
                for m in result.months
            ],
            months_truncated=result.months_truncated,
        )
