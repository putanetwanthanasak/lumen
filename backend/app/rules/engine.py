"""Saving rule engine (04 section 7). Pure functions: no I/O, Decimal in and out."""

from decimal import (
    ROUND_HALF_UP,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

from app.models import InstallmentKind
from app.rules.config import AutoSaveRules, decimal_places

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
# Numeric(12,2) holds at most 10 integer digits; anything larger is not storable money.
MONEY_LIMIT = Decimal("1E10")
# Explicit context so a caller's global decimal settings cannot change the result.
CONTEXT = Context(prec=28, traps=[InvalidOperation, DivisionByZero, Overflow])


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


def compute_saving(
    *,
    kind: str,
    item_value: Decimal,
    bank_balance: Decimal,
    rules: AutoSaveRules,
    protected_min: Decimal,
) -> Decimal:
    """Auto-save amount for one purchase, or 0.00 when the safety net skips it.

    saving = clamp(round_half_up(item_value * rules.rate, 0.01), min_saving, max_saving)
    The rule is fixed (L46 + L52: 10%, min 10.00, max 500.00); callers pass no rate or cap.
    All or nothing: if saving would leave bank_balance below protected_min, save 0.00.
    Kinds outside rules.applies_to_kinds save 0.00 (INV-5: cash_withdrawal and
    cash_loan never auto-save); the engine enforces this, not each caller.

    Keyword-only because every argument is a Decimal and a positional swap would be
    silent. Raises ValueError on invalid input; never returns a partial amount.
    """
    for name, money in (
        ("item_value", item_value),
        ("bank_balance", bank_balance),
        ("protected_min", protected_min),
    ):
        _require_money(name, money)
    try:
        installment_kind = InstallmentKind(kind)
    except ValueError:
        raise ValueError(f"unknown installment kind: {kind!r}") from None

    if item_value <= 0:
        raise ValueError("item_value must be > 0")
    if protected_min < 0:
        raise ValueError("protected_min must be >= 0")

    if installment_kind not in rules.applies_to_kinds:
        return ZERO

    with localcontext(CONTEXT):
        raw = (item_value * rules.rate).quantize(CENT, rounding=ROUND_HALF_UP)
        # min_saving > 0 is guaranteed by AutoSaveRules, so saving is always positive here.
        saving = min(max(raw, rules.min_saving), rules.max_saving).quantize(CENT)

        if bank_balance - saving < protected_min:
            return ZERO
        return saving
