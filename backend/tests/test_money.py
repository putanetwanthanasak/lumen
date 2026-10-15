"""The shared money and rate parser (L49, review L5): strings only, strict pattern."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.money import parse_money, parse_rate

MONEY_ACCEPTED = [
    ("0", "0"),
    ("0.00", "0.00"),
    ("10.5", "10.5"),
    ("1234.50", "1234.50"),
    ("9999999999.99", "9999999999.99"),  # largest Numeric(12,2) value
]

MONEY_REJECTED = [
    "",
    "1.005",  # Postgres would round this silently (review L3)
    "123.455",
    "10000000000",  # 1E10: beyond Numeric(12,2)
    "10000000000.00",
    "-1.00",
    "+1.00",
    " 1.00",
    "1.00 ",
    "1.00\n",  # $ would let a trailing newline through; fullmatch does not
    "1_000.00",
    "1,000.00",
    "1e3",
    "1E+30",
    "NaN",
    "Infinity",
    "10.",
    ".50",
    "๑๐.00",  # Thai digits: \d and Decimal both accept them
    "\uff11\uff10.00",  # full-width digits "10"
]


@pytest.mark.parametrize(("raw", "expected"), MONEY_ACCEPTED)
def test_money_accepts_plain_decimal_strings(raw: str, expected: str) -> None:
    result = parse_money(raw)
    assert type(result) is Decimal
    assert str(result) == expected


@pytest.mark.parametrize("raw", MONEY_REJECTED)
def test_money_rejects_anything_else(raw: str) -> None:
    with pytest.raises(ValueError, match="plain decimal string"):
        parse_money(raw)


@pytest.mark.parametrize("bad", [12, 0, True, None, Decimal("1.00"), b"1.00"])
def test_money_rejects_non_strings(bad: object) -> None:
    # A JSON number arrives as int or float; it is rejected before any arithmetic.
    with pytest.raises(ValueError, match="must be a JSON string"):
        parse_money(bad)


@pytest.mark.parametrize("raw", ["0", "0.05", "0.020833", "9.999999"])
def test_rate_accepts_up_to_six_places(raw: str) -> None:
    assert parse_rate(raw) == Decimal(raw)


@pytest.mark.parametrize("raw", ["0.0208333", "10", "10.0", "-0.01", "0.05 ", "5e-2", ".05"])
def test_rate_rejects_anything_else(raw: str) -> None:
    with pytest.raises(ValueError, match="plain decimal string"):
        parse_rate(raw)


@given(
    st.decimals(
        min_value=Decimal("0.00"),
        max_value=Decimal("9999999999.99"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ).map(abs)  # -0.00 is a sign, which the pattern rightly rejects
)
def test_money_roundtrips_every_storable_value(value: Decimal) -> None:
    # Every value Numeric(12,2) can hold, written plainly, parses back unchanged.
    assert parse_money(f"{value:f}") == value
