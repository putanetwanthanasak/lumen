"""Saving rule engine (04 section 7, L63). Pure functions: no I/O, Decimal in and out."""

from dataclasses import dataclass
from decimal import (
    ROUND_DOWN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

from app.models import InstallmentKind
from app.money import decimal_places
from app.rules.config import NEVER_SAVE_KINDS

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
# Numeric(12,2) holds at most 10 integer digits; anything larger is not storable money.
MONEY_LIMIT = Decimal("1E10")
# Explicit context so a caller's global decimal settings cannot change the result.
CONTEXT = Context(prec=28, traps=[InvalidOperation, DivisionByZero, Overflow])


@dataclass(frozen=True)
class PercentRule:
    """L63 (a): an integer percent of the item price, 1 to 100."""

    percent: int


@dataclass(frozen=True)
class FixedRule:
    """L63 (b): a fixed amount per recorded installment, > 0."""

    amount: Decimal


SavingRule = PercentRule | FixedRule


def _require_money(name: str, value: object) -> Decimal:
    if isinstance(value, float):
        raise ValueError(f"{name} is a float; money must be Decimal")
    if type(value) is not Decimal:
        raise ValueError(f"{name} must be Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if decimal_places(value) > 2:
        raise ValueError(f"{name} has more than 2 decimal places")
    if abs(value) >= MONEY_LIMIT:
        raise ValueError(f"{name} must be below {MONEY_LIMIT:,f} in absolute value")
    return value


def _require_rule(rule: object) -> SavingRule:
    match rule:
        case PercentRule(percent=percent):
            # bool is an int subclass, so check the exact type.
            if type(percent) is not int or not 1 <= percent <= 100:
                raise ValueError("rule.percent must be an int from 1 to 100")
        case FixedRule(amount=amount):
            if _require_money("rule.amount", amount) <= 0:
                raise ValueError("rule.amount must be > 0")
        case _:
            raise ValueError(f"rule must be PercentRule or FixedRule, got {type(rule).__name__}")
    return rule


def compute_saving(
    *,
    kind: str,
    item_value: Decimal,
    bank_balance: Decimal,
    rule: SavingRule,
    protected_min: Decimal,
) -> Decimal:
    """Auto-save amount for one installment, or 0.00 when nothing is saved.

    The user's one rule (L63), never combined:
    - PercentRule: round_down(item_value * percent / 100, 0.01); 0.00 means skip.
    - FixedRule: the amount itself, whatever the item value. No minimum, no cap.
    All or nothing: if saving would leave bank_balance below protected_min, save 0.00
    (exactly protected_min left is allowed). cash_withdrawal and cash_loan save 0.00
    (INV-5); the engine enforces this, not each caller.

    Keyword-only because every money argument is a Decimal and a positional swap
    would be silent. Raises ValueError on invalid input; never returns a partial amount.
    """
    for name, money in (
        ("item_value", item_value),
        ("bank_balance", bank_balance),
        ("protected_min", protected_min),
    ):
        _require_money(name, money)
    _require_rule(rule)
    try:
        installment_kind = InstallmentKind(kind)
    except ValueError:
        raise ValueError(f"unknown installment kind: {kind!r}") from None

    if item_value <= 0:
        raise ValueError("item_value must be > 0")
    if protected_min < 0:
        raise ValueError("protected_min must be >= 0")

    if installment_kind in NEVER_SAVE_KINDS:
        return ZERO

    with localcontext(CONTEXT):
        if isinstance(rule, PercentRule):
            saving = (item_value * rule.percent / 100).quantize(CENT, rounding=ROUND_DOWN)
        else:
            saving = rule.amount.quantize(CENT)
        if saving == ZERO:
            return ZERO
        if bank_balance - saving < protected_min:
            return ZERO
        return saving
