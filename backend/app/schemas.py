"""Webhook payload schemas (04 section 5.3 plus L41, L48, L49).

One frozen model per event type, chosen by `event_type`. Unknown fields are
rejected at every level, money and rates go through app.money (strings only), and
validation is strict (6, not "6" or 6.0). The vendor is not in the body: it comes
from the signed X-Vendor-Id header.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, ClassVar, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.models import InstallmentKind
from app.money import MoneyStr, RateStr

# No C0 control characters (U+0000..U+001F) in any free-text field. Postgres JSONB
# cannot store U+0000, so without this an authenticated NUL would be a 500, not a 422;
# no field in the contract needs tabs or newlines either.
NO_CONTROL_CHARS = r"^[^\x00-\x1f]*$"
Id = Annotated[str, Field(min_length=1, max_length=128, pattern=NO_CONTROL_CHARS)]
Text = Annotated[str, Field(min_length=1, max_length=500, pattern=NO_CONTROL_CHARS)]


class _Payload(BaseModel):
    # strict: no lax coercion ("6" -> 6, 1700000000 -> date); JSON strings still
    # parse into dates, datetimes and enums.
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Contract(_Payload):
    contract_id: Id
    kind: InstallmentKind
    item_name: Text
    principal: Annotated[MoneyStr, Field(gt=Decimal(0))]
    months: Annotated[int, Field(gt=0)]
    monthly_amount: MoneyStr
    fee_total: MoneyStr
    first_due_date: date
    # L41: full debt data, an assumption about the platform API. All required.
    min_payment: MoneyStr
    late_fee_per_period: MoneyStr
    monthly_rate: RateStr
    overdue_days: Annotated[int, Field(ge=0)]


class _Event(_Payload):
    event_type: str
    event_id: Id
    occurred_at: AwareDatetime
    user_ref: Id


class _ContractCreated(_Event):
    KIND: ClassVar[InstallmentKind]  # the only kind this event type may carry
    contract: Contract

    @property
    def contract_id(self) -> str:
        return self.contract.contract_id

    @model_validator(mode="after")
    def _kind_matches_event_type(self) -> Self:
        if self.contract.kind != self.KIND:
            raise ValueError(f"{self.event_type} must carry contract.kind {self.KIND.value!r}")
        return self


class InstallmentCreated(_ContractCreated):
    event_type: Literal["installment_created"]
    KIND = InstallmentKind.PURCHASE


class CashWithdrawalCreated(_ContractCreated):
    event_type: Literal["cash_withdrawal_created"]
    KIND = InstallmentKind.CASH_WITHDRAWAL


class CashLoanCreated(_ContractCreated):
    event_type: Literal["cash_loan_created"]
    KIND = InstallmentKind.CASH_LOAN


class _ContractEvent(_Event):
    contract_id: Id


class PaymentCollected(_ContractEvent):
    event_type: Literal["installment_payment_collected"]
    amount: Annotated[MoneyStr, Field(gt=Decimal(0))]
    installment_no: Annotated[int, Field(ge=1)]


class InstallmentOverdue(_ContractEvent):
    event_type: Literal["installment_overdue"]
    overdue_days: Annotated[int, Field(ge=1)]
    # The platform's cumulative total, not an increment, so a replay cannot double-count.
    late_fees_accrued: MoneyStr


class InstallmentCancelled(_ContractEvent):
    event_type: Literal["installment_cancelled"]
    reason: Text


WebhookEvent = Annotated[
    InstallmentCreated
    | CashWithdrawalCreated
    | CashLoanCreated
    | PaymentCollected
    | InstallmentOverdue
    | InstallmentCancelled,
    Field(discriminator="event_type"),
]

_ADAPTER: TypeAdapter[WebhookEvent] = TypeAdapter(WebhookEvent)


def parse_event(raw: bytes) -> WebhookEvent:
    """Validate a raw JSON body. Raises pydantic.ValidationError (-> 422)."""
    return _ADAPTER.validate_json(raw)


class WebhookAck(BaseModel):
    """Response body (04 section 5.4)."""

    status: Literal["processed", "duplicate", "pending_parent"]
