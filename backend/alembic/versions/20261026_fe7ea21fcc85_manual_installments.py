"""manual installments

L62: the user records installments themselves. A manual row has vendor
'manual' and the client's request id, which is the idempotency key through a
partial UNIQUE index on (user_id, client_request_id). The L41 platform debt
data (min_payment, late_fee_per_period, monthly_rate) becomes nullable for
manual rows only: unknown is stored as NULL, never as a made-up 0.

An auto_save from a manual entry has no webhook event, so the CHECK
auto_save_has_source_event is dropped. One auto_save per installment is still
enforced by uq_savings_transactions_auto_save_installment_id, and one per event
by uq_savings_transactions_auto_save_source_event.

The downgrade refuses to run while manual rows exist: it cannot make their
NULL debt data NOT NULL or give their auto_saves a source event.

Revision ID: fe7ea21fcc85
Revises: 13bb1d51a30c
Create Date: 2026-10-26 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe7ea21fcc85"
down_revision: str | Sequence[str] | None = "13bb1d51a30c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEBT_DATA = ("min_payment", "late_fee_per_period", "monthly_rate")
INDEX = "uq_installments_user_client_request_id"
SOURCE_EVENT = "ck_savings_transactions_auto_save_has_source_event"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("installments", sa.Column("client_request_id", sa.Text(), nullable=True))
    for column in DEBT_DATA:
        op.alter_column("installments", column, nullable=True)
    op.create_check_constraint(
        op.f("ck_installments_manual_has_client_request_id"),
        "installments",
        "(vendor = 'manual') = (client_request_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_installments_platform_debt_data_complete"),
        "installments",
        "vendor = 'manual' OR (min_payment IS NOT NULL "
        "AND late_fee_per_period IS NOT NULL AND monthly_rate IS NOT NULL)",
    )
    op.create_index(
        INDEX,
        "installments",
        ["user_id", "client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
    )
    op.drop_constraint(op.f(SOURCE_EVENT), "savings_transactions", type_="check")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM installments WHERE vendor = 'manual') THEN "
        "RAISE EXCEPTION 'manual installments exist; cannot downgrade'; END IF; END $$"
    )
    op.create_check_constraint(
        op.f(SOURCE_EVENT),
        "savings_transactions",
        "type <> 'auto_save' OR (source_vendor IS NOT NULL AND source_event_id IS NOT NULL)",
    )
    op.drop_index(INDEX, table_name="installments")
    op.drop_constraint(
        op.f("ck_installments_platform_debt_data_complete"), "installments", type_="check"
    )
    op.drop_constraint(
        op.f("ck_installments_manual_has_client_request_id"), "installments", type_="check"
    )
    for column in DEBT_DATA:
        op.alter_column("installments", column, nullable=False)
    op.drop_column("installments", "client_request_id")
