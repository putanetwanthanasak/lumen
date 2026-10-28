"""BS-01 to BS-03, BS-05 to BS-07: the buffer spent on the months over budget, months
in date order (assistant.plan.shortfalls), pure. "Now" is November 2026, as in
test_plan.py. BS-05 to BS-07 (Session 17): money already moved for a month
(POST /buffer/move-to-main with for_month) closes that month's gap first."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.affordability.months import Month, Scheduled
from app.assistant.plan import (
    HORIZON_CAP,
    Debt,
    PreparedState,
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


def run(
    debts: list[Debt], budget: str, balance: str, prepared: dict[Month, Decimal] | None = None
) -> Shortfalls:
    return shortfalls(
        [d.schedule for d in debts],
        now=NOW,
        budget=Decimal(budget),
        balance=Decimal(balance),
        prepared=prepared or {},
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


# --- BS-05: what was prepared for a month closes its gap ---------------------------------

NOV, DEC = NOW, NOW.plus(1)


def prepared_rows(result: Shortfalls) -> list[tuple[str, str, str, str, str, str, str]]:
    return [
        (
            str(r.month),
            str(r.shortfall),
            str(r.prepared),
            str(r.remaining_gap),
            r.state.value,
            str(r.covered_by_buffer),
            str(r.still_short),
        )
        for r in result.months
    ]


@pytest.mark.parametrize(
    ("moved", "nov", "dec"),
    [
        # Nothing moved: both gaps open, the buffer pays Nov first.
        (
            None,
            ("1500.00", "0.00", "1500.00", "not_prepared", "1500.00", "0.00"),
            ("1500.00", "0.00", "1500.00", "not_prepared", "500.00", "1000.00"),
        ),
        # All of Nov's gap moved: Nov is prepared, the buffer now goes to Dec.
        (
            "1500.00",
            ("1500.00", "1500.00", "0.00", "prepared", "0.00", "0.00"),
            ("1500.00", "0.00", "1500.00", "not_prepared", "1500.00", "0.00"),
        ),
        # Part of it: the gap that is left, and the buffer spent on it first.
        (
            "600.00",
            ("1500.00", "600.00", "900.00", "partly_prepared", "900.00", "0.00"),
            ("1500.00", "0.00", "1500.00", "not_prepared", "1100.00", "400.00"),
        ),
        # A satang short of the gap is still only partly prepared.
        (
            "1499.99",
            ("1500.00", "1499.99", "0.01", "partly_prepared", "0.01", "0.00"),
            ("1500.00", "0.00", "1500.00", "not_prepared", "1500.00", "0.00"),
        ),
        # More than the gap: prepared, and the extra never closes another month's gap.
        (
            "2000.00",
            ("1500.00", "2000.00", "0.00", "prepared", "0.00", "0.00"),
            ("1500.00", "0.00", "1500.00", "not_prepared", "1500.00", "0.00"),
        ),
    ],
    ids=["nothing", "all", "part", "a_satang_short", "more_than_the_gap"],
)
def test_BS_05_prepared_money_closes_its_months_gap(
    moved: str | None, nov: tuple[str, ...], dec: tuple[str, ...]
) -> None:
    # Budget 5,000: Nov and Dec are 6,500. The buffer is what is left after the move.
    prepared = {} if moved is None else {NOV: Decimal(moved)}
    result = run([debt("6500.00", 2)], "5000.00", "2000.00", prepared)
    assert prepared_rows(result) == [("2026-11", *nov), ("2026-12", *dec)]
    # A move never changes a month's total or budget numbers.
    assert [(str(r.total), str(r.shortfall)) for r in result.months] == [
        ("6500.00", "1500.00"),
        ("6500.00", "1500.00"),
    ]


def test_BS_05_the_totals_count_the_remaining_gap() -> None:
    result = run([debt("6500.00", 2)], "5000.00", "1000.00", {NOV: Decimal("1500.00")})
    buffer = result.buffer
    assert (buffer.shortfall, buffer.remaining_gap, buffer.covered, buffer.still_short) == (
        Decimal("3000.00"),
        Decimal("1500.00"),
        False,
        Decimal("500.00"),
    )
    result = run([debt("6500.00", 2)], "5000.00", "0.00", {NOV: Decimal("9000.00"), DEC: ZERO})
    assert (result.buffer.remaining_gap, result.buffer.covered) == (Decimal("1500.00"), False)
    assert [r.state for r in result.months] == [
        PreparedState.PREPARED,
        PreparedState.NOT_PREPARED,
    ]


def test_BS_05_both_months_prepared_needs_no_buffer() -> None:
    prepared = {NOV: Decimal("1500.00"), DEC: Decimal("1500.00")}
    result = run([debt("6500.00", 2)], "5000.00", "0.00", prepared)
    assert (result.buffer.remaining_gap, result.buffer.covered, result.buffer.still_short) == (
        ZERO,
        True,
        ZERO,
    )
    assert {r.state for r in result.months} == {PreparedState.PREPARED}


# --- BS-06: the month boundary ------------------------------------------------------------


@pytest.mark.parametrize(
    "month",
    [NOW.plus(-1), NOW.plus(2), NOW.plus(-12), NOW.plus(12)],
    ids=["last_month", "within_budget_after", "last_year", "next_year"],
)
def test_BS_06_money_prepared_for_another_month_closes_no_gap(month: Month) -> None:
    # Only Nov and Dec are over budget; money for any other month changes nothing.
    result = run([debt("6500.00", 2)], "5000.00", "0.00", {month: Decimal("1500.00")})
    assert [r.prepared for r in result.months] == [ZERO, ZERO]
    assert result.buffer.remaining_gap == result.buffer.shortfall == Decimal("3000.00")


def test_BS_06_money_for_a_month_counts_for_that_month_only() -> None:
    result = run([debt("6500.00", 2)], "5000.00", "0.00", {DEC: Decimal("1500.00")})
    assert [r.state.value for r in result.months] == ["not_prepared", "prepared"]
    assert result.buffer.remaining_gap == Decimal("1500.00")


# --- BS-07: against a month-by-month oracle, with money prepared -----------------------------

prepared_strategy = st.dictionaries(
    st.integers(min_value=-3, max_value=40).map(NOW.plus),
    money("0.01", "20000.00"),
    max_size=6,
)


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    debts=debts_strategy,
    budget=money("0.00", "40000.00"),
    balance=money("0.00", "100000.00"),
    prepared=prepared_strategy,
)
def test_BS_07_prepared_allocation_matches_every_month_and_the_plans_buffer(
    debts: list[Debt], budget: Decimal, balance: Decimal, prepared: dict[Month, Decimal]
) -> None:
    result = shortfalls(
        [d.schedule for d in debts], now=NOW, budget=budget, balance=balance, prepared=prepared
    )

    # The oracle walks every month from now with no cap: what was moved for the month
    # comes off its gap, then the buffer pays what is left, in date order.
    expected, left = [], balance
    for i, total in enumerate(full_totals(debts)):
        if total > budget:
            gap = total - budget
            moved = prepared.get(NOW.plus(i), ZERO)
            rest = max(ZERO, gap - moved)
            covered = min(left, rest)
            left -= covered
            expected.append((str(NOW.plus(i)), total, gap, moved, rest, covered, rest - covered))
    shown = [
        (
            str(r.month),
            r.total,
            r.shortfall,
            r.prepared,
            r.remaining_gap,
            r.covered_by_buffer,
            r.still_short,
        )
        for r in result.months
    ]
    assert shown == expected[:HORIZON_CAP]

    plan = build(
        debts,
        now=NOW,
        income=INCOME,
        budget=budget,
        buffer_balance=balance,
        annual_rate=RATE,
        term=TERM,
        prepared=prepared,
    )
    assert result.buffer == plan.buffer
    every_gap = sum((e[2] for e in expected), ZERO)
    every_rest = sum((e[4] for e in expected), ZERO)
    assert result.buffer.shortfall == every_gap
    assert result.buffer.remaining_gap == every_rest
    assert result.buffer.covered is (balance >= every_rest)
    assert result.buffer.still_short == max(ZERO, every_rest - balance)
    for r in result.months:
        assert ZERO <= r.remaining_gap <= r.shortfall
        assert r.state is (
            PreparedState.NOT_PREPARED
            if r.prepared == ZERO
            else PreparedState.PREPARED
            if r.prepared >= r.shortfall
            else PreparedState.PARTLY_PREPARED
        )
