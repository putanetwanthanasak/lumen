"""AS-01 to AS-07, AS-09, AS-10: the payoff plan's numbers (assistant.plan), pure.

"Now" is November 2026 throughout. Debts are plain values, so the DB-free plan is
tested on its own; test_plan_api.py checks the same numbers through the Ledger.
"""

import math
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.affordability.months import Month, Scheduled, Verdict, month_totals, month_verdict
from app.assistant.plan import (
    HORIZON_CAP,
    SAFE_NEW_TERM,
    Debt,
    Plan,
    Reason,
    amortised_payment,
    build,
    months_left,
    remaining_for_payoff,
)
from app.money import MONEY_MAX

NOW = Month(2026 * 12 + 10)  # 2026-11
INCOME = Decimal("30000.00")  # a third is 10,000.00, above every budget used here
RATE = Decimal("0.18")  # the config example, not a real rate
TERM = 24


def debt(
    monthly: str,
    months: int,
    *,
    offset: int = 0,
    remaining: str | None = None,
    manual: bool = True,
    overdue: bool = False,
    disputed: bool = False,
) -> Debt:
    """A counted installment due from NOW + offset. ledger_remaining defaults to the
    whole schedule, as a manual row with no payments has."""
    amount = Decimal(monthly)
    return Debt(
        schedule=Scheduled(NOW.plus(offset), months, amount),
        ledger_remaining=Decimal(remaining) if remaining is not None else months * amount,
        manual=manual,
        overdue=overdue,
        disputed=disputed,
    )


def plan(
    debts: list[Debt], budget: str = "5000.00", buffer: str = "0.00", income: Decimal = INCOME
) -> Plan:
    return build(
        debts,
        now=NOW,
        income=income,
        budget=Decimal(budget),
        buffer_balance=Decimal(buffer),
        annual_rate=RATE,
        term=TERM,
    )


# The doc example: budget 5,000; months 5,700, 5,700, 3,700.
DOC_EXAMPLE = [debt("3700.00", 3), debt("2000.00", 2)]


# --- AS-01: back in budget, pause, headroom on the doc example ---------------------


def test_AS_01_doc_example_back_in_budget_at_month_3_with_headroom_1300() -> None:
    result = plan(DOC_EXAMPLE)

    assert [(str(r.month), r.total, r.over_budget, r.headroom) for r in result.rows] == [
        ("2026-11", Decimal("5700.00"), True, Decimal("0.00")),
        ("2026-12", Decimal("5700.00"), True, Decimal("0.00")),
        ("2027-01", Decimal("3700.00"), False, Decimal("1300.00")),
    ]
    assert result.back_in_budget_month == NOW.plus(2)  # month 3
    assert result.pause_until == NOW.plus(2)
    assert result.safe_new_from == NOW.plus(2)
    assert result.safe_new_monthly == Decimal("1300.00")


def test_AS_01_exactly_the_budget_is_within_budget() -> None:
    result = plan([debt("5000.00", 2), debt("0.01", 1)])

    assert [r.over_budget for r in result.rows] == [True, False]
    assert result.rows[1].headroom == Decimal("0.00")
    assert result.back_in_budget_month == NOW.plus(1)


def test_AS_01_over_budget_in_the_last_month_is_back_in_budget_after_the_horizon() -> None:
    result = plan([debt("1000.00", 3), debt("4500.00", 1, offset=2)])

    assert [r.over_budget for r in result.rows] == [False, False, True]
    assert result.back_in_budget_month == NOW.plus(3)  # nothing is due after the horizon
    assert result.pause_until is None  # the current month is within budget
    assert result.safe_new_monthly == Decimal("5000.00")


# --- AS-02: already within budget; within now but over later ------------------------


def test_AS_02_within_budget_everywhere_has_no_back_in_budget_or_pause() -> None:
    result = plan([debt("3000.00", 4), debt("1000.00", 2)])

    assert result.back_in_budget_month is None
    assert result.pause_until is None
    assert result.safe_new_from == NOW
    assert result.safe_new_monthly == Decimal("1000.00")  # the first two months


