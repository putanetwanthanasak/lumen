"""Bodies for GET /bank/main-account (Session 21). Money is a JSON string. There is
no account number in the API: the screen shows a masked placeholder of its own."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.bank.service import MOVEMENTS_LIMIT, Direction
from app.models import SavingsType


class MovementOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    at: datetime = Field(description="When it was recorded, in Bangkok time (+07:00).")
    kind: SavingsType = Field(description="The savings_transactions type, as stored.")
    direction: Direction = Field(description='"in" to the main account, "out" of it.')
    amount: Decimal = Field(description="Always positive; the sign is `direction`.")
    for_month: str | None = Field(
        description='"YYYY-MM": the month a move to main was for, or the payday month of '
        "a leftover saving; null for an auto-save and a free move."
    )


class MainAccountOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: Decimal = Field(description="The main account balance, from the bank provider.")
    movements: list[MovementOut] = Field(
        description=f"Newest first, at most the {MOVEMENTS_LIMIT} newest."
    )
    movements_truncated: bool = Field(description="The user has older movements not listed.")
