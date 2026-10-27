"""Bodies for the buffer API (L66). Money is a JSON string with at most 2 places
(L49, never rounded); unknown keys are rejected."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

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
