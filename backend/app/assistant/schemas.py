"""GET /assistant/plan body. Money serialises as JSON strings (L49); months as
"YYYY-MM"."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from app.affordability.months import Month
from app.assistant.plan import SAFE_NEW_TERM, Estimate, Plan, Reason


def month_str(month: Month | None) -> str | None:
    return None if month is None else str(month)


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class PlanMonth(_Out):
    month: str
    total: Decimal = Field(description="Installments due that month (the L65 total).")
    budget: Decimal
    over_budget: bool
    headroom: Decimal = Field(description="max(0, budget - total).")


class BufferPlanOut(_Out):
    shortfall: Decimal = Field(description="Sum of total - budget over the months over budget.")
    remaining_gap: Decimal = Field(description="shortfall minus what was prepared for it.")
    balance: Decimal = Field(description="The buffer (savings balance, L66).")
    covered: bool = Field(description="The buffer covers the whole remaining gap.")
    still_short: Decimal = Field(description="max(0, remaining_gap - balance).")


class EstimateOut(_Out):
    principal: Decimal = Field(description="What paying off every counted installment takes.")
    annual_rate: Decimal = Field(description="EXAMPLE yearly rate from config, not a real rate.")
    rate_is_example: Literal[True] = True
    rate_note: Literal["example, not a real rate"] = "example, not a real rate"
    term_months: int
    first_due_month: str
    monthly_payment: Decimal = Field(description="Level payment, rounded up to 0.01.")
    total_cost: Decimal = Field(description="monthly_payment x term_months.")
    current_remaining_total: Decimal = Field(
        description="What is left to pay on the current plans, for comparison."
    )
    extra_cost: Decimal = Field(description="total_cost - current_remaining_total.")
    monthly_reduction: Decimal = Field(
        description="The counted plans' monthly total (L43) - monthly_payment; above 0."
    )

    @classmethod
    def of(cls, estimate: Estimate) -> Self:
        return cls(
            principal=estimate.principal,
            annual_rate=estimate.annual_rate,
            term_months=estimate.term_months,
            first_due_month=str(estimate.first_month),
            monthly_payment=estimate.monthly_payment,
            total_cost=estimate.total_cost,
            current_remaining_total=estimate.current_remaining_total,
            extra_cost=estimate.extra_cost,
            monthly_reduction=estimate.monthly_reduction,
        )


class ConsolidationOut(_Out):
    eligible: bool
    reason: Reason
    estimate: EstimateOut | None = Field(description="Only when eligible.")


class PlanOut(_Out):
    months: list[PlanMonth] = Field(
        description="From the current month to the last month anything counted is due, "
        "at most 600 months. Every other number covers every month, shown or not."
    )
    months_truncated: bool = Field(description="True when months stops at 600.")
    back_in_budget_month: str | None = Field(
        description="First month from which every later month is within budget; "
        "null if every month already is."
    )
    pause_until: str | None = Field(
        description="back_in_budget_month when the current month is over budget, else null."
    )
    safe_new_monthly: Decimal = Field(
        description=f"Largest monthly amount a new {SAFE_NEW_TERM}-month installment from "
        "safe_new_from could add without any of its months going over budget or over "
        "a third of income (the L65 RED line)."
    )
    safe_new_from: str
    safe_new_months: int = SAFE_NEW_TERM
    buffer_plan: BufferPlanOut
    consolidation: ConsolidationOut

    @classmethod
    def of(cls, plan: Plan) -> Self:
        c = plan.consolidation
        return cls(
            months=[
                PlanMonth(
                    month=str(r.month),
                    total=r.total,
                    budget=plan.budget,
                    over_budget=r.over_budget,
                    headroom=r.headroom,
                )
                for r in plan.rows
            ],
            months_truncated=plan.months_truncated,
            back_in_budget_month=month_str(plan.back_in_budget_month),
            pause_until=month_str(plan.pause_until),
            safe_new_monthly=plan.safe_new_monthly,
            safe_new_from=str(plan.safe_new_from),
            buffer_plan=BufferPlanOut(
                shortfall=plan.buffer.shortfall,
                remaining_gap=plan.buffer.remaining_gap,
                balance=plan.buffer.balance,
                covered=plan.buffer.covered,
                still_short=plan.buffer.still_short,
            ),
            consolidation=ConsolidationOut(
                eligible=c.eligible,
                reason=c.reason,
                estimate=None if c.estimate is None else EstimateOut.of(c.estimate),
            ),
        )
