"""The payoff assistant's numbers (L69, L70). Pure: no database, no clock.

Every number the assistant shows comes from here, never from AI. It never ranks
which debt to pay first (L69): BNPL apps mostly cannot be paid early. It shows when
the month totals are back within budget, how much new monthly debt would still fit,
how far the buffer covers the months over budget, and whether consolidating every
counted installment into one loan is worth asking the bank about (L70).

Month totals come from affordability.months.month_totals, the same function as the
L65 verdict, so the plan and "think before you buy" never disagree.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext
from enum import StrEnum
from itertools import pairwise

from app.affordability.months import (
    Month,
    MonthTotal,
    Scheduled,
    month_totals,
    over_budget,
)
from app.money import MONEY_MAX

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
NOISE = Decimal("1E-20")
HORIZON_CAP = 600  # months shown, the R2 bound on a schedule (L59 6)
SAFE_NEW_TERM = 12  # safe_new_monthly is for a new 12-month installment
CONSOLIDATION_RUN = 3  # L70 (a): consecutive months over budget


@dataclass(frozen=True)
class Debt:
    """A counted installment as the plan sees it."""

    schedule: Scheduled
    ledger_remaining: Decimal  # owed - paid (debts.service.remaining)
    manual: bool  # recorded by the user (L62); it never gets payments
    overdue: bool
    disputed: bool


@dataclass(frozen=True)
class MonthRow:
    month: Month
    total: Decimal
    over_budget: bool
    headroom: Decimal  # max(0, budget - total)


@dataclass(frozen=True)
class BufferPlan:
    shortfall: Decimal  # the sum of total - budget over the months over budget
    balance: Decimal
    covered: bool
    still_short: Decimal


class Reason(StrEnum):
    """Why consolidation is or is not offered (L70), checked in this order."""

    NOT_NEEDED = "NOT_NEEDED"  # (a) no run of 3 months over budget
    OVERDUE_DEBT = "OVERDUE_DEBT"  # (c)
    DISPUTED_DEBT = "DISPUTED_DEBT"  # (d) never pay off a "Not me" debt
    ESTIMATE_TOO_LARGE = "ESTIMATE_TOO_LARGE"  # the loan would not fit Numeric(12,2)
    PAYMENT_ABOVE_BUDGET = "PAYMENT_ABOVE_BUDGET"  # (b)
    # (b), Session 14 open question 14: the loan must not make any month L65 RED.
    PAYMENT_ABOVE_ONE_THIRD_OF_INCOME = "PAYMENT_ABOVE_ONE_THIRD_OF_INCOME"
    ELIGIBLE = "ELIGIBLE"


@dataclass(frozen=True)
class Estimate:
    """One loan replacing every counted installment. The rate and term are EXAMPLE
    values from config, not a real rate (the bank decides, L71)."""

    principal: Decimal
    annual_rate: Decimal
    term_months: int
    first_month: Month
    monthly_payment: Decimal
    total_cost: Decimal
    current_remaining_total: Decimal  # what is left on the plans as they are now

    @property
    def extra_cost(self) -> Decimal:
        """What consolidating costs on top of the current plans; never below 0 for a
        rate >= 0, because the payment is rounded up."""
        return self.total_cost - self.current_remaining_total


@dataclass(frozen=True)
class Consolidation:
    reason: Reason
    estimate: Estimate | None  # only when eligible

    @property
    def eligible(self) -> bool:
        return self.reason is Reason.ELIGIBLE


@dataclass(frozen=True)
class Plan:
    budget: Decimal
    rows: list[MonthRow]  # at most HORIZON_CAP; the numbers below cover every month
    months_truncated: bool
    back_in_budget_month: Month | None
    pause_until: Month | None
    safe_new_monthly: Decimal
    safe_new_from: Month
    buffer: BufferPlan
    consolidation: Consolidation


@dataclass(frozen=True)
class Span:
    """Consecutive months with the same total. A total changes only where a schedule
    starts or ends, so a few spans cover any range, however long (review F1)."""

    first: Month
    months: int
    total: Decimal

    @property
    def after(self) -> Month:
        return self.first.plus(self.months)


def spans(schedules: Sequence[Scheduled], now: Month) -> list[Span]:
    """Every month from now to the last month anything is due (at least the current
    month), as spans. Each span's total comes from month_totals, like the rows."""
    end = max([now.index + 1, *(s.last_month.index + 1 for s in schedules)])
    edges = {s.first_month.index for s in schedules} | {s.last_month.index + 1 for s in schedules}
    cuts = sorted({now.index, end} | {e for e in edges if now.index < e < end})
    return [
        Span(Month(a), b - a, month_totals(schedules, first=Month(a), count=1)[0].total)
        for a, b in pairwise(cuts)
    ]


def headroom(total: Decimal, budget: Decimal) -> Decimal:
    return max(ZERO, budget - total)


def third_headroom(total: Decimal, income: Decimal) -> Decimal:
    """The most a month can add and stay at or below a third of income (L65 RED,
    review F2): rounded DOWN to the satang, so total + it never passes the third."""
    return max(ZERO, ((income - 3 * total) / 3).quantize(CENT, rounding=ROUND_DOWN))


def rows_of(totals: Sequence[MonthTotal], budget: Decimal) -> list[MonthRow]:
    return [
        MonthRow(t.month, t.total, over_budget(t.total, budget), headroom(t.total, budget))
        for t in totals
    ]


def back_in_budget(over: Sequence[Span]) -> Month | None:
    """The first month from which every later month is within budget: the month
    after the last one over budget. None if no month is over budget. After the last
    span nothing is due, so that month is always within."""
    return over[-1].after if over else None


