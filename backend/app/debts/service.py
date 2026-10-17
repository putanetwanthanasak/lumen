"""Debt summary (04 section 9, L43, OR-04).

One function computes it, and both GET /debts/summary and the new-debt alert's
monthly total (L43) use it, so the two can never disagree.

What counts as owed: an installment that is `active` or `disputed` and still has
something left to pay. A disputed debt is owed until the platform cancels it, but a
fully paid one that was disputed afterwards is not owed again.
"""

import calendar
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger.service import owed
from app.models import Installment, InstallmentStatus

ZERO = Decimal("0.00")
OWED_STATUSES = frozenset({InstallmentStatus.ACTIVE, InstallmentStatus.DISPUTED})


def add_months(start: date, months: int) -> date:
    """The same day `months` later, clamped to the end of a shorter month."""
    year, month0 = divmod(start.month - 1 + months, 12)
    year += start.year
    last_day = calendar.monthrange(year, month0 + 1)[1]
    return date(year, month0 + 1, min(start.day, last_day))


def last_due_date(installment: Installment) -> date:
    """The scheduled final due date from the plan, not a prediction."""
    return add_months(installment.first_due_date, installment.months - 1)


def remaining(installment: Installment) -> Decimal:
    return owed(installment) - installment.paid_amount


def still_owed(installment: Installment) -> bool:
    return installment.status in OWED_STATUSES and remaining(installment) > ZERO


class _Out(BaseModel):
    # Decimals serialise as JSON strings, as webhook money arrives (L49).
    model_config = ConfigDict(frozen=True)


class InstallmentLine(_Out):
    id: uuid.UUID
    vendor: str
    contract_id: str
    kind: str
    item_name: str
    principal: Decimal
    monthly_amount: Decimal
    months: int
    paid_amount: Decimal
    late_fees_accrued: Decimal
    remaining: Decimal
    status: str
    # Set once by "Not me" and kept after a later cancel (L59 3).
    disputed_at: datetime | None
    owed: bool = Field(description="Counts toward monthly_total and total_remaining.")
    first_due_date: date
    last_due_date: date = Field(description="Scheduled final due date from the plan.")


class DebtSummary(_Out):
    monthly_total: Decimal = Field(description="Sum of monthly_amount over owed installments.")
    total_remaining: Decimal = Field(description="Sum of remaining over owed installments.")
    debt_free_date: date | None = Field(
        description=(
            "The latest scheduled final due date among owed installments, taken from each "
            "installment plan. It is not a prediction: early or late payments do not move "
            "it. Null when nothing is owed."
        )
    )
    installments: list[InstallmentLine]


def summary(session: Session, user_id: str) -> DebtSummary:
    rows = session.execute(
        select(Installment)
        .where(Installment.user_id == user_id)
        .order_by(Installment.created_at, Installment.id)
    ).scalars()
    lines = [
        InstallmentLine(
            id=i.id,
            vendor=i.vendor,
            contract_id=i.contract_id,
            kind=i.kind,
            item_name=i.item_name,
            principal=i.principal,
            monthly_amount=i.monthly_amount,
            months=i.months,
            paid_amount=i.paid_amount,
            late_fees_accrued=i.late_fees_accrued,
            remaining=remaining(i),
            status=i.status,
            disputed_at=i.disputed_at,
            owed=still_owed(i),
            first_due_date=i.first_due_date,
            last_due_date=last_due_date(i),
        )
        for i in rows
    ]
    owed_lines = [line for line in lines if line.owed]
    return DebtSummary(
        monthly_total=sum((line.monthly_amount for line in owed_lines), ZERO),
        total_remaining=sum((line.remaining for line in owed_lines), ZERO),
        debt_free_date=max((line.last_due_date for line in owed_lines), default=None),
        installments=lines,
    )
