"""POST /consolidation/requests bodies (L70, L71, L72).

Strict like every app API body: unknown keys are rejected, money is a JSON string
with at most 2 places (L49, never rounded), and consent must be the JSON literal
true.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.money import MONEY_MAX, MoneyStr
from app.schemas import Id

MAX_PAYOFFS = 100
MOCK_NOTE = "MOCK bank decision for the Lumen prototype. No bank was asked."


def _must_be_true(consent: bool) -> bool:
    if consent is not True:
        raise ValueError("consent must be true")
    return consent


# Not Literal[True]: that accepts 1 and 1.0 even in strict mode, since 1 == True.
Consent = Annotated[StrictBool, AfterValidator(_must_be_true)]


class PayoffIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    installment_id: uuid.UUID
    # What the user believes it takes to close this debt. It starts the request; the
    # bank decides with its own data (L71).
    payoff_amount: Annotated[MoneyStr, Field(gt=Decimal(0))]


class ConsolidationRequestIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # The idempotency key, with the user: a double submit is decided once.
    client_request_id: Id
    consent: Consent
    payoffs: Annotated[list[PayoffIn], Field(min_length=1, max_length=MAX_PAYOFFS)]

    @model_validator(mode="after")
    def _payoffs_fit(self) -> Self:
        if len({p.installment_id for p in self.payoffs}) != len(self.payoffs):
            raise ValueError("each installment may appear once")
        if sum(p.payoff_amount for p in self.payoffs) > MONEY_MAX:
            raise ValueError("the payoff amounts are too large")
        return self

    def stored_payoffs(self) -> list[dict[str, str]]:
        """The payoffs as stored and compared: sorted by installment, money as text."""
        return sorted(
            (
                {"installment_id": str(p.installment_id), "payoff_amount": str(p.payoff_amount)}
                for p in self.payoffs
            ),
            key=lambda p: p["installment_id"],
        )


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class LoanOut(_Out):
    installment_id: uuid.UUID
    principal: Decimal
    annual_rate: Decimal = Field(description="EXAMPLE yearly rate from config, not a real rate.")
    rate_is_example: Literal[True] = True
    term_months: int
    first_due_month: str
    monthly_payment: Decimal
    total_cost: Decimal = Field(description="monthly_payment x term_months.")


class PayoutOut(_Out):
    installment_id: uuid.UUID
    vendor: str
    contract_id: str
    amount: Decimal


class ConsolidationOut(_Out):
    request_id: uuid.UUID
    client_request_id: str
    status: Literal["created", "duplicate"]
    decision: Literal["approved", "declined"]
    mock: Literal[True] = True
    note: str = MOCK_NOTE
    loan: LoanOut | None = Field(description="The new consolidation_loan; null when declined.")
    payouts: list[PayoutOut] = Field(description="One mock payout per paid-off installment.")
    monthly_total: Decimal = Field(description="What is owed per month now (L43).")


def month_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"