def test_AS_02_within_now_but_over_later_sets_back_in_budget_without_a_pause() -> None:
    result = plan([debt("4000.00", 4), debt("2000.00", 1, offset=1)])

    assert [r.over_budget for r in result.rows] == [False, True, False, False]
    assert result.back_in_budget_month == NOW.plus(2)
    assert result.pause_until is None


def test_AS_02_nothing_owed_is_one_empty_month_with_the_whole_budget_free() -> None:
    result = plan([])

    assert [(r.month, r.total) for r in result.rows] == [(NOW, Decimal("0.00"))]
    assert result.back_in_budget_month is None
    assert result.safe_new_monthly == Decimal("5000.00")
    assert result.consolidation.reason is Reason.NOT_NEEDED


def test_AS_02_horizon_runs_to_the_last_month_due_and_is_capped_at_600() -> None:
    assert len(plan([debt("1.00", 3), debt("1.00", 5, offset=4)]).rows) == 9
    assert len(plan([debt("1.00", 3, offset=-6)]).rows) == 1  # all in the past
    assert len(plan([debt("1.00", 590, offset=10)]).rows) == HORIZON_CAP
    assert plan([debt("1.00", 590, offset=10)]).months_truncated is False
    capped = plan([debt("1.00", 591, offset=10)])
    assert (len(capped.rows), capped.months_truncated) == (HORIZON_CAP, True)


# --- AS-03: safe_new_monthly is the min headroom over the 12 months -----------------


def test_AS_03_safe_new_monthly_is_the_smallest_headroom_of_the_12_months() -> None:
    # Back in budget from 2027-01. The 12 months from there have headroom 1,300 in
    # January, 4,700 from February to May, 500 in 2027-11 and 5,000 otherwise.
    debts = [*DOC_EXAMPLE, debt("300.00", 4, offset=3), debt("4500.00", 1, offset=12)]
    result = plan(debts)

    assert result.safe_new_from == NOW.plus(2)
    assert result.safe_new_monthly == Decimal("500.00")


def test_AS_03_window_past_the_horizon_counts_the_months_after_it_as_free() -> None:
    result = plan([debt("4800.00", 2)])

    assert len(result.rows) == 2
    assert result.safe_new_monthly == Decimal("200.00")  # the 12 months include 10 free


def test_AS_03_a_debt_due_only_in_month_13_does_not_limit_the_12_months() -> None:
    result = plan([debt("5000.00", 1, offset=SAFE_NEW_TERM)])

    assert result.safe_new_monthly == Decimal("5000.00")


@pytest.mark.parametrize(
    ("income", "safe"),
    [
        ("12000.00", "4000.00"),  # a third of income is below the 5,000.00 budget
        ("12000.02", "4000.00"),  # 4,000.01 x 3 = 12,000.03: RED, so rounded down
        ("15000.00", "5000.00"),  # exactly a third is the budget
        ("30000.00", "5000.00"),  # the budget is the lower line
    ],
)
def test_AS_03_safe_new_monthly_also_stays_within_a_third_of_income(income: str, safe: str) -> None:
    """Review F2: a "safe" amount must not get L65 RED from the preview."""
    assert plan([], income=Decimal(income)).safe_new_monthly == Decimal(safe)


def test_AS_03_a_third_of_income_already_used_leaves_nothing_safe() -> None:
    result = plan([debt("4500.00", 12)], budget="9000.00", income=Decimal("12000.00"))

    assert result.safe_new_monthly == Decimal("0.00")


# --- AS-04: the buffer plan ---------------------------------------------------------


