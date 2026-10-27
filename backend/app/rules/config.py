"""Rule config (04 section 7): rules.json, validated once into Decimals.

Money must be a JSON string. A JSON number such as 500.00 is rejected, because it
would be parsed through float before reaching Decimal. The saving rule itself is
the user's own (L63, in user_settings), so it is not here.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.models import EventType, InstallmentKind
from app.money import MoneyStr

RULES_PATH = Path(__file__).with_name("rules.json")

# Kinds that must never trigger auto-save (INV-5, L72).
NEVER_SAVE_KINDS = frozenset(
    {
        InstallmentKind.CASH_WITHDRAWAL,
        InstallmentKind.CASH_LOAN,
        InstallmentKind.CONSOLIDATION_LOAN,
    }
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SafetyNetRules(_Frozen):
    protected_min_balance: MoneyStr  # non-negative by the money pattern (no sign)


class AlertRules(_Frozen):
    notify_on: tuple[EventType, ...]
    strong_alert_kinds: tuple[InstallmentKind, ...]
    push_max_attempts: int = Field(ge=1, strict=True)


class Rules(_Frozen):
    safety_net: SafetyNetRules
    alerts: AlertRules


def parse_rules(raw: str | bytes) -> Rules:
    """Parse and validate rule config JSON. Raises pydantic.ValidationError."""
    return Rules.model_validate_json(raw)


@lru_cache
def load_rules() -> Rules:
    """The packaged rules.json, read and validated once per process."""
    return parse_rules(RULES_PATH.read_bytes())
