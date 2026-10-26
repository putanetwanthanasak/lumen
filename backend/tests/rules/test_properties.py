"""PB-01 to PB-03 (05 section 4.2, revised for L63): properties of compute_saving.

Decimals only (money places=2); no floats, NaN, or infinity are ever generated.

The oracle is deliberately independent of the engine (review L2): it works in
integer satang with exact fractions and never calls Decimal.quantize, so a wrong
rounding mode in the engine cannot also change the expected value.
"""

from decimal import Decimal
from fractions import Fraction
from math import floor

from hypothesis import event, given, settings
from hypothesis import strategies as st

from app.money import MONEY_MAX
from app.rules.engine import FixedRule, PercentRule, SavingRule, compute_saving
from tests.rules.helpers import PROTECTED_MIN

EXAMPLES = 2500


def money(lo: str, hi: str) -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal(lo),
        max_value=Decimal(hi),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


# Tiny prices (where percent rounds to 0.00), everyday prices, and the full
# Numeric(12,2) range.
item_values = st.one_of(
    money("0.01", "5.00"),
    money("0.01", "30000.00"),
    money("0.01", "9999999999.99"),
)
percent_rules = st.integers(min_value=1, max_value=100).map(PercentRule)
fixed_rules = st.one_of(money("0.01", "100.00"), money("0.01", "9999999999.99")).map(FixedRule)


def oracle(item_value: Decimal, rule: SavingRule) -> Decimal:
    """Expected saving before the safety net, from L63 alone."""
    if isinstance(rule, FixedRule):
        return rule.amount
    exact = Fraction(item_value) * 100 * rule.percent / 100  # satang, exact
    return Decimal(floor(exact)).scaleb(-2)  # round down (inputs are positive)


@st.composite
def saving_inputs(
    draw: st.DrawFn, rules: st.SearchStrategy[SavingRule]
) -> tuple[Decimal, SavingRule, Decimal]:
    item_value = draw(item_values)
    rule = draw(rules)
    if draw(st.booleans()):
        # Land within 2.00 of the safety-net boundary so it is actually exercised.
        boundary = PROTECTED_MIN + oracle(item_value, rule)
        # Capped: a balance must itself fit Numeric(12,2).
        balance = min(boundary + draw(money("-2.00", "2.00")), MONEY_MAX)
    else:
        balance = draw(money("-1000.00", "10000000.00"))
    return item_value, rule, balance


def run(item_value: Decimal, rule: SavingRule, balance: Decimal, kind: str = "purchase") -> Decimal:
    return compute_saving(
        kind=kind,
        item_value=item_value,
        bank_balance=balance,
        rule=rule,
        protected_min=PROTECTED_MIN,
    )


def test_oracle_matches_hand_computed_cases() -> None:
    # The oracle itself is checked against values worked out by hand.
    cases = [
        ("99.99", 1, "0.99"),
        ("33.33", 15, "4.99"),
        ("0.99", 1, "0.00"),
        ("1234.50", 10, "123.45"),
        ("4999.95", 10, "499.99"),
    ]
    for item, percent, expected in cases:
        assert oracle(Decimal(item), PercentRule(percent)) == Decimal(expected), item


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs(percent_rules))
def test_PB_01_percent_saving_within_rule(inputs: tuple[Decimal, SavingRule, Decimal]) -> None:
    item_value, rule, balance = inputs
    assert isinstance(rule, PercentRule)
    saving = run(item_value, rule, balance)

    event("saved" if saving > 0 else "skipped")
    assert type(saving) is Decimal
    assert saving.as_tuple().exponent == -2
    assert Decimal("0.00") <= saving <= item_value * rule.percent / 100
    if saving != 0:
        assert saving == oracle(item_value, rule)


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs(fixed_rules))
def test_PB_03_fixed_saving_is_amount_or_zero(inputs: tuple[Decimal, SavingRule, Decimal]) -> None:
    item_value, rule, balance = inputs
    assert isinstance(rule, FixedRule)
    saving = run(item_value, rule, balance)

    event("saved" if saving > 0 else "skipped")
    assert saving in (rule.amount, Decimal("0.00"))
    assert saving >= 0


@settings(max_examples=EXAMPLES, deadline=None)
@given(saving_inputs(st.one_of(percent_rules, fixed_rules)))
def test_PB_02_saving_never_breaches_protected_min(
    inputs: tuple[Decimal, SavingRule, Decimal],
) -> None:
    item_value, rule, balance = inputs
    saving = run(item_value, rule, balance)
    expected = oracle(item_value, rule)

    event("saved" if saving > 0 else "skipped")
    if saving > 0:
        assert balance - saving >= PROTECTED_MIN
    else:
        # All or nothing: a skip happens only when there is nothing to save or the
        # full amount would breach the safety net.
        assert expected == 0 or balance - expected < PROTECTED_MIN


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    saving_inputs(st.one_of(percent_rules, fixed_rules)),
    st.sampled_from(["cash_withdrawal", "cash_loan"]),
)
def test_INV_5_cash_kinds_never_save_property(
    inputs: tuple[Decimal, SavingRule, Decimal], kind: str
) -> None:
    item_value, rule, balance = inputs
    assert run(item_value, rule, balance, kind) == Decimal("0.00")