@pytest.mark.parametrize(
    ("buffer", "covered", "still_short"),
    [
        ("0.00", False, "1400.00"),
        ("1399.99", False, "0.01"),
        ("1400.00", True, "0.00"),  # exactly covered
        ("9000.00", True, "0.00"),
    ],
)
def test_AS_04_buffer_plan_covers_the_shortfall_of_the_months_over_budget(
    buffer: str, covered: bool, still_short: str
) -> None:
    result = plan(DOC_EXAMPLE, buffer=buffer).buffer

    assert result.shortfall == Decimal("1400.00")  # 700 + 700
    assert result.balance == Decimal(buffer)
    assert result.covered is covered
    assert result.still_short == Decimal(still_short)


def test_AS_04_no_month_over_budget_is_no_shortfall_and_covered() -> None:
    result = plan([debt("100.00", 3)]).buffer

    assert (result.shortfall, result.covered, result.still_short) == (
        Decimal("0.00"),
        True,
        Decimal("0.00"),
    )


# --- AS-05: consolidation eligibility (L70) -----------------------------------------


def test_AS_05_two_consecutive_months_over_budget_is_not_needed() -> None:
    result = plan(DOC_EXAMPLE).consolidation

    assert result.reason is Reason.NOT_NEEDED
    assert result.eligible is False
    assert result.estimate is None


def test_AS_05_two_runs_of_two_split_by_a_month_within_is_not_needed() -> None:
    debts = [debt("4000.00", 5), debt("2000.00", 2), debt("2000.00", 2, offset=3)]
    result = plan(debts)

    assert [r.over_budget for r in result.rows] == [True, True, False, True, True]
    assert result.consolidation.reason is Reason.NOT_NEEDED


def test_AS_05_three_consecutive_months_over_budget_is_eligible_with_an_estimate() -> None:
    result = plan([debt("3700.00", 3), debt("2000.00", 3)]).consolidation

    assert result.reason is Reason.ELIGIBLE
    assert result.eligible is True
    assert result.estimate is not None
    assert result.estimate.principal == Decimal("17100.00")
    assert result.estimate.monthly_payment == Decimal("853.71")


def test_AS_05_a_run_of_three_with_different_totals_is_one_run() -> None:
    # 5,700 then 5,800 twice: three months over budget, though no total repeats 3x.
    result = plan([debt("5700.00", 3), debt("100.00", 2, offset=1)])

    assert [r.total for r in result.rows] == [
        Decimal("5700.00"),
        Decimal("5800.00"),
        Decimal("5800.00"),
    ]
    assert result.consolidation.reason is Reason.ELIGIBLE


def test_AS_05_three_months_over_budget_later_in_the_horizon_also_counts() -> None:
    result = plan([debt("1000.00", 6), debt("4500.00", 3, offset=3)])

    assert [r.over_budget for r in result.rows] == [False, False, False, True, True, True]
    assert result.consolidation.reason is Reason.ELIGIBLE


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        ({"overdue": True}, Reason.OVERDUE_DEBT),
        ({"disputed": True}, Reason.DISPUTED_DEBT),
        ({"overdue": True, "disputed": True}, Reason.OVERDUE_DEBT),  # (c) is checked first
    ],
)
def test_AS_05_an_overdue_or_disputed_counted_debt_is_not_eligible(
    flags: dict[str, bool], reason: Reason
) -> None:
    debts = [debt("5700.00", 3), debt("100.00", 2, offset=1, manual=False, **flags)]

    assert plan(debts).consolidation.reason is reason


def test_AS_05_payment_above_budget_is_not_eligible() -> None:
    # 120,000 left over 10 years; one 24-month loan would be about 5,991 a month.
    result = plan([debt("1000.00", 120)], budget="999.99").consolidation

    assert result.reason is Reason.PAYMENT_ABOVE_BUDGET
    assert result.estimate is None


def test_AS_05_payment_exactly_the_budget_is_eligible() -> None:
    # 853.71 a month for the 17,100.00 of AS-05 above.
    debts = [debt("300.00", 3), debt("5400.00", 3)]

    assert plan(debts, budget="853.71").consolidation.reason is Reason.ELIGIBLE
    assert plan(debts, budget="853.70").consolidation.reason is Reason.PAYMENT_ABOVE_BUDGET