def months_left(schedule: Scheduled, now: Month) -> int:
    """Scheduled months from the current month on, the current month included."""
    return max(0, schedule.last_month.index - max(schedule.first_month.index, now.index) + 1)


def remaining_for_payoff(debt: Debt, now: Month) -> Decimal:
    """What paying the debt off would take (Session 14, open questions 1 and 2).
    A manual row gets no payments, so its earlier months are taken as paid: months
    left x monthly amount. A webhook row takes the larger of the Ledger's remaining
    (it includes late fees and missed months) and the schedule still to come, so the
    estimate never understates the debt."""
    scheduled = months_left(debt.schedule, now) * debt.schedule.monthly_amount
    return scheduled if debt.manual else max(debt.ledger_remaining, scheduled)


def amortised_payment(principal: Decimal, annual_rate: Decimal, term: int) -> Decimal:
    """The standard level payment, P * r / (1 - (1 + r) ** -n) with r = annual / 12
    (a 0 rate is P / n). Computed at 34 digits, then cleaned to 20 places, because
    the last digits are rounding noise: 4.00 over one month at 6% a year is exactly
    4.02, but comes out as 4.02000...004, which would round up to 4.03. Last, it is
    rounded UP to the satang, so it never understates (Session 14, open question 3)."""
    with localcontext() as ctx:
        ctx.prec = 34
        rate = annual_rate / 12
        exact = principal / term if rate == 0 else principal * rate / (1 - (1 + rate) ** -term)
        return exact.quantize(NOISE).quantize(CENT, rounding=ROUND_UP)


def has_run(over: Sequence[Span], length: int) -> bool:
    """A run of `length` consecutive months over budget; adjacent spans join."""
    run, after = 0, None
    for span in over:
        run = (run if span.first == after else 0) + span.months
        if run >= length:
            return True
        after = span.after
    return False


def consolidation(
    debts: Sequence[Debt],
    over: Sequence[Span],
    *,
    now: Month,
    income: Decimal,
    budget: Decimal,
    annual_rate: Decimal,
    term: int,
) -> Consolidation:
    """L70: every condition must hold, or the reason of the first that fails."""
    if not has_run(over, CONSOLIDATION_RUN):
        return Consolidation(Reason.NOT_NEEDED, None)
    if any(d.overdue for d in debts):
        return Consolidation(Reason.OVERDUE_DEBT, None)
    if any(d.disputed for d in debts):
        return Consolidation(Reason.DISPUTED_DEBT, None)
    principal = sum((remaining_for_payoff(d, now) for d in debts), ZERO)
    # Before any payment math (round 2 review F1): up to MONEY_MAX the payment stays
    # below 1.1E10, which 34 digits hold to 20 places; far above it, quantize fails.
    if principal > MONEY_MAX:
        return Consolidation(Reason.ESTIMATE_TOO_LARGE, None)
    payment = amortised_payment(principal, annual_rate, term)
    total_cost = payment * term
    if total_cost > MONEY_MAX:
        return Consolidation(Reason.ESTIMATE_TOO_LARGE, None)
    # The loan replaces every counted installment, so after consolidating, the loan
    # is the only plan due: every month of its term must be within budget (b).
    loan = Scheduled(now.plus(1), term, payment)
    if any(
        r.over_budget
        for r in rows_of(month_totals([loan], first=loan.first_month, count=term), budget)
    ):
        return Consolidation(Reason.PAYMENT_ABOVE_BUDGET, None)
    # Nor RED in any month (L65): the loan alone is each month's total. Exactly one
    # third is not RED; compared without division.
    if payment * 3 > income:
        return Consolidation(Reason.PAYMENT_ABOVE_ONE_THIRD_OF_INCOME, None)
    return Consolidation(
        Reason.ELIGIBLE,
        Estimate(
            principal=principal,
            annual_rate=annual_rate,
            term_months=term,
            first_month=loan.first_month,
            monthly_payment=payment,
            total_cost=total_cost,
            current_remaining_total=principal,
        ),
    )


def build(
    debts: Sequence[Debt],
    *,
    now: Month,
    income: Decimal,
    budget: Decimal,
    buffer_balance: Decimal,
    annual_rate: Decimal,
    term: int,
) -> Plan:
    schedules = [d.schedule for d in debts]
    every = spans(schedules, now)
    over = [span for span in every if over_budget(span.total, budget)]
    shown = min(every[-1].after.index - now.index, HORIZON_CAP)
    rows = rows_of(month_totals(schedules, first=now, count=shown), budget)
    back = back_in_budget(over)
    # A new installment fits from the month the totals are back within budget; its
    # 12 months may run past the last month due, where nothing else is. "Safe" also
    # means no L65 RED: at most a third of income in every month (review F2).
    safe_from = back or now
    window = month_totals(schedules, first=safe_from, count=SAFE_NEW_TERM)
    shortfall = sum(((span.total - budget) * span.months for span in over), ZERO)
    return Plan(
        budget=budget,
        rows=rows,
        months_truncated=shown < every[-1].after.index - now.index,
        back_in_budget_month=back,
        pause_until=back if over and over[0].first == now else None,
        safe_new_monthly=min(
            min(headroom(t.total, budget), third_headroom(t.total, income)) for t in window
        ),
        safe_new_from=safe_from,
        buffer=BufferPlan(
            shortfall=shortfall,
            balance=buffer_balance,
            covered=buffer_balance >= shortfall,
            still_short=max(ZERO, shortfall - buffer_balance),
        ),
        consolidation=consolidation(
            debts,
            over,
            now=now,
            income=income,
            budget=budget,
            annual_rate=annual_rate,
            term=term,
        ),
    )
