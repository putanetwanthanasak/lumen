"""RE-xx unit tests for compute_saving (05 section 4.1)."""

from decimal import Decimal
from typing import Any

import pytest

from app.rules.engine import compute_saving
from tests.rules.helpers import AUTO_SAVE, PROTECTED_MIN, save


def test_RE_01_five_percent_of_item() -> None:
    assert save("500.00") == Decimal("25.00")


def test_RE_02_exactly_at_cap() -> None:
    assert save("2000.00") == Decimal("100.00")


def test_RE_03_cap_hit_just_above_boundary() -> None:
    # 5% of 2,000.20 = 100.01, capped to 100.00
    assert save("2000.20") == Decimal("100.00")


def test_RE_04_large_item_capped() -> None:
    assert save("20000.00") == Decimal("100.00")


def test_RE_05_small_item_raised_to_min_saving() -> None:
    assert save("50.00") == Decimal("10.00")


def test_RE_05a_below_min_raised_to_min_saving() -> None:
    # 5% of 106 = 5.30 < 10
    assert save("106.00") == Decimal("10.00")


def test_RE_05b_exactly_at_min_saving() -> None:
    assert save("200.00") == Decimal("10.00")


def test_RE_05c_just_above_min_saving() -> None:
    assert save("201.00") == Decimal("10.05")


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("201.10", "10.06"),  # 10.055: HALF_UP 10.06, DOWN 10.05
        ("1000.10", "50.01"),  # 50.005: HALF_UP 50.01, DOWN and HALF_EVEN 50.00
        ("201.09", "10.05"),  # 10.0545: below half, rounds down in every mode
    ],
)
def test_rounding_is_half_up_at_half_cent(item: str, expected: str) -> None:
    # Added after break test 3: only PB-01 (probabilistically) caught ROUND_DOWN.
    assert save(item) == Decimal(expected)


@pytest.mark.parametrize("kind", ["cash_withdrawal", "cash_loan"])
def test_INV_5_cash_kinds_never_save(kind: str) -> None:
    # SV-03 / SV-03a: ample balance and a normal item, but cash kinds never auto-save.
    assert save("2000.00", kind=kind) == Decimal("0.00")


def test_INV_5_purchase_saves() -> None:
    assert save("2000.00", kind="purchase") == Decimal("100.00")


@pytest.mark.parametrize("kind", ["credit_card", "", "PURCHASE"])
def test_unknown_kind_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="unknown installment kind"):
        save("500.00", kind=kind)


def test_cash_kind_still_validates_inputs() -> None:
    # Skipping a cash kind must not bypass input validation (no float sneaks through).
    with pytest.raises(ValueError, match="item_value must be > 0"):
        save("0.00", kind="cash_loan")


def test_RE_05d_cap_below_min_saving_rejected() -> None:
    # Engine level; the /settings 422 test is carry-over (no API yet).
    with pytest.raises(ValueError, match="per_item_cap must be >= min_saving"):
        save("500.00", per_item_cap="5.00")


def test_RE_05d_cap_equal_to_min_saving_allowed() -> None:
    assert save("500.00", per_item_cap="10.00") == Decimal("10.00")


def test_RE_06_safety_net_allows_exact_protected_min() -> None:
    # saving 50, balance 550 -> 500 left, exactly protected_min: still saves
    assert save("1000.00", bank_balance="550.00") == Decimal("50.00")


def test_RE_07_safety_net_skips_when_below_protected_min() -> None:
    assert save("1000.00", bank_balance="549.99") == Decimal("0.00")


def test_RE_08_insufficient_balance_saves_nothing_not_partial() -> None:
    assert save("500.00", bank_balance="30.00") == Decimal("0.00")


@pytest.mark.parametrize(("rate", "expected"), [("0.03", "15.00"), ("0.10", "50.00")])
def test_RE_09_rate_range_bounds(rate: str, expected: str) -> None:
    assert save("500.00", rate=rate) == Decimal(expected)


@pytest.mark.parametrize("rate", ["0.02", "0.029999", "0.100001", "0.11"])
def test_RE_10_rate_outside_bounds_rejected(rate: str) -> None:
    # Engine level; the /settings 422 test is carry-over (no API yet).
    with pytest.raises(ValueError, match="rate must be within"):
        save("500.00", rate=rate)


RE_CASES = [
    ("500.00", "10000.00"),
    ("2000.00", "10000.00"),
    ("2000.20", "10000.00"),
    ("50.00", "10000.00"),
    ("201.00", "10000.00"),
    ("1000.00", "549.99"),
]


@pytest.mark.parametrize(("item", "balance"), RE_CASES)
def test_RE_11_result_is_decimal_with_two_places(item: str, balance: str) -> None:
    result = save(item, bank_balance=balance)
    assert type(result) is Decimal
    assert result.as_tuple().exponent == -2


VALID: dict[str, Any] = {
    "kind": "purchase",
    "item_value": Decimal("500.00"),
    "rate": Decimal("0.05"),
    "per_item_cap": Decimal("100.00"),
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


def test_rate_with_more_than_six_places_rejected() -> None:
    with pytest.raises(ValueError, match="rate has more than 6 decimal places"):
        save("500.00", rate="0.0500001")


def test_arguments_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        compute_saving(*VALID.values(), AUTO_SAVE)  # type: ignore[call-arg, misc]


def test_negative_balance_skips_saving() -> None:
    assert save("500.00", bank_balance="-100.00") == Decimal("0.00")
