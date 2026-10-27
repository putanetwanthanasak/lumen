"""payday runs and leftover saving

L67: on payday the user's month total is compared with their budget. Over budget
stores a `payday_shortfall` alert; under it, if the user opted in, the leftover
is saved as a `leftover_save` row and a `leftover_saved` alert is stored.

`payday_runs` holds one row per (user_id, month); its primary key is the
idempotency key, so a second run of the month changes nothing. The app role
gets SELECT and INSERT only (append-only, like audit_log). A leftover_save row
carries its payday month, and a partial UNIQUE index keeps it to one per user
per month as a second layer.

The downgrade refuses while payday runs exist: their savings rows and alerts
would no longer fit the narrower type and kind CHECKs.

Revision ID: 8f1c2d4e6a90
Revises: 3d9b7e2a4c61
Create Date: 2026-10-27 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f1c2d4e6a90"
down_revision: str | Sequence[str] | None = "3d9b7e2a4c61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "lumen_app"
SAVINGS_TYPES_BEFORE = "type IN ('auto_save', 'withdrawal')"
SAVINGS_TYPES = "type IN ('auto_save', 'withdrawal', 'leftover_save')"
KINDS_BEFORE = "kind IN ('new_debt', 'cash_withdrawal', 'cash_loan', 'over_cap')"
KINDS = (
    "kind IN ('new_debt', 'cash_withdrawal', 'cash_loan', 'over_cap', "
    "'payday_shortfall', 'leftover_saved')"
)
LEFTOVER_CHECK = "ck_savings_transactions_leftover_save_has_payday_month"
LEFTOVER_INDEX = "uq_savings_transactions_leftover_save_month"


def _replace_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "payday_runs",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("month_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("budget", sa.Numeric(12, 2), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("buffer_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM month) = 1", name=op.f("ck_payday_runs_month_first_day")
        ),
        sa.CheckConstraint(
            "outcome IN ('over_budget', 'leftover_saved', 'no_leftover', 'leftover_off', "
            "'safety_net')",
            name=op.f("ck_payday_runs_outcome_valid"),
        ),
        sa.CheckConstraint("month_total >= 0", name=op.f("ck_payday_runs_month_total_nonneg")),
        sa.CheckConstraint("budget >= 0", name=op.f("ck_payday_runs_budget_nonneg")),
        sa.CheckConstraint(
            "buffer_balance >= 0", name=op.f("ck_payday_runs_buffer_balance_nonneg")
        ),
        sa.CheckConstraint(
            "(outcome IN ('over_budget', 'leftover_saved')) = (amount > 0)",
            name=op.f("ck_payday_runs_amount_with_outcome"),
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_payday_runs_amount_nonneg")),
        sa.PrimaryKeyConstraint("user_id", "month", name=op.f("pk_payday_runs")),
    )
    op.execute(f"GRANT SELECT, INSERT ON payday_runs TO {ROLE}")

    op.add_column("savings_transactions", sa.Column("payday_month", sa.Date(), nullable=True))
    _replace_check("ck_savings_transactions_type_valid", "savings_transactions", SAVINGS_TYPES)
    op.create_check_constraint(
        op.f(LEFTOVER_CHECK),
        "savings_transactions",
        "(type = 'leftover_save') = (payday_month IS NOT NULL)",
    )
    op.create_index(
        LEFTOVER_INDEX,
        "savings_transactions",
        ["user_id", "payday_month"],
        unique=True,
        postgresql_where=sa.text("type = 'leftover_save'"),
    )
    _replace_check("ck_notifications_kind_valid", "notifications", KINDS)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM payday_runs) THEN "
        "RAISE EXCEPTION 'payday runs exist; cannot downgrade'; END IF; END $$"
    )
    _replace_check("ck_notifications_kind_valid", "notifications", KINDS_BEFORE)
    op.drop_index(LEFTOVER_INDEX, table_name="savings_transactions")
    op.drop_constraint(op.f(LEFTOVER_CHECK), "savings_transactions", type_="check")
    _replace_check(
        "ck_savings_transactions_type_valid", "savings_transactions", SAVINGS_TYPES_BEFORE
    )
    op.drop_column("savings_transactions", "payday_month")
    op.drop_table("payday_runs")