def test_AS_05_an_estimate_beyond_numeric_12_2_is_not_eligible() -> None:
    result = plan([debt("4000000000.00", 3)], budget="0.00").consolidation

    assert result.reason is Reason.ESTIMATE_TOO_LARGE


# --- AS-06: the estimate ------------------------------------------------------------


@pytest.mark.parametrize(
    ("principal", "rate", "term", "payment"),
    [
        ("10000.00", "0.12", 12, "888.49"),  # the textbook value: 888.4879 rounded up
        ("12000.00", "0.18", 24, "599.09"),  # 599.0892
        ("17100.00", "0.18", 24, "853.71"),  # 853.7021
        ("1000.00", "0", 3, "333.34"),  # 0 rate: 333.333... rounded up, never down
        ("900.00", "0", 3, "300.00"),  # exact stays exact
        ("4.00", "0.06", 1, "4.02"),  # exactly 4.02; without the noise cleanup, 4.03
    ],
)
def test_AS_06_amortised_payment_is_rounded_up_to_the_satang(
    principal: str, rate: str, term: int, payment: str
) -> None:
    result = amortised_payment(Decimal(principal), Decimal(rate), term)

    assert type(result) is Decimal
    assert result == Decimal(payment)
    assert result.as_tuple().exponent == -2


def test_AS_06_total_cost_is_payment_times_term_and_the_comparison_is_returned() -> None:
    estimate = plan([debt("3700.00", 3), debt("2000.00", 3)]).consolidation.estimate

    assert estimate is not None
    assert estimate.annual_rate == RATE
    assert estimate.term_months == TERM
    assert estimate.first_month == NOW.plus(1)
    assert estimate.total_cost == Decimal("20489.04")  # 853.71 x 24
    assert estimate.current_remaining_total == Decimal("17100.00")
    assert estimate.extra_cost == Decimal("3389.04")
    for value in (
        estimate.principal,
        estimate.monthly_payment,
        estimate.total_cost,
        estimate.current_remaining_total,
        estimate.extra_cost,
    ):
        assert type(value) is Decimal


def exact_payment(principal: Decimal, rate: Decimal, term: int) -> Fraction:
    """The payment as an exact fraction: the oracle, never used by the app."""
    r = Fraction(rate) / 12
    if r == 0:
        return Fraction(principal) / term
    growth = (1 + r) ** term
    return Fraction(principal) * r * growth / (growth - 1)


def documented_rounding(exact: Fraction) -> Fraction:
    """To 20 places, half even as Decimal.quantize does, then up to the satang.
    Integer arithmetic only: no round() on money (review F5)."""
    scaled = exact * 10**20
    whole, rest = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * rest
    if twice > scaled.denominator or (twice == scaled.denominator and whole % 2 == 1):
        whole += 1
    return Fraction(math.ceil(Fraction(whole, 10**20) * 100), 100)


@settings(max_examples=1500, deadline=None)
@given(
    principal=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("9999999.99"), places=2, allow_nan=False
    ),
    rate=st.decimals(min_value=Decimal("0"), max_value=Decimal("0.9999"), places=4),
    term=st.integers(min_value=1, max_value=600),
)
def test_AS_06_payment_is_the_exact_payment_rounded_up(
    principal: Decimal, rate: Decimal, term: int
) -> None:
    payment = amortised_payment(principal, rate, term)
    exact = exact_payment(principal, rate, term)

    assert payment.as_tuple().exponent == -2
    assert Fraction(payment) == documented_rounding(exact)
    assert payment >= exact - Fraction(1, 10**20)  # never understates beyond the noise


# --- AS-07: what paying off each debt takes -----------------------------------------


