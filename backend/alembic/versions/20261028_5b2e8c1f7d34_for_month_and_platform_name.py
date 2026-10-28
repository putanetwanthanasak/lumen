"""buffer for_month and platform_name

Session 17. A buffer move (L66) may name the month it prepares money for:
`savings_transactions.for_month`, the first day of that month, on withdrawals
only. A manual installment (L62) may name the app it is paid in:
`installments.platform_name`, at most 60 characters, on manual rows only.

Both columns are nullable and new, so no existing row breaks a CHECK.

Revision ID: 5b2e8c1f7d34
Revises: 0663a31734bc
Create Date: 2026-10-28 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b2e8c1f7d34"
down_revision: str | Sequence[str] | None = "0663a31734bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOR_MONTH_CHECK = "ck_savings_transactions_for_month_on_withdrawal_only"
MANUAL_ONLY_CHECK = "ck_installments_platform_name_manual_only"
LENGTH_CHECK = "ck_installments_platform_name_length"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("savings_transactions", sa.Column("for_month", sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f(FOR_MONTH_CHECK),
        "savings_transactions",
        "type = 'withdrawal' OR for_month IS NULL",
    )
    op.add_column("installments", sa.Column("platform_name", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f(MANUAL_ONLY_CHECK), "installments", "platform_name IS NULL OR vendor = 'manual'"
    )
    op.create_check_constraint(
        op.f(LENGTH_CHECK), "installments", "char_length(platform_name) <= 60"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f(LENGTH_CHECK), "installments", type_="check")
    op.drop_constraint(op.f(MANUAL_ONLY_CHECK), "installments", type_="check")
    op.drop_column("installments", "platform_name")
    op.drop_constraint(op.f(FOR_MONTH_CHECK), "savings_transactions", type_="check")
    op.drop_column("savings_transactions", "for_month")
