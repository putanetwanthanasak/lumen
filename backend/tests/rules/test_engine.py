"""RE-xx unit tests for compute_saving (05 section 4.1, revised for L63).

L63 replaces L46 + L52: the user picks exactly one rule. Percent is an integer 1 to
100 of the item price, rounded DOWN to the cent, and 0.00 means skip. Fixed is the
amount itself. No minimum, no cap. The 500.00 safety net and INV-5 stay.
"""

from decimal import Decimal, localcontext
from typing import Any

import pytest

from app.rules.engine import FixedRule, PercentRule, SavingRule, compute_saving
from tests.rules.helpers import PROTECTED_MIN, TEN_PERCENT, fixed, save

BOTH_MODES = [pytest.param(TEN_PERCENT, id="percent"), pytest.param(fixed("50.00"), id="fixed")]


def test_RE_01_percent_of_item_price() -> None:
    assert save("500.00", PercentRule(10)) == Decimal("50.00")


@pytest.mark.parametrize(
    ("item", "percent", "expected"),
    [
        ("99.99", 1, "0.99"),  # 0.9999: DOWN 0.99, HALF_UP 1.00
        ("33.33", 15, "4.99"),  # 4.9995: DOWN 4.99, HALF_UP 5.00
        ("10.01", 33, "3.30"),  # 3.3033: below half, the same in every mode
        ("100.05", 10, "10.00"),  # 10.005: DOWN 10.00, HALF_UP 10.01
        ("4999.95", 10, "499.99"),  # 499.995: DOWN 499.99, HALF_UP 500.00
    ],
)
def test_RE_02_percent_rounds_down_to_the_cent(item: str, percent: int, expected: str) -> None:
    assert save(item, PercentRule(percent)) == Decimal(expected)


@pytest.mark.parametrize(("item", "percent"), [("0.99", 1), ("0.01", 99), ("0.09", 10)])
def test_RE_03_percent_result_zero_is_skipped(item: str, percent: int) -> None:
    assert save(item, PercentRule(percent)) == Decimal("0.00")


def test_RE_03a_smallest_percent_saving_is_one_cent() -> None:
    assert save("1.00", PercentRule(1)) == Decimal("0.01")


@pytest.mark.parametrize("percent", [1, 100])
def test_RE_03b_percent_bounds_accepted(percent: int) -> None:
    assert save("200.00", PercentRule(percent)) == Decimal(2 * percent).quantize(Decimal("0.01"))


@pytest.mark.parametrize("item", ["10.00", "500.00", "1000000.00"])
def test_RE_04_fixed_is_the_amount_whatever_the_price(item: str) -> None:
    # No minimum and no per-purchase cap (L63), even above the item price.
    assert save(item, fixed("50.00")) == Decimal("50.00")


def test_RE_04a_smallest_fixed_amount() -> None:
    assert save("500.00", fixed("0.01")) == Decimal("0.01")


def test_RE_05_no_cap_on_percent() -> None:
    # The old 500.00 cap is gone: 10% of 20,000.00 saves all 2,000.00.
    assert save("20000.00", PercentRule(10)) == Decimal("2000.00")


def test_RE_05a_no_minimum_on_percent() -> None:
    # The old 10.00 minimum is gone: 10% of 50.00 saves 5.00.
    assert save("50.00", PercentRule(10)) == Decimal("5.00")


@pytest.mark.parametrize("rule", BOTH_MODES)
def test_RE_06_safety_net_allows_exact_protected_min(rule: SavingRule) -> None:
    # saving 50.00, balance 550.00 -> exactly 500.00 left: still saves
    assert save("500.00", rule, bank_balance="550.00") == Decimal("50.00")


@pytest.mark.parametrize("rule", BOTH_MODES)
def test_RE_07_safety_net_skips_when_below_protected_min(rule: SavingRule) -> None:
    # saving 50.00, balance 549.99 -> 499.99 left: nothing is saved
    assert save("500.00", rule, bank_balance="549.99") == Decimal("0.00")


@pytest.mark.parametrize("rule", [PercentRule(10), fixed("25.00")])
def test_RE_08_insufficient_balance_saves_nothing_not_partial(rule: SavingRule) -> None:
    # saving would be 25.00; the balance cannot cover it, and no partial amount is saved
    assert save("250.00", rule, bank_balance="30.00") == Decimal("0.00")


@pytest.mark.parametrize("rule", BOTH_MODES)
@pytest.mark.parametrize("kind", ["cash_withdrawal", "cash_loan"])
def test_INV_5_cash_kinds_never_save(kind: str, rule: SavingRule) -> None:
    # SV-03 / SV-03a: ample balance and a normal item, but cash kinds never auto-save.
    assert save("2000.00", rule, kind=kind) == Decimal("0.00")


@pytest.mark.parametrize("rule", BOTH_MODES)
def test_INV_5_purchase_saves(rule: SavingRule) -> None:
    assert save("500.00", rule, kind="purchase") == Decimal("50.00")


@pytest.mark.parametrize("kind", ["credit_card", "", "PURCHASE"])
def test_unknown_kind_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="unknown installment kind"):
        save("500.00", kind=kind)


def test_cash_kind_still_validates_inputs() -> None:
    # Skipping a cash kind must not bypass input validation (no float sneaks through).
    with pytest.raises(ValueError, match="item_value must be > 0"):
        save("0.00", kind="cash_loan")


@pytest.mark.parametrize("percent", [0, 101, -1, True, Decimal("10"), "10"])
def test_RE_12_bad_percent_rejected(percent: Any) -> None:
    with pytest.raises(ValueError, match=r"rule\.percent must be an int from 1 to 100"):
        save("500.00", PercentRule(percent))


