"""LO-03, LO-04, LO-07: compute_leftover_saving (L67), pure. The service and the
opt-in checks are tested in tests/payday."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import MONEY_MAX
from app.rules.engine import compute_leftover_saving
from tests.rules.helpers import PROTECTED_MIN


def leftover(budget: str, total: str, bank: str = "10000.00") -> Decimal:
    return compute_leftover_saving(
        budget=Decimal(budget),
        month_total=Decimal(total),
        bank_balance=Decimal(bank),
        protected_min=PROTECTED_MIN,
    )


def test_LO_01_saves_what_is_left_of_the_budget() -> None:
    assert leftover("9000.00", "7200.50") == Decimal("1799.50")
    assert leftover("9000.00", "0.00") == Decimal("9000.00")  # nothing due: all of it


@pytest.mark.parametrize(("budget", "total"), [("9000.00", "9000.00"), ("9000.00", "9000.01")])
def test_LO_04_nothing_left_saves_nothing(budget: str, total: str) -> None:
    assert leftover(budget, total) == Decimal("0.00")


def test_LO_04_zero_budget_saves_nothing() -> None:
    assert leftover("0.00", "0.00") == Decimal("0.00")


def test_LO_03_safety_net_exactly_500_left_saves() -> None:
    # 1,000.00 left of the budget, 1,500.00 in the bank: exactly 500.00 stays.
    assert leftover("9000.00", "8000.00", bank="1500.00") == Decimal("1000.00")


def test_LO_03_safety_net_one_satang_short_saves_nothing_at_all() -> None:
    # Never a partial amount: not 999.99, nothing.
    assert leftover("9000.00", "8000.00", bank="1499.99") == Decimal("0.00")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("budget", Decimal("-0.01"), "must be >= 0"),
        ("month_total", Decimal("-0.01"), "must be >= 0"),
        ("protected_min", Decimal("-0.01"), "must be >= 0"),
        ("budget", Decimal("1.001"), "more than 2 decimal places"),
        ("bank_balance", Decimal("NaN"), "finite"),
        ("month_total", 1, "must be Decimal"),
    ],
)
def test_LO_bad_input_rejected(field: str, value: object, message: str) -> None:
    kwargs: dict[str, object] = {
        "budget": Decimal("9000.00"),
        "month_total": Decimal("100.00"),
        "bank_balance": Decimal("10000.00"),
        "protected_min": PROTECTED_MIN,
    }
    with pytest.raises(ValueError, match=message):
        compute_leftover_saving(**(kwargs | {field: value}))  # type: ignore[arg-type]


def money(lo: str, hi: Decimal | str) -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal(lo),
        max_value=Decimal(hi),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


@st.composite
def inputs(draw: st.DrawFn) -> tuple[Decimal, Decimal, Decimal]:
    budget = draw(money("0.00", "500000.00"))
    total = draw(money("0.00", "500000.00"))
    if draw(st.booleans()):
        # Land within 2.00 of the safety-net boundary so it is actually exercised.
        gap = max(budget - total, Decimal("0.00"))
        bank = max(PROTECTED_MIN + gap + draw(money("-2.00", "2.00")), Decimal("0.00"))
    else:
        bank = draw(money("0.00", MONEY_MAX))
    return budget, total, bank


@settings(max_examples=2500, deadline=None)
@given(inputs())
def test_LO_07_leftover_is_never_negative_never_above_budget_all_or_nothing(
    values: tuple[Decimal, Decimal, Decimal],
) -> None:
    budget, total, bank = values
    saved = compute_leftover_saving(
        budget=budget, month_total=total, bank_balance=bank, protected_min=PROTECTED_MIN
    )
    assert type(saved) is Decimal
    assert saved.as_tuple().exponent == -2
    assert Decimal("0.00") <= saved <= budget
    assert saved in (Decimal("0.00"), budget - total)  # all or nothing
    if saved > 0:
        assert bank - saved >= PROTECTED_MIN
    elif budget > total:
        assert bank - (budget - total) < PROTECTED_MIN  # skipped only for the net
