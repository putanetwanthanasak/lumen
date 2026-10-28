"""BS-01 to BS-03: the buffer spent on the months over budget, months in date order
(assistant.plan.shortfalls), pure. "Now" is November 2026, as in test_plan.py."""

from decimal import Decimal

import pytest
from hypothesis import given, settings

from app.affordability.months import Scheduled
from app.assistant.plan import (
    HORIZON_CAP,
    Debt,
    ShortfallMonth,
    Shortfalls,
    build,
    shortfalls,
)
from tests.assistant.test_plan import (
    EXAMPLES,
    INCOME,
    NOW,
    RATE,
    TERM,
    debt,
    debts_strategy,
    full_totals,
    money,
)

ZERO = Decimal("0.00")


def run(debts: list[Debt], budget: str, balance: str) -> Shortfalls:
    return shortfalls(
        [d.schedule for d in debts], now=NOW, budget=Decimal(budget), balance=Decimal(balance)
    )


def as_tuples(rows: list[ShortfallMonth]) -> list[tuple[str, str, str, str, str]]:
    return [
        (str(r.month), str(r.total), str(r.shortfall), str(r.covered_by_buffer), str(r.still_short))
        for r in rows
    ]


# --- BS-01: the allocation ------------------------------------------------------------------


def test_BS_01_the_buffer_pays_the_months_in_date_order() -> None:
    # Budget 5,000: Nov and Dec are 6,500 (1,500 over each), Jan is 5,800 (800 over),
    # Feb is back to 2,000.
    debts = [debt("2000.00", 4), debt("4500.00", 2), debt("3800.00", 1, offset=2)]
    result = run(debts, "5000.00", "2700.00")
    assert as_tuples(result.months) == [
        ("2026-11", "6500.00", "1500.00", "1500.00", "0.00"),
        ("2026-12", "6500.00", "1500.00", "1200.00", "300.00"),
        ("2027-01", "5800.00", "800.00", "0.00", "800.00"),
    ]
    buffer = result.buffer
    assert (buffer.shortfall, buffer.balance, buffer.covered, buffer.still_short) == (
        Decimal("3800.00"),
        Decimal("2700.00"),
        False,
        Decimal("1100.00"),
    )
    assert result.months_truncated is False


@pytest.mark.parametrize(
    ("balance", "covered", "still_short", "last_month"),
    [
        ("3000.00", True, "0.00", ("1500.00", "0.00")),  # exactly the shortfall covers it
        ("2999.99", False, "0.01", ("1499.99", "0.01")),  # a satang less is a satang short
        ("9000.00", True, "0.00", ("1500.00", "0.00")),  # more than enough: no more spent
        ("0.00", False, "3000.00", ("0.00", "1500.00")),
    ],
)
def test_BS_01_a_buffer_of_exactly_the_shortfall_covers_it(
    balance: str, covered: bool, still_short: str, last_month: tuple[str, str]
) -> None:
    result = run([debt("6500.00", 2)], "5000.00", balance)
    assert (result.buffer.covered, str(result.buffer.still_short)) == (covered, still_short)
    last = result.months[-1]
    assert (str(last.covered_by_buffer), str(last.still_short)) == last_month


def test_BS_01_months_over_budget_later_are_listed_after_a_gap() -> None:
    debts = [debt("6000.00", 1), debt("6000.00", 1, offset=3)]
    result = run(debts, "5000.00", "1500.00")
    assert as_tuples(result.months) == [
        ("2026-11", "6000.00", "1000.00", "1000.00", "0.00"),
        ("2027-02", "6000.00", "1000.00", "500.00", "500.00"),
    ]


# --- BS-02: against a month-by-month oracle --------------------------------------------------


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    debts=debts_strategy,
    budget=money("0.00", "40000.00"),
    balance=money("0.00", "100000000.00"),
)
def test_BS_02_allocation_matches_every_month_and_the_plans_buffer(
    debts: list[Debt], budget: Decimal, balance: Decimal
) -> None:
    result = shortfalls([d.schedule for d in debts], now=NOW, budget=budget, balance=balance)

    # The oracle walks every month with no cap, spending the buffer as it goes.
    totals = full_totals(debts)
    expected, left = [], balance
    for i, total in enumerate(totals):
        if total > budget:
            gap = total - budget
            covered = min(left, gap)
            left -= covered
            expected.append((str(NOW.plus(i)), total, gap, covered, gap - covered))
    shown = [
        (str(r.month), r.total, r.shortfall, r.covered_by_buffer, r.still_short)
        for r in result.months
    ]
    assert shown == expected[:HORIZON_CAP]
    assert result.months_truncated is (len(expected) > HORIZON_CAP)

    # The totals are the plan's own buffer numbers, over every month.
    plan = build(
        debts,
        now=NOW,
        income=INCOME,
        budget=budget,
        buffer_balance=balance,
        annual_rate=RATE,
        term=TERM,
    )
    assert result.buffer == plan.buffer
    every_gap = sum((e[2] for e in expected), ZERO)
    every_covered = sum((e[3] for e in expected), ZERO)
    assert result.buffer.shortfall == every_gap
    assert every_covered == min(balance, every_gap)
    assert result.buffer.still_short == every_gap - every_covered
    assert all(ZERO <= r.covered_by_buffer <= r.shortfall for r in result.months)


# --- BS-03: nothing over budget ---------------------------------------------------------------


@pytest.mark.parametrize(
    "debts",
    [[], [debt("5000.00", 3)], [debt("2000.00", 2), debt("3000.00", 2)]],
    ids=["nothing_owed", "exactly_the_budget", "exactly_the_budget_in_sum"],
)
def test_BS_03_nothing_over_budget_has_no_shortfall(debts: list[Debt]) -> None:
    result = run(debts, "5000.00", "100.00")
    assert result.months == []
    assert (result.buffer.shortfall, result.buffer.covered, result.buffer.still_short) == (
        ZERO,
        True,
        ZERO,
    )


def test_BS_03_months_before_now_are_never_shortfalls() -> None:
    # Over budget from Aug to Oct only: all past.
    result = run([debt("9000.00", 3, offset=-3)], "5000.00", "0.00")
    assert result.months == []


def test_BS_03_rows_stop_at_600_months_over_budget() -> None:
    schedule = Scheduled(NOW, 600, Decimal("6000.00"))
    extra = Scheduled(NOW.plus(600), 5, Decimal("6000.00"))
    result = shortfalls([schedule, extra], now=NOW, budget=Decimal("5000.00"), balance=ZERO)
    assert (len(result.months), result.months_truncated) == (600, True)
    assert result.buffer.shortfall == Decimal("605000.00")  # every month, shown or not