def test_AS_07_months_left_counts_from_the_current_month() -> None:
    assert months_left(Scheduled(NOW.plus(-2), 6, Decimal("1.00")), NOW) == 4
    assert months_left(Scheduled(NOW.plus(3), 6, Decimal("1.00")), NOW) == 6
    assert months_left(Scheduled(NOW.plus(-6), 6, Decimal("1.00")), NOW) == 0
    assert months_left(Scheduled(NOW.plus(-5), 6, Decimal("1.00")), NOW) == 1


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        # A manual row has no payments: its earlier months are taken as paid.
        (debt("1000.00", 6, offset=-2), "4000.00"),
        (debt("1000.00", 6, offset=-2, remaining="9999.00"), "4000.00"),
        (debt("1000.00", 6, offset=-6), "0.00"),
        # A webhook row: the larger of the Ledger's remaining and the schedule to come.
        (debt("1000.00", 6, offset=-2, remaining="5000.00", manual=False), "5000.00"),
        (debt("1000.00", 6, offset=-2, remaining="3000.00", manual=False), "4000.00"),
        (debt("1000.00", 6, offset=-6, remaining="1050.00", manual=False), "1050.00"),
        (debt("1000.00", 6, offset=2, manual=False), "6000.00"),
    ],
)
def test_AS_07_remaining_for_payoff(item: Debt, expected: str) -> None:
    assert remaining_for_payoff(item, NOW) == Decimal(expected)


def test_AS_07_principal_is_the_sum_over_every_counted_debt() -> None:
    debts = [
        debt("2000.00", 6, offset=-3),  # 3 left: 6,000
        debt("3700.00", 3),  # 11,100
        debt("1000.00", 4, remaining="4500.00", manual=False),  # late fees: 4,500
    ]
    estimate = plan(debts).consolidation.estimate

    assert estimate is not None
    assert estimate.principal == Decimal("21600.00")


# --- AS-09, AS-10: properties (Hypothesis) ------------------------------------------

EXAMPLES = 1500


def money(lo: str, hi: str) -> st.SearchStrategy[Decimal]:
    return st.decimals(min_value=Decimal(lo), max_value=Decimal(hi), places=2, allow_nan=False)


debts_strategy = st.lists(
    st.builds(
        lambda monthly, months, offset, manual: Debt(
            schedule=Scheduled(NOW.plus(offset), months, monthly),
            ledger_remaining=months * monthly,
            manual=manual,
            overdue=False,
            disputed=False,
        ),
        money("0.01", "20000.00"),
        # Mostly short plans; some long enough to pass the 600-month cap (review F1).
        st.one_of(st.integers(min_value=1, max_value=36), st.integers(500, 600)),
        st.one_of(st.integers(min_value=-24, max_value=24), st.integers(100, 140)),
        st.booleans(),
    ),
    max_size=6,
)


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    debts=debts_strategy,
    budget=money("0.00", "40000.00"),
    income=money("0.01", "120000.00"),
)
def test_AS_09_headroom_is_never_negative_and_safe_new_monthly_always_fits(
    debts: list[Debt], budget: Decimal, income: Decimal
) -> None:
    result = build(
        debts,
        now=NOW,
        income=income,
        budget=budget,
        buffer_balance=Decimal("0.00"),
        annual_rate=RATE,
        term=TERM,
    )
    schedules = [d.schedule for d in debts]

    assert all(r.headroom >= 0 for r in result.rows)
    assert result.safe_new_monthly >= 0
    candidate = Scheduled(result.safe_new_from, SAFE_NEW_TERM, result.safe_new_monthly)
    with_new = month_totals(
        schedules, first=result.safe_new_from, count=SAFE_NEW_TERM, candidate=candidate
    )
    before = month_totals(schedules, first=result.safe_new_from, count=SAFE_NEW_TERM)
    for old, new in zip(before, with_new, strict=True):
        if month_verdict(old.total, income=income, budget=budget) is Verdict.GREEN:
            # The new installment keeps the month GREEN in the L65 verdict: within
            # budget and within a third of income.
            assert month_verdict(new.total, income=income, budget=budget) is Verdict.GREEN
        else:
            # Already over a third of income (the window is within budget): nothing
            # more is safe.
            assert result.safe_new_monthly == 0
    # And it is the largest such amount: one satang more leaves GREEN in some month.
    assert any(
        month_verdict(m.total + Decimal("0.01"), income=income, budget=budget) is not Verdict.GREEN
        for m in with_new
    )


