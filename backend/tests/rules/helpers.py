from decimal import Decimal

from app.rules.config import load_rules
from app.rules.engine import FixedRule, PercentRule, SavingRule, compute_saving

PROTECTED_MIN = load_rules().safety_net.protected_min_balance
TEN_PERCENT = PercentRule(10)


def save(
    item_value: str,
    rule: SavingRule = TEN_PERCENT,
    *,
    kind: str = "purchase",
    bank_balance: str = "10000.00",
) -> Decimal:
    """compute_saving with the shipped safety net; string inputs keep floats out of tests."""
    return compute_saving(
        kind=kind,
        item_value=Decimal(item_value),
        bank_balance=Decimal(bank_balance),
        rule=rule,
        protected_min=PROTECTED_MIN,
    )


def fixed(amount: str) -> FixedRule:
    return FixedRule(Decimal(amount))
