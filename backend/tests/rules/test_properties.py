"""PB-01 / PB-02 (05 section 4.2): properties of compute_saving over generated inputs.

Decimals only (money places=2); no floats, NaN, or infinity are ever generated.
The rule is fixed (L46 + L52), so only the item value and balance vary.

The oracle is deliberately independent of the engine (review L2): it works in
integer satang with exact fractions, takes the L52 numbers from the spec rather
than from rules.json, and never calls Decimal.quantize. A changed rules.json or a
wrong rounding mode in the engine therefore cannot also change the expected value.
"""

from decimal import Decimal
from fractions import Fraction
from math import floor

from hypothesis import event, given, settings
from hypothesis import strategies as st

from app.rules.engine import compute_saving
from tests.rules.helpers import AUTO_SAVE, PROTECTED_MIN

EXAMPLES = 2500

# L46 + L52, written out from the spec: 10% of item value, min 10.00, max 500.00.
SPEC_RATE = Fraction(1, 10)
SPEC_MIN_SATANG = 10_00
SPEC_MAX_SATANG = 500_00


def money(lo: str, hi: str) -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal(lo),
        max_value=Decimal(hi),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


# Bands around the min boundary (100.00) and the cap boundary (5000.00), plus the
# full Numeric(12,2) range.
item_values = st.one_of(
    money("0.01", "300.00"),
    money("4900.00", "5100.00"),
    money("0.01", "30000.00"),
    money("0.01", "9999999999.99"),
)


def oracle_satang(item_value: Decimal) -> int:
    """Expected saving in satang before the safety net, from the spec alone."""
    exact = Fraction(item_value) * 100 * SPEC_RATE  # satang, exact
    rounded = floor(exact + Fraction(1, 2))  # round half up (inputs are positive)
    return min(max(rounded, SPEC_MIN_SATANG), SPEC_MAX_SATANG)


def oracle(item_value: Decimal) -> Decimal:
    return Decimal(oracle_satang(item_value)).scaleb(-2)


@st.composite
def saving_inputs(draw: st.DrawFn) -> tuple[Decimal, Decimal]:
    item_value = draw(item_values)
    if draw(st.booleans()):
        # Land within 2.00 of the safety-net boundary so it is actually exercised.
        boundary = PROTECTED_MIN + oracle(item_value)
        balance = boundary + draw(money("-2.00", "2.00"))
    else:
        balance = draw(money("-1000.00", "10000000.00"))
    return item_value, balance


def run(item_value: Decimal, balance: Decimal, kind: str = "purchase") -> Decimal:
    return compute_saving(
        kind=kind,
        item_value=item_value,
        bank_balance=balance,
        rules=AUTO_SAVE,
        protected_min=PROTECTED_MIN,
    )


def test_oracle_matches_hand_computed_cases() -> None:
    # The oracle itself is checked against values worked out by hand.
    cases = {
        "50.00": "10.00",
        "100.00": "10.00",
        "100.05": "10.01",
        "100.15": "10.02",
        "1234.50": "123.45",
        "4999.95": "500.00",
        "5000.10": "500.00",
    }
    for item, expected in cases.items():
        assert oracle(Decimal(item)) == Decimal(expected), item


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs())
def test_PB_01_saving_is_zero_or_clamped_rule(inputs: tuple[Decimal, Decimal]) -> None:
    item_value, balance = inputs
    saving = run(item_value, balance)

    exact = Fraction(item_value) * 100 * SPEC_RATE
    event(
        "min clamp"
        if exact < SPEC_MIN_SATANG
        else "cap"
        if exact > SPEC_MAX_SATANG
        else "rate band"
    )

    assert type(saving) is Decimal
    assert saving.as_tuple().exponent == -2
    if saving != 0:
        assert Decimal("10.00") <= saving <= Decimal("500.00")
        assert saving == oracle(item_value)


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs())
def test_PB_02_saving_never_breaches_protected_min(inputs: tuple[Decimal, Decimal]) -> None:
    item_value, balance = inputs
    saving = run(item_value, balance)

    event("saved" if saving > 0 else "skipped by safety net")
    if saving > 0:
        assert balance - saving >= PROTECTED_MIN
    else:
        # All or nothing: a skip happens only when the full amount would breach.
        assert balance - oracle(item_value) < PROTECTED_MIN


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs(), st.sampled_from(["cash_withdrawal", "cash_loan"]))
def test_INV_5_cash_kinds_never_save_property(inputs: tuple[Decimal, Decimal], kind: str) -> None:
    item_value, balance = inputs
    assert run(item_value, balance, kind) == Decimal("0.00")
