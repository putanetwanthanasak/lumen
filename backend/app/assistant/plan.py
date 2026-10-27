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
from decimal import ROUND_UP, Decimal, localcontext
from enum import StrEnum

from app.affordability.months import Month, MonthTotal, Scheduled, month_totals, over_budget
from app.money import MONEY_MAX

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
NOISE = Decimal("1E-20")
HORIZON_CAP = 600  # months, the R2 bound on a schedule (L59 6)
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
    rows: list[MonthRow]
    back_in_budget_month: Month | None
    pause_until: Month | None
    safe_new_monthly: Decimal
    safe_new_from: Month
    buffer: BufferPlan
    consolidation: Consolidation


def horizon(debts: Sequence[Debt], now: Month) -> int:
    """Months from now to the last month any counted schedule is due: at least the
    current month, at most HORIZON_CAP."""
    last = max((d.schedule.last_month.index for d in debts), default=now.index)
    return min(max(last - now.index + 1, 1), HORIZON_CAP)


def headroom(total: Decimal, budget: Decimal) -> Decimal:
    return max(ZERO, budget - total)


def rows_of(totals: Sequence[MonthTotal], budget: Decimal) -> list[MonthRow]:
    return [
        MonthRow(t.month, t.total, over_budget(t.total, budget), headroom(t.total, budget))
        for t in totals
    ]


def back_in_budget(rows: Sequence[MonthRow]) -> Month | None:
    """The first month from which every later month is within budget: the month
    after the last one over budget. None if no month is over budget. Past the
    horizon nothing is due, so the month after the horizon is always within."""
    over = [r.month for r in rows if r.over_budget]
    return over[-1].plus(1) if over else None


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


def has_run(rows: Sequence[MonthRow], length: int) -> bool:
    run = 0
    for row in rows:
        run = run + 1 if row.over_budget else 0
        if run >= length:
            return True
    return False


def consolidation(
    debts: Sequence[Debt],
    rows: Sequence[MonthRow],
    *,
    now: Month,
    budget: Decimal,
    annual_rate: Decimal,
    term: int,
) -> Consolidation:
    """L70: every condition must hold, or the reason of the first that fails."""
    if not has_run(rows, CONSOLIDATION_RUN):
        return Consolidation(Reason.NOT_NEEDED, None)
    if any(d.overdue for d in debts):
        return Consolidation(Reason.OVERDUE_DEBT, None)
    if any(d.disputed for d in debts):
        return Consolidation(Reason.DISPUTED_DEBT, None)
    principal = sum((remaining_for_payoff(d, now) for d in debts), ZERO)
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
    budget: Decimal,
    buffer_balance: Decimal,
    annual_rate: Decimal,
    term: int,
) -> Plan:
    schedules = [d.schedule for d in debts]
    rows = rows_of(month_totals(schedules, first=now, count=horizon(debts, now)), budget)
    back = back_in_budget(rows)
    # A new installment fits from the month the totals are back within budget; its
    # 12 months may run past the horizon, where nothing else is due.
    safe_from = back or now
    window = month_totals(schedules, first=safe_from, count=SAFE_NEW_TERM)
    shortfall = sum((r.total - budget for r in rows if r.over_budget), ZERO)
    return Plan(
        budget=budget,
        rows=rows,
        back_in_budget_month=back,
        pause_until=back if rows[0].over_budget else None,
        safe_new_monthly=min(headroom(t.total, budget) for t in window),
        safe_new_from=safe_from,
        buffer=BufferPlan(
            shortfall=shortfall,
            balance=buffer_balance,
            covered=buffer_balance >= shortfall,
            still_short=max(ZERO, shortfall - buffer_balance),
        ),
        consolidation=consolidation(
            debts, rows, now=now, budget=budget, annual_rate=annual_rate, term=term
        ),
    )
