"""The verdict block (L65), returned by the preview and in POST /installments
`warnings`. Money serialises as JSON strings, as it arrives (L49)."""

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from app.affordability.months import Verdict, over_budget, over_one_third
from app.affordability.service import Assessment


class MonthRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    month: str = Field(description='Calendar month, "YYYY-MM".')
    total: Decimal = Field(description="Installments due that month, the candidate included.")
    over_budget: bool
    over_one_third: bool


class VerdictOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    months: list[MonthRow] = Field(description="Every month of the entry's term.")
    over_budget_months: list[str]
    monthly_total: Decimal = Field(description="What is owed per month now (L43).")

    @classmethod
    def of(cls, assessment: Assessment) -> Self:
        income, budget = assessment.profile.income, assessment.profile.budget
        rows = [
            MonthRow(
                month=str(r.month),
                total=r.total,
                over_budget=over_budget(r.total, budget),
                over_one_third=over_one_third(r.total, income),
            )
            for r in assessment.rows
        ]
        return cls(
            verdict=assessment.verdict,
            months=rows,
            over_budget_months=[r.month for r in rows if r.over_budget],
            monthly_total=assessment.monthly_total,
        )


class PreviewOut(VerdictOut):
    """POST /installments/preview: the verdict plus what recording would save."""

    saving_if_recorded: Decimal = Field(
        description="What POST /installments would save for this body now (L63 rule, "
        'the 500.00 safety net and the kind included); "0.00" when nothing.'
    )
