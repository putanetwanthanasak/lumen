"""PB-01 / PB-02 (05 section 4.2): properties of compute_saving over generated inputs.

Decimals only: money places=2, rates places=4 within the configured bounds.
No floats, NaN, or infinity are ever generated.
"""

from decimal import ROUND_HALF_UP, Decimal

from hypothesis import event, given, settings
from hypothesis import strategies as st

from app.rules.engine import compute_saving
from tests.rules.helpers import AUTO_SAVE, PROTECTED_MIN

EXAMPLES = 2500
CENT = Decimal("0.01")


def money(lo: str, hi: str) -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal(lo),
        max_value=Decimal(hi),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


# Small items exercise the min clamp, mid items the 5% band, large ones the cap.
item_values = st.one_of(
    money("0.01", "3000.00"), money("100.00", "30000.00"), money("0.01", "9999999999.99")
)
rates = st.decimals(
    min_value=AUTO_SAVE.min_rate,
    max_value=AUTO_SAVE.max_rate,
    places=4,
    allow_nan=False,
    allow_infinity=False,
)
caps = money(str(AUTO_SAVE.min_saving), "1000.00")


def oracle(item_value: Decimal, rate: Decimal, cap: Decimal) -> Decimal:
    """Independent statement of the rule (03 section 3.2), before the safety net."""
    raw = (item_value * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    return min(max(raw, AUTO_SAVE.min_saving), cap)


@st.composite
def saving_inputs(draw: st.DrawFn) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    item_value, rate, cap = draw(item_values), draw(rates), draw(caps)
    if draw(st.booleans()):
        # Land within 2.00 of the safety-net boundary so it is actually exercised.
        boundary = PROTECTED_MIN + oracle(item_value, rate, cap)
        balance = boundary + draw(money("-2.00", "2.00"))
    else:
        balance = draw(money("-1000.00", "10000000.00"))
    return item_value, rate, cap, balance


def run(item_value: Decimal, rate: Decimal, cap: Decimal, balance: Decimal) -> Decimal:
    return compute_saving(
        item_value=item_value,
        rate=rate,
        per_item_cap=cap,
        bank_balance=balance,
        rules=AUTO_SAVE,
        protected_min=PROTECTED_MIN,
    )


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs())
def test_PB_01_saving_is_zero_or_clamped_rule(inputs: tuple[Decimal, ...]) -> None:
    item_value, rate, cap, balance = inputs
    saving = run(item_value, rate, cap, balance)

    raw = (item_value * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    event("min clamp" if raw < AUTO_SAVE.min_saving else "cap" if raw > cap else "rate band")

    assert type(saving) is Decimal
    assert saving.as_tuple().exponent == -2
    if saving != 0:
        assert AUTO_SAVE.min_saving <= saving <= cap
        assert saving == oracle(item_value, rate, cap)


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs())
def test_PB_02_saving_never_breaches_protected_min(inputs: tuple[Decimal, ...]) -> None:
    item_value, rate, cap, balance = inputs
    saving = run(item_value, rate, cap, balance)

    event("saved" if saving > 0 else "skipped by safety net")
    if saving > 0:
        assert balance - saving >= PROTECTED_MIN
    else:
        # All or nothing: a skip happens only when the full amount would breach.
        assert balance - oracle(item_value, rate, cap) < PROTECTED_MIN
