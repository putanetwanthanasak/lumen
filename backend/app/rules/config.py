"""Rule config (04 section 7): rules.json, validated once into Decimals.

Money and rates must be JSON strings. A JSON number such as 0.05 is rejected,
because it would be parsed through float before reaching Decimal.
"""

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.models import EventType, InstallmentKind

RULES_PATH = Path(__file__).with_name("rules.json")

# Kinds that must never trigger auto-save (INV-5).
NEVER_SAVE_KINDS = frozenset({InstallmentKind.CASH_WITHDRAWAL, InstallmentKind.CASH_LOAN})


def decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):  # NaN / Infinity have no decimal places
        raise ValueError("must be finite")
    return max(0, -exponent)


def _decimal_from_string(max_places: int) -> Callable[[object], Decimal]:
    def parse(value: object) -> Decimal:
        if not isinstance(value, str):
            raise ValueError(f'must be a JSON string such as "0.05", got {type(value).__name__}')
        try:
            result = Decimal(value)
        except InvalidOperation:
            raise ValueError(f"not a decimal: {value!r}") from None
        if not result.is_finite():
            raise ValueError("must be finite")
        if decimal_places(result) > max_places:
            raise ValueError(f"at most {max_places} decimal places")
        return result

    return parse


# Places match the DB columns: money Numeric(12,2), rates Numeric(7,6).
MoneyStr = Annotated[Decimal, BeforeValidator(_decimal_from_string(2))]
RateStr = Annotated[Decimal, BeforeValidator(_decimal_from_string(6))]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AutoSaveRules(_Frozen):
    """The fixed saving rule (L46 + L52). Not user-configurable."""

    rate: RateStr
    min_saving: MoneyStr
    max_saving: MoneyStr
    rounding: Literal["ROUND_HALF_UP"]
    applies_to_kinds: tuple[InstallmentKind, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not 0 < self.rate <= 1:
            raise ValueError("rate must be within (0, 1]")
        if self.min_saving <= 0:
            raise ValueError("min_saving must be > 0")
        if self.max_saving < self.min_saving:
            raise ValueError("max_saving must be >= min_saving")
        if NEVER_SAVE_KINDS & set(self.applies_to_kinds):
            raise ValueError("cash_withdrawal and cash_loan must never trigger auto-save (INV-5)")
        return self


class SafetyNetRules(_Frozen):
    protected_min_balance: MoneyStr

    @model_validator(mode="after")
    def _non_negative(self) -> Self:
        if self.protected_min_balance < 0:
            raise ValueError("protected_min_balance must be >= 0")
        return self


class AlertRules(_Frozen):
    notify_on: tuple[EventType, ...]
    strong_alert_kinds: tuple[InstallmentKind, ...]
    push_max_attempts: int = Field(ge=1, strict=True)


class Rules(_Frozen):
    auto_save: AutoSaveRules
    safety_net: SafetyNetRules
    alerts: AlertRules


def parse_rules(raw: str | bytes) -> Rules:
    """Parse and validate rule config JSON. Raises pydantic.ValidationError."""
    return Rules.model_validate_json(raw)


@lru_cache
def load_rules() -> Rules:
    """The packaged rules.json, read and validated once per process."""
    return parse_rules(RULES_PATH.read_bytes())