def full_totals(debts: list[Debt]) -> list[Decimal]:
    """The oracle: every month from NOW to the last month due, with no cap."""
    last = max([NOW.index, *(d.schedule.last_month.index for d in debts)])
    rows = month_totals([d.schedule for d in debts], first=NOW, count=last - NOW.index + 1)
    return [r.total for r in rows]


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    debts=debts_strategy,
    budget=money("0.00", "40000.00"),
    buffer=money("0.00", "100000000.00"),
)
def test_AS_10_back_in_budget_shortfall_and_run_match_every_month_uncapped(
    debts: list[Debt], budget: Decimal, buffer: Decimal
) -> None:
    result = build(
        debts,
        now=NOW,
        income=INCOME,
        budget=budget,
        buffer_balance=buffer,
        annual_rate=RATE,
        term=TERM,
    )
    totals = full_totals(debts)
    over = [i for i, t in enumerate(totals) if t > budget]

    assert [r.total for r in result.rows] == totals[:HORIZON_CAP]
    assert result.months_truncated is (len(totals) > HORIZON_CAP)
    assert result.back_in_budget_month == (NOW.plus(over[-1] + 1) if over else None)
    assert result.pause_until == (result.back_in_budget_month if 0 in over else None)
    shortfall = sum((totals[i] - budget for i in over), Decimal(0))
    assert result.buffer.shortfall == shortfall
    assert result.buffer.covered is (buffer >= shortfall)
    assert result.buffer.still_short == max(Decimal(0), shortfall - buffer)
    run = any(all(i + k in over for k in range(3)) for i in over)
    assert (result.consolidation.reason is not Reason.NOT_NEEDED) is run
    estimate = result.consolidation.estimate
    assert (estimate is not None) is result.consolidation.eligible
    if estimate is not None:
        assert estimate.total_cost == estimate.monthly_payment * TERM
        assert estimate.monthly_payment <= budget
        assert estimate.total_cost <= MONEY_MAX


# --- Review F1: months past the 600-month display cap still count -------------------


def test_AS_02_months_over_budget_past_the_cap_still_count() -> None:
    # 6,000.00 a month for 600 months from 2027-06: over budget until now + 606.
    result = plan([debt("6000.00", 600, offset=7)], buffer="595000.00")

    assert len(result.rows) == HORIZON_CAP
    assert result.months_truncated is True
    assert result.back_in_budget_month == NOW.plus(607)
    assert result.buffer.shortfall == Decimal("600000.00")  # 600 x 1,000.00
    assert result.buffer.covered is False
    assert result.buffer.still_short == Decimal("5000.00")


def test_AS_05_a_run_past_the_cap_still_makes_consolidation_needed() -> None:
    result = plan([debt("100.00", 1), debt("6000.00", 3, offset=650)])

    assert result.months_truncated is True
    assert not any(r.over_budget for r in result.rows)
    assert result.back_in_budget_month == NOW.plus(653)
    assert result.consolidation.reason is Reason.ELIGIBLE


def test_AS_05_a_principal_beyond_numeric_12_2_is_too_large_before_any_payment_math() -> None:
    """Round 2 review F1: a principal of 1E14 or more must not reach the 34-digit
    payment computation, which cannot quantize it to 20 places."""
    # 3 x 3,400 rows of 9,999,999,999.00: a principal above 1E14, over a 1-month term.
    debts = [debt("9999999999.00", 1, offset=i) for i in range(3)] * 3400
    result = build(
        debts,
        now=NOW,
        income=INCOME,
        budget=Decimal("0.00"),
        buffer_balance=Decimal("0.00"),
        annual_rate=RATE,
        term=1,
    )

    assert result.consolidation.reason is Reason.ESTIMATE_TOO_LARGE
