"""user settings and saving rule

L63 + L64: user_settings holds the user's profile (income, payday, monthly
installment budget) and exactly one saving rule (percent or fixed), plus the
stored-only leftover_saving_enabled flag. monthly_installment_cap is renamed to
monthly_installment_budget: it is the same per-month limit, and 5d (over_cap)
was never built.

Hand-written CHECKs (tests/db/test_schema_snapshot.py sees them): the ranges,
the mode's value present exactly for that mode, and the profile all-or-none, so
rows from before L63 stay valid and save nothing until the user sets a rule. Their
never-used cap is cleared first, or a cap alone would break the all-or-none CHECK.

Revision ID: 13bb1d51a30c
Revises: c4e6a8b0d2f4
Create Date: 2026-10-26 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13bb1d51a30c"
down_revision: str | Sequence[str] | None = "c4e6a8b0d2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "user_settings"
CHECKS = {
    "ck_user_settings_income_positive": "income > 0",
    "ck_user_settings_payday_day_of_month": "payday BETWEEN 1 AND 31",
    "ck_user_settings_saving_mode_valid": "saving_mode IN ('percent', 'fixed')",
    "ck_user_settings_saving_percent_range": "saving_percent BETWEEN 1 AND 100",
    "ck_user_settings_saving_fixed_amount_positive": "saving_fixed_amount > 0",
    "ck_user_settings_saving_percent_with_mode": (
        "(saving_percent IS NOT NULL) = (saving_mode IS NOT DISTINCT FROM 'percent')"
    ),
    "ck_user_settings_saving_fixed_amount_with_mode": (
        "(saving_fixed_amount IS NOT NULL) = (saving_mode IS NOT DISTINCT FROM 'fixed')"
    ),
    "ck_user_settings_profile_all_or_none": (
        "num_nulls(income, payday, monthly_installment_budget, saving_mode) IN (0, 4)"
    ),
}


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f("ck_user_settings_monthly_cap_nonneg"), TABLE, type_="check")
    op.alter_column(TABLE, "monthly_installment_cap", new_column_name="monthly_installment_budget")
    op.create_check_constraint(
        op.f("ck_user_settings_monthly_budget_nonneg"), TABLE, "monthly_installment_budget >= 0"
    )
    op.add_column(TABLE, sa.Column("income", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column(TABLE, sa.Column("payday", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("saving_mode", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("saving_percent", sa.Integer(), nullable=True))
    op.add_column(
        TABLE, sa.Column("saving_fixed_amount", sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column(
        TABLE,
        sa.Column(
            "leftover_saving_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    # Review F5: the old CHECK allowed a cap alone, which would now be a budget with
    # no profile. No code ever wrote the cap (5d was never built), and every row here
    # has no rule yet, so the budget is cleared rather than kept half-filled.
    op.execute("UPDATE user_settings SET monthly_installment_budget = NULL")
    for name, condition in CHECKS.items():
        op.create_check_constraint(op.f(name), TABLE, condition)


def downgrade() -> None:
    """Downgrade schema."""
    for name in reversed(CHECKS):
        op.drop_constraint(op.f(name), TABLE, type_="check")
    for column in (
        "leftover_saving_enabled",
        "saving_fixed_amount",
        "saving_percent",
        "saving_mode",
        "payday",
        "income",
    ):
        op.drop_column(TABLE, column)
    op.drop_constraint(op.f("ck_user_settings_monthly_budget_nonneg"), TABLE, type_="check")
    op.alter_column(TABLE, "monthly_installment_budget", new_column_name="monthly_installment_cap")
    op.create_check_constraint(
        op.f("ck_user_settings_monthly_cap_nonneg"),
        TABLE,
        "monthly_installment_cap IS NULL OR monthly_installment_cap >= 0",
    )
