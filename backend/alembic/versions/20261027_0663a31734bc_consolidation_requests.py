"""consolidation requests and payouts

L70, L71: one row per consolidation request, approved or declined, with UNIQUE
(user_id, client_request_id) as the idempotency key. L72: one payout row per
paid-off installment (UNIQUE installment_id, UNIQUE idempotency_key). The app role
gets SELECT and INSERT only: both tables are append-only.

The approved loan is a new debt (L58), so the notification kind
`consolidation_loan` joins the new-debt kinds: the CHECK and the one-alert-per-
installment index are rebuilt with it.

The downgrade refuses while requests exist, or while an alert of the new kind
exists: the narrower CHECKs would reject it.

Revision ID: 0663a31734bc
Revises: 31616ed1dc70
Create Date: 2026-10-27 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0663a31734bc"
down_revision: str | Sequence[str] | None = "31616ed1dc70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "lumen_app"
KINDS_BEFORE = (
    "kind IN ('new_debt', 'cash_withdrawal', 'cash_loan', 'over_cap', "
    "'payday_shortfall', 'leftover_saved')"
)
KINDS = (
    "kind IN ('new_debt', 'cash_withdrawal', 'cash_loan', 'over_cap', "
    "'payday_shortfall', 'leftover_saved', 'consolidation_loan')"
)
NEW_DEBT_BEFORE = "kind IN ('new_debt', 'cash_withdrawal', 'cash_loan')"
NEW_DEBT = "kind IN ('new_debt', 'cash_withdrawal', 'cash_loan', 'consolidation_loan')"
NEW_DEBT_CHECK = "ck_notifications_new_debt_has_installment"
NEW_DEBT_INDEX = "uq_notifications_new_debt_installment_id"


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _new_debt_guard(kinds: str) -> None:
    op.drop_index(op.f(NEW_DEBT_INDEX), table_name="notifications")
    op.drop_constraint(op.f(NEW_DEBT_CHECK), "notifications", type_="check")
    op.create_check_constraint(
        op.f(NEW_DEBT_CHECK), "notifications", f"NOT ({kinds}) OR installment_id IS NOT NULL"
    )
    op.create_index(
        op.f(NEW_DEBT_INDEX),
        "notifications",
        ["installment_id"],
        unique=True,
        postgresql_where=sa.text(kinds),
    )


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_notifications_kind_valid"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind_valid"), "notifications", kinds)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "consolidation_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payoffs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("principal", sa.Numeric(12, 2), nullable=False),
        sa.Column("annual_rate", sa.Numeric(7, 6), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("monthly_payment", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("decision_reference", sa.Text(), nullable=False),
        sa.Column("loan_installment_id", sa.UUID(), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('approved', 'declined')",
            name=op.f("ck_consolidation_requests_status_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'approved') = (loan_installment_id IS NOT NULL)",
            name=op.f("ck_consolidation_requests_approved_has_loan"),
        ),
        sa.CheckConstraint(
            "principal > 0", name=op.f("ck_consolidation_requests_principal_positive")
        ),
        sa.CheckConstraint(
            "annual_rate >= 0", name=op.f("ck_consolidation_requests_annual_rate_nonneg")
        ),
        sa.CheckConstraint(
            "term_months BETWEEN 1 AND 600",
            name=op.f("ck_consolidation_requests_term_months_range"),
        ),
        sa.CheckConstraint(
            "monthly_payment > 0", name=op.f("ck_consolidation_requests_monthly_payment_positive")
        ),
        sa.CheckConstraint(
            "total_cost = monthly_payment * term_months",
            name=op.f("ck_consolidation_requests_total_cost_rule"),
        ),
        sa.ForeignKeyConstraint(
            ["loan_installment_id"],
            ["installments.id"],
            name=op.f("fk_consolidation_requests_loan_installment_id_installments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consolidation_requests")),
        sa.UniqueConstraint(
            "user_id",
            "client_request_id",
            name=op.f("uq_consolidation_requests_user_id_client_request_id"),
        ),
    )
    op.create_index(
        op.f("ix_consolidation_requests_user_id"), "consolidation_requests", ["user_id"]
    )
    op.create_table(
        "consolidation_payouts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("installment_id", sa.UUID(), nullable=False),
        sa.Column("vendor", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        _created_at(),
        sa.CheckConstraint("amount > 0", name=op.f("ck_consolidation_payouts_amount_positive")),
        sa.ForeignKeyConstraint(
            ["installment_id"],
            ["installments.id"],
            name=op.f("fk_consolidation_payouts_installment_id_installments"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["consolidation_requests.id"],
            name=op.f("fk_consolidation_payouts_request_id_consolidation_requests"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consolidation_payouts")),
        sa.UniqueConstraint(
            "idempotency_key", name=op.f("uq_consolidation_payouts_idempotency_key")
        ),
        sa.UniqueConstraint("installment_id", name=op.f("uq_consolidation_payouts_installment_id")),
    )
    op.create_index(op.f("ix_consolidation_payouts_user_id"), "consolidation_payouts", ["user_id"])
    op.execute(f"GRANT SELECT, INSERT ON consolidation_requests TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON consolidation_payouts TO {ROLE}")
    _kinds(KINDS)
    _new_debt_guard(NEW_DEBT)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM consolidation_requests) "
        "OR EXISTS (SELECT 1 FROM notifications WHERE kind = 'consolidation_loan') THEN "
        "RAISE EXCEPTION 'consolidation requests exist; cannot downgrade'; END IF; END $$"
    )
    _new_debt_guard(NEW_DEBT_BEFORE)
    _kinds(KINDS_BEFORE)
    op.drop_index(op.f("ix_consolidation_payouts_user_id"), table_name="consolidation_payouts")
    op.drop_table("consolidation_payouts")
    op.drop_index(op.f("ix_consolidation_requests_user_id"), table_name="consolidation_requests")
    op.drop_table("consolidation_requests")