@pytest.mark.parametrize("amount", ["0.00", "-0.01"])
def test_RE_12_non_positive_fixed_amount_rejected(amount: str) -> None:
    with pytest.raises(ValueError, match=r"rule\.amount must be > 0"):
        save("500.00", fixed(amount))


def test_RE_12_fixed_amount_with_three_places_rejected() -> None:
    with pytest.raises(ValueError, match=r"rule\.amount has more than 2 decimal places"):
        save("500.00", fixed("1.234"))


def test_RE_12_float_fixed_amount_rejected() -> None:
    with pytest.raises(ValueError, match=r"rule\.amount is a float"):
        save("500.00", FixedRule(50.0))  # type: ignore[arg-type]


@pytest.mark.parametrize("rule", [None, 10, Decimal("50.00"), "percent"])
def test_RE_12_rule_of_wrong_type_rejected(rule: Any) -> None:
    with pytest.raises(ValueError, match="rule must be PercentRule or FixedRule"):
        save("500.00", rule)


RE_CASES = [
    (PercentRule(10), "500.00", "10000.00"),
    (PercentRule(7), "123.45", "10000.00"),
    (PercentRule(10), "500.00", "549.99"),
    (fixed("50.00"), "500.00", "10000.00"),
    (fixed("50"), "500.00", "10000.00"),  # no places in: still two places out
]


@pytest.mark.parametrize(("rule", "item", "balance"), RE_CASES)
def test_RE_11_result_is_decimal_with_two_places(rule: SavingRule, item: str, balance: str) -> None:
    result = save(item, rule, bank_balance=balance)
    assert type(result) is Decimal
    assert result.as_tuple().exponent == -2


VALID: dict[str, Any] = {
    "kind": "purchase",
    "item_value": Decimal("500.00"),
    "bank_balance": Decimal("10000.00"),
    "protected_min": PROTECTED_MIN,
}


@pytest.mark.parametrize("field", [f for f in VALID if f != "kind"])
def test_RE_11_float_input_rejected(field: str) -> None:
    # Floats on purpose: proving floats are rejected needs one.
    args = VALID | {field: float(VALID[field])}
    with pytest.raises(ValueError, match=f"{field} is a float"):
        compute_saving(rule=TEN_PERCENT, **args)


@pytest.mark.parametrize("bad", [500, "500.00", True, None])
def test_non_decimal_input_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="item_value must be Decimal"):
        compute_saving(rule=TEN_PERCENT, **(VALID | {"item_value": bad}))


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_non_finite_input_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="bank_balance must be finite"):
        compute_saving(rule=TEN_PERCENT, **(VALID | {"bank_balance": Decimal(bad)}))


@pytest.mark.parametrize("item", ["0.00", "-0.01", "-500.00"])
def test_non_positive_item_value_rejected(item: str) -> None:
    with pytest.raises(ValueError, match="item_value must be > 0"):
        save(item)


def test_money_with_more_than_two_places_rejected() -> None:
    with pytest.raises(ValueError, match="item_value has more than 2 decimal places"):
        save("500.005")


@pytest.mark.parametrize("field", ["item_value", "bank_balance", "protected_min"])
@pytest.mark.parametrize("bad", ["1E+30", "1E+10", "10000000000.00", "-10000000000.00"])
def test_money_beyond_numeric_12_2_rejected(field: str, bad: str) -> None:
    # Review M4: 1E+30 has no decimal places, so it used to pass and then raise
    # decimal.InvalidOperation in quantize instead of ValueError.
    with pytest.raises(ValueError, match=f"{field} must be below"):
        compute_saving(rule=TEN_PERCENT, **(VALID | {field: Decimal(bad)}))


def test_largest_numeric_12_2_money_accepted() -> None:
    # 1% of 9,999,999,999.99 = 99,999,999.9999, rounded down.
    largest = "9999999999.99"
    assert save(largest, PercentRule(1), bank_balance=largest) == Decimal("99999999.99")


def test_RE_11_largest_percent_saving_is_exact() -> None:
    # 100% leaves exactly 500.00, so the full 10-digit amount is saved, not rounded.
    item = "9999999499.99"
    assert save(item, PercentRule(100), bank_balance="9999999999.99") == Decimal(item)


def test_result_ignores_callers_decimal_context() -> None:
    # Review M4: under a 2-digit global context, 5000.00 * 10 / 100 cannot be quantized
    # to cents. The engine computes in its own context, so the caller cannot break it.
    with localcontext(prec=2):
        assert save("5000.00", PercentRule(10)) == Decimal("500.00")


def test_negative_protected_min_rejected() -> None:
    # Review L1.
    with pytest.raises(ValueError, match="protected_min must be >= 0"):
        compute_saving(rule=TEN_PERCENT, **(VALID | {"protected_min": Decimal("-0.01")}))


def test_zero_protected_min_allowed() -> None:
    args = VALID | {"protected_min": Decimal("0.00"), "bank_balance": Decimal("50.00")}
    assert compute_saving(rule=TEN_PERCENT, **args) == Decimal("50.00")


def test_arguments_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        compute_saving(*VALID.values(), TEN_PERCENT)  # type: ignore[misc]


@pytest.mark.parametrize("extra", [{"rules": None}, {"max_saving": Decimal("500.00")}])
def test_L63_no_global_rule_inputs(extra: dict[str, Any]) -> None:
    # L63: no cap or global rule argument survives from L46 + L52.
    with pytest.raises(TypeError):
        compute_saving(rule=TEN_PERCENT, **(VALID | extra))


def test_negative_balance_skips_saving() -> None:
    assert save("500.00", bank_balance="-100.00") == Decimal("0.00")
