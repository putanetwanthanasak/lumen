"""RE-xx unit tests for compute_saving (05 section 4.1).

The rule is fixed by L46 + L52: 10% of item value, min 10.00, max 500.00 per purchase.
These values replace the 5% / 100.00 examples in 05; RE-05d and RE-10 (user-set
rate and cap via /settings) are dropped because the rule is no longer configurable.
"""

from decimal import Decimal, localcontext
from typing import Any

import pytest

from app.rules.engine import compute_saving
from tests.rules.helpers import AUTO_SAVE, PROTECTED_MIN, save


def test_RE_01_ten_percent_of_item() -> None:
    assert save("500.00") == Decimal("50.00")


def test_RE_02_exactly_at_cap() -> None:
    # 10% of 5,000.00 = 500.00, exactly max_saving
    assert save("5000.00") == Decimal("500.00")


def test_RE_03_cap_hit_just_above_boundary() -> None:
    # 10% of 5,000.10 = 500.01, capped to 500.00
    assert save("5000.10") == Decimal("500.00")


def test_RE_04_large_item_capped() -> None:
    assert save("20000.00") == Decimal("500.00")


def test_RE_05_small_item_raised_to_min_saving() -> None:
    assert save("50.00") == Decimal("10.00")


def test_RE_05a_just_below_min_raised_to_min_saving() -> None:
    # 10% of 99.90 = 9.99 < 10.00
    assert save("99.90") == Decimal("10.00")


def test_RE_05b_exactly_at_min_saving() -> None:
    # 10% of 100.00 = 10.00, exactly min_saving
    assert save("100.00") == Decimal("10.00")


def test_RE_05c_just_above_min_saving() -> None:
    assert save("100.10") == Decimal("10.01")


def test_RE_06_safety_net_allows_exact_protected_min() -> None:
    # saving 50, balance 550 -> 500 left, exactly protected_min: still saves
    assert save("500.00", bank_balance="550.00") == Decimal("50.00")


def test_RE_07_safety_net_skips_when_below_protected_min() -> None:
    assert save("500.00", bank_balance="549.99") == Decimal("0.00")


def test_RE_08_insufficient_balance_saves_nothing_not_partial() -> None:
    # saving would be 25.00; the balance cannot cover it, and no partial amount is saved
    assert save("250.00", bank_balance="30.00") == Decimal("0.00")


def test_RE_09_rate_is_fixed_at_ten_percent() -> None:
    assert save("1234.50") == Decimal("123.45")


@pytest.mark.parametrize("extra", [{"rate": Decimal("0.05")}, {"per_item_cap": Decimal("100")}])
def test_RE_09_rate_and_cap_are_not_inputs(extra: dict[str, Decimal]) -> None:
    with pytest.raises(TypeError):
        compute_saving(rules=AUTO_SAVE, **(VALID | extra))


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("100.05", "10.01"),  # 10.005: HALF_UP 10.01, DOWN and HALF_EVEN 10.00
        ("100.15", "10.02"),  # 10.015: HALF_UP 10.02, DOWN 10.01
        ("4999.95", "500.00"),  # 499.995: HALF_UP 500.00, DOWN 499.99 (below the cap)
        ("100.04", "10.00"),  # 10.004: below half, rounds down in every mode
    ],
)
def test_rounding_is_half_up_at_half_cent(item: str, expected: str) -> None:
    assert save(item) == Decimal(expected)


@pytest.mark.parametrize("kind", ["cash_withdrawal", "cash_loan"])
def test_INV_5_cash_kinds_never_save(kind: str) -> None:
    # SV-03 / SV-03a: ample balance and a normal item, but cash kinds never auto-save.
    assert save("2000.00", kind=kind) == Decimal("0.00")


def test_INV_5_purchase_saves() -> None:
    assert save("2000.00", kind="purchase") == Decimal("200.00")


@pytest.mark.parametrize("kind", ["credit_card", "", "PURCHASE"])
def test_unknown_kind_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="unknown installment kind"):
        save("500.00", kind=kind)


def test_cash_kind_still_validates_inputs() -> None:
    # Skipping a cash kind must not bypass input validation (no float sneaks through).
    with pytest.raises(ValueError, match="item_value must be > 0"):
        save("0.00", kind="cash_loan")


RE_CASES = [
    ("500.00", "10000.00"),
    ("5000.00", "10000.00"),
    ("5000.10", "10000.00"),
    ("50.00", "10000.00"),
    ("100.10", "10000.00"),
    ("500.00", "549.99"),
]


@pytest.mark.parametrize(("item", "balance"), RE_CASES)
def test_RE_11_result_is_decimal_with_two_places(item: str, balance: str) -> None:
    result = save(item, bank_balance=balance)
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
    # The only float in the codebase, on purpose: proving floats are rejected needs one.
    args = VALID | {field: float(VALID[field])}
    with pytest.raises(ValueError, match=f"{field} is a float"):
        compute_saving(rules=AUTO_SAVE, **args)


@pytest.mark.parametrize("bad", [500, "500.00", True, None])
def test_non_decimal_input_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="item_value must be Decimal"):
        compute_saving(rules=AUTO_SAVE, **(VALID | {"item_value": bad}))


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_non_finite_input_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="bank_balance must be finite"):
        compute_saving(rules=AUTO_SAVE, **(VALID | {"bank_balance": Decimal(bad)}))


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
        compute_saving(rules=AUTO_SAVE, **(VALID | {field: Decimal(bad)}))


def test_largest_numeric_12_2_money_accepted() -> None:
    assert save("9999999999.99", bank_balance="9999999999.99") == Decimal("500.00")


def test_result_ignores_callers_decimal_context() -> None:
    # Review M4: under a 2-digit global context, 5000.00 * 0.10 cannot be quantized
    # to cents. The engine computes in its own context, so the caller cannot break it.
    with localcontext(prec=2):
        assert save("5000.00") == Decimal("500.00")


def test_negative_protected_min_rejected() -> None:
    # Review L1.
    with pytest.raises(ValueError, match="protected_min must be >= 0"):
        compute_saving(rules=AUTO_SAVE, **(VALID | {"protected_min": Decimal("-0.01")}))


def test_zero_protected_min_allowed() -> None:
    args = VALID | {"protected_min": Decimal("0.00"), "bank_balance": Decimal("50.00")}
    assert compute_saving(rules=AUTO_SAVE, **args) == Decimal("50.00")


def test_arguments_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        compute_saving(*VALID.values(), AUTO_SAVE)  # type: ignore[misc]


def test_negative_balance_skips_saving() -> None:
    assert save("500.00", bank_balance="-100.00") == Decimal("0.00")
