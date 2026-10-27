"""AF-01, AF-02, AF-04 to AF-06, AF-12, AF-13: per-month totals and the L65 verdict,
on the pure functions (no database). 05 has no AF section; the IDs are new
(Session 13)."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.affordability.months import (
    SEVERITY,
    Month,
    MonthTotal,
    Scheduled,
    Verdict,
    month_totals,
    verdict,
)

NOV = Month.of(date(2026, 11, 1))
INCOME = Decimal("30000.00")
BUDGET = Decimal("9000.00")


def plan(first: Month, months: int, amount: str) -> Scheduled:
    return Scheduled(first, months, Decimal(amount))


def totals(rows: list[MonthTotal]) -> list[tuple[str, Decimal]]:
    return [(str(r.month), r.total) for r in rows]


# --- Month ---------------------------------------------------------------------------


def test_AF_01_month_steps_across_a_year_boundary() -> None:
    assert str(Month.of(date(2026, 12, 31)).plus(1)) == "2027-01"
    assert str(Month.of(date(2027, 1, 1)).plus(-1)) == "2026-12"
    assert Month.of(date(2026, 11, 30)) == NOV  # the day is ignored
    assert NOV.plus(14).first_day() == date(2028, 1, 1)
    assert (NOV.year, NOV.month, str(NOV)) == (2026, 11, "2026-11")
    assert str(Month.of(date(1, 1, 1))) == "0001-01"


# --- AF-01: placement ------------------------------------------------------------------


def test_AF_01_an_installment_counts_in_exactly_its_scheduled_months() -> None:
    rows = month_totals([plan(NOV.plus(1), 2, "100.00")], first=NOV, count=4)
    assert totals(rows) == [
        ("2026-11", Decimal("0.00")),
        ("2026-12", Decimal("100.00")),
        ("2027-01", Decimal("100.00")),
        ("2027-02", Decimal("0.00")),
    ]


def test_AF_01_candidate_is_added_to_every_month_of_its_term() -> None:
    existing = [plan(NOV, 12, "500.00"), plan(NOV, 12, "250.50")]
    rows = month_totals(existing, first=NOV, count=3, candidate=plan(NOV, 3, "99.50"))
    assert [r.total for r in rows] == [Decimal("850.00")] * 3


def test_AF_01_without_candidate_only_the_existing_plans_count() -> None:
    rows = month_totals([plan(NOV, 1, "10.00")], first=NOV, count=1)
    assert [r.total for r in rows] == [Decimal("10.00")]


def test_AF_01_no_plans_give_zero_totals() -> None:
    rows = month_totals([], first=NOV, count=2)
    assert [r.total for r in rows] == [Decimal("0.00")] * 2
    assert all(type(r.total) is Decimal for r in rows)


# --- AF-02: overlap ---------------------------------------------------------------------


def test_AF_02_installment_ending_mid_term_counts_only_where_it_overlaps() -> None:
    # Started in September for 4 months: due Sep, Oct, Nov, Dec. The candidate runs
    # Nov to Feb, so only Nov and Dec carry both.
    ending = plan(NOV.plus(-2), 4, "300.00")
    rows = month_totals([ending], first=NOV, count=4, candidate=plan(NOV, 4, "200.00"))
    assert totals(rows) == [
        ("2026-11", Decimal("500.00")),
        ("2026-12", Decimal("500.00")),
        ("2027-01", Decimal("200.00")),
        ("2027-02", Decimal("200.00")),
    ]


def test_AF_02_installment_starting_mid_term_counts_from_its_first_month() -> None:
    later = plan(NOV.plus(2), 6, "300.00")
    rows = month_totals([later], first=NOV, count=4, candidate=plan(NOV, 4, "200.00"))
    assert [r.total for r in rows] == [Decimal(v) for v in ("200.00", "200.00", "500.00", "500.00")]


# --- AF-04 to AF-06: verdict boundaries -----------------------------------------------


def one(total: str, income: str = "30000.00", budget: str = "9000.00") -> Verdict:
    rows = [MonthTotal(NOV, Decimal(total))]
    return verdict(rows, income=Decimal(income), budget=Decimal(budget))


@pytest.mark.parametrize(
    ("total", "expected"),
    [("10000.00", Verdict.YELLOW), ("10000.01", Verdict.RED)],  # 10000 * 3 == 30000
)
def test_AF_04_red_starts_just_above_one_third(total: str, expected: Verdict) -> None:
    assert one(total) == expected


def test_AF_04_red_boundary_compares_without_division() -> None:
    # One third of 0.01 has no exact decimal; total * 3 > income does not round.
    assert one("0.00", income="0.01", budget="0.00") == Verdict.GREEN
    assert one("0.01", income="0.03", budget="0.01") == Verdict.GREEN  # exactly a third
    assert one("0.01", income="0.02", budget="0.01") == Verdict.RED


@pytest.mark.parametrize(
    ("total", "expected"),
    [("8999.99", Verdict.GREEN), ("9000.00", Verdict.GREEN), ("9000.01", Verdict.YELLOW)],
)
def test_AF_05_yellow_starts_just_above_the_budget(total: str, expected: Verdict) -> None:
    assert one(total) == expected


def test_AF_05_zero_budget_makes_any_installment_yellow() -> None:
    assert one("0.00", budget="0.00") == Verdict.GREEN
    assert one("0.01", budget="0.00") == Verdict.YELLOW


def test_AF_06_budget_above_one_third_still_gives_red_over_one_third() -> None:
    # The user ignored the L64 warning: a budget of 15,000 on 30,000 income.
    assert one("12000.00", budget="15000.00") == Verdict.RED
    assert one("10000.00", budget="15000.00") == Verdict.GREEN


def test_AF_06_the_worst_month_decides() -> None:
    months = [NOV.plus(i) for i in range(3)]
    rows = [
        MonthTotal(months[0], Decimal("100.00")),
        MonthTotal(months[1], Decimal("9500.00")),  # over budget only
        MonthTotal(months[2], Decimal("100.00")),
    ]
    assert verdict(rows, income=INCOME, budget=BUDGET) == Verdict.YELLOW
    rows.append(MonthTotal(NOV.plus(3), Decimal("10000.01")))  # over one third
    assert verdict(rows, income=INCOME, budget=BUDGET) == Verdict.RED


def test_AF_06_no_months_is_green() -> None:
    assert verdict([], income=INCOME, budget=BUDGET) == Verdict.GREEN


# --- AF-12, AF-13: properties (Hypothesis) ---------------------------------------------

EXAMPLES = 1500


def money(lo: str, hi: str) -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal(lo),
        max_value=Decimal(hi),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


plans = st.builds(
    lambda offset, months, amount: Scheduled(NOV.plus(offset), months, amount),
    st.integers(min_value=-24, max_value=24),
    st.integers(min_value=1, max_value=36),
    money("0.01", "50000.00"),
)


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    existing=st.lists(plans, max_size=6),
    candidate=plans,
    extra=money("0.01", "50000.00"),
    another=plans,
    income=money("0.01", "300000.00"),
    budget=money("0.00", "300000.00"),
)
def test_AF_12_verdict_is_monotonic(
    existing: list[Scheduled],
    candidate: Scheduled,
    extra: Decimal,
    another: Scheduled,
    income: Decimal,
    budget: Decimal,
) -> None:
    def judged(schedules: list[Scheduled], cand: Scheduled) -> int:
        rows = month_totals(schedules, first=cand.first_month, count=cand.months, candidate=cand)
        return SEVERITY[verdict(rows, income=income, budget=budget)]

    base = judged(existing, candidate)
    bigger = Scheduled(candidate.first_month, candidate.months, candidate.monthly_amount + extra)
    assert judged(existing, bigger) >= base  # a larger monthly amount
    assert judged([*existing, another], candidate) >= base  # one more installment


def oracle(schedules: list[Scheduled], first: Month, count: int) -> list[Fraction]:
    """Brute force over (year, month) pairs and exact fractions: no Month arithmetic,
    no Decimal sum, so a bug there cannot also change the expected value."""
    out = []
    for i in range(count):
        y, m = divmod(first.year * 12 + first.month - 1 + i, 12)
        total = Fraction(0)
        for s in schedules:
            for k in range(s.months):
                sy, sm = divmod(s.first_month.year * 12 + s.first_month.month - 1 + k, 12)
                if (sy, sm) == (y, m):
                    total += Fraction(s.monthly_amount)
        out.append(total)
    return out


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    existing=st.lists(plans, max_size=6),
    candidate=st.none() | plans,
    offset=st.integers(min_value=-30, max_value=30),
    count=st.integers(min_value=1, max_value=40),
)
def test_AF_13_month_totals_match_a_brute_force_oracle(
    existing: list[Scheduled], candidate: Scheduled | None, offset: int, count: int
) -> None:
    first = NOV.plus(offset)
    rows = month_totals(existing, first=first, count=count, candidate=candidate)
    everything = existing + ([candidate] if candidate is not None else [])
    assert [Fraction(r.total) for r in rows] == oracle(everything, first, count)
    assert [r.month for r in rows] == [first.plus(i) for i in range(count)]
    assert all(r.total.as_tuple().exponent == -2 for r in rows)
