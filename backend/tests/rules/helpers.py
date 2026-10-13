from decimal import Decimal

from app.rules.config import load_rules
from app.rules.engine import compute_saving

RULES = load_rules()
AUTO_SAVE = RULES.auto_save
PROTECTED_MIN = RULES.safety_net.protected_min_balance


def save(
    item_value: str,
    *,
    rate: str = "0.05",
    per_item_cap: str = "100.00",
    bank_balance: str = "10000.00",
) -> Decimal:
    """compute_saving with the shipped rules; string inputs keep floats out of tests."""
    return compute_saving(
        item_value=Decimal(item_value),
        rate=Decimal(rate),
        per_item_cap=Decimal(per_item_cap),
        bank_balance=Decimal(bank_balance),
        rules=AUTO_SAVE,
        protected_min=PROTECTED_MIN,
    )
