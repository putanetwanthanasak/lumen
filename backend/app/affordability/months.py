"""Per-month installment totals and the L65 verdict. Pure: no database, no clock.

The payoff assistant (next session) imports month_totals, so it takes plain values
and returns plain values. The service module loads the schedules from the Ledger.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0.00")


@dataclass(frozen=True, order=True)
class Month:
    """A calendar month. Ordered and stepped by its index, year * 12 + month - 1."""

    index: int

    @classmethod
    def of(cls, day: date) -> Month:
        """The month a date falls in: a webhook due date on the 15th is in its month."""
        return cls(day.year * 12 + day.month - 1)

    @property
    def year(self) -> int:
        return self.index // 12

    @property
    def month(self) -> int:
        return self.index % 12 + 1

    def plus(self, months: int) -> Month:
        return Month(self.index + months)

    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True)
class Scheduled:
    """One installment plan: monthly_amount is due in `months` consecutive months
    starting at first_month."""

    first_month: Month
    months: int
    monthly_amount: Decimal

    @property
    def last_month(self) -> Month:
        return self.first_month.plus(self.months - 1)

    def due_in(self, month: Month) -> bool:
        return self.first_month <= month <= self.last_month


@dataclass(frozen=True)
class MonthTotal:
    month: Month
    total: Decimal


def month_totals(
    schedules: Iterable[Scheduled],
    *,
    first: Month,
    count: int,
    candidate: Scheduled | None = None,
) -> list[MonthTotal]:
    """The installment total due in each of `count` months from `first`: every
    schedule due that month, plus the candidate if one is given (L65)."""
    plans = list(schedules)
    if candidate is not None:
        plans.append(candidate)
    months = [first.plus(i) for i in range(count)]
    return [
        MonthTotal(m, sum((p.monthly_amount for p in plans if p.due_in(m)), ZERO)) for m in months
    ]


class Verdict(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


# Worse verdicts rank higher, so the verdict over a term is the worst month's.
SEVERITY = {Verdict.GREEN: 0, Verdict.YELLOW: 1, Verdict.RED: 2}


def over_one_third(total: Decimal, income: Decimal) -> bool:
    """Above one third of income: Bank of Thailand financial-literacy guidance that
    total debt payments should not exceed a third of monthly income. It is guidance,
    not a regulation. No division to round; exactly one third is not over."""
    return total * 3 > income


def over_budget(total: Decimal, budget: Decimal) -> bool:
    """Above the user's own monthly installment budget; exactly the budget is not."""
    return total > budget


def month_verdict(total: Decimal, *, income: Decimal, budget: Decimal) -> Verdict:
    if over_one_third(total, income):
        return Verdict.RED
    if over_budget(total, budget):
        return Verdict.YELLOW
    return Verdict.GREEN


def verdict(rows: Sequence[MonthTotal], *, income: Decimal, budget: Decimal) -> Verdict:
    """L65: RED if any month is over one third of income, else YELLOW if any month is
    over the budget, else GREEN. A budget the user set above one third (L64 warned)
    still gives RED in a month over one third."""
    return max(
        (month_verdict(r.total, income=income, budget=budget) for r in rows),
        key=SEVERITY.__getitem__,
        default=Verdict.GREEN,
    )
