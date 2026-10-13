"""Saving rule engine (04 section 7). Pure functions: no I/O, Decimal in and out."""

from decimal import ROUND_HALF_UP, Decimal

from app.models import InstallmentKind
from app.rules.config import AutoSaveRules, decimal_places

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _require_decimal(name: str, value: object, max_places: int) -> Decimal:
    if isinstance(value, float):
        raise ValueError(f"{name} is a float; money and rates must be Decimal")
    if type(value) is not Decimal:
        raise ValueError(f"{name} must be Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if decimal_places(value) > max_places:
        raise ValueError(f"{name} has more than {max_places} decimal places")
    return value


def compute_saving(
    *,
    kind: str,
    item_value: Decimal,
    rate: Decimal,
    per_item_cap: Decimal,
    bank_balance: Decimal,
    rules: AutoSaveRules,
    protected_min: Decimal,
) -> Decimal:
    """Auto-save amount for one purchase, or 0.00 when the safety net skips it.

    saving = clamp(round_half_up(item_value * rate, 0.01), min_saving, per_item_cap)
    All or nothing: if saving would leave bank_balance below protected_min, save 0.00.
    Kinds outside rules.applies_to_kinds save 0.00 (INV-5: cash_withdrawal and
    cash_loan never auto-save); the engine enforces this, not each caller.

    Keyword-only because every argument is a Decimal and a positional swap would be
    silent. Raises ValueError on invalid input; never returns a partial amount.
    """
    for name, money in (
        ("item_value", item_value),
        ("per_item_cap", per_item_cap),
        ("bank_balance", bank_balance),
        ("protected_min", protected_min),
    ):
        _require_decimal(name, money, max_places=2)
    _require_decimal("rate", rate, max_places=6)
    try:
        installment_kind = InstallmentKind(kind)
    except ValueError:
        raise ValueError(f"unknown installment kind: {kind!r}") from None

    if item_value <= 0:
        raise ValueError("item_value must be > 0")
    if not rules.min_rate <= rate <= rules.max_rate:
        raise ValueError(f"rate must be within [{rules.min_rate}, {rules.max_rate}]")
    if per_item_cap < rules.min_saving:
        raise ValueError(f"per_item_cap must be >= min_saving ({rules.min_saving})")

    if installment_kind not in rules.applies_to_kinds:
        return ZERO

    raw = (item_value * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    # min_saving > 0 is guaranteed by AutoSaveRules, so saving is always positive here.
    saving = min(max(raw, rules.min_saving), per_item_cap).quantize(CENT)

    if bank_balance - saving < protected_min:
        return ZERO
    return saving
