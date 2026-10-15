"""vendor event key and late fees

L47: the idempotency key is (vendor, event_id), so webhook_events gets a
composite PK and savings_transactions references the pair (new source_vendor,
backfilled from webhook_events). The INV-3 partial UNIQUE moves to the pair.
L48: installments.late_fees_accrued, and INV-6 becomes
paid_amount <= principal + fee_total + late_fees_accrued.

Autogenerate detected only the columns, index and FK. The PK swap, the backfill
and every CHECK are hand-written (autogenerate detects none of them; see
tests/db/test_schema_snapshot.py).

Downgrade fails loudly at the PK step if two vendors already share an event_id,
since the old single-column key cannot hold that data.

Revision ID: 223146e7868a
Revises: ec76c45447e9
Create Date: 2026-10-15 18:37:05.461951

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "223146e7868a"
down_revision: str | Sequence[str] | None = "ec76c45447e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SOURCE_INDEX = "uq_savings_transactions_auto_save_source_event_id"
NEW_SOURCE_INDEX = "uq_savings_transactions_auto_save_source_event"
AUTO_SAVE_ONLY = sa.text("type = 'auto_save'")


def upgrade() -> None:
    """Upgrade schema."""
    # --- L47: (vendor, event_id) -------------------------------------------------
    op.drop_constraint(
        op.f("fk_savings_transactions_source_event_id_webhook_events"),
        "savings_transactions",
        type_="foreignkey",
    )
    op.drop_index(OLD_SOURCE_INDEX, table_name="savings_transactions")
    op.drop_constraint(
        op.f("ck_savings_transactions_auto_save_has_source_event"),
        "savings_transactions",
        type_="check",
    )
    op.add_column("savings_transactions", sa.Column("source_vendor", sa.Text(), nullable=True))
    # Event ids are still unique here (old PK), so the join finds at most one vendor.
    op.execute(
        sa.text(
            "UPDATE savings_transactions AS s SET source_vendor = w.vendor "
            "FROM webhook_events AS w WHERE w.event_id = s.source_event_id"
        )
    )
    op.drop_constraint(op.f("pk_webhook_events"), "webhook_events", type_="primary")
    op.create_primary_key(op.f("pk_webhook_events"), "webhook_events", ["vendor", "event_id"])
    op.create_foreign_key(
        op.f("fk_savings_transactions_source_vendor_webhook_events"),
        "savings_transactions",
        "webhook_events",
        ["source_vendor", "source_event_id"],
        ["vendor", "event_id"],
    )
    op.create_check_constraint(
        op.f("ck_savings_transactions_source_event_pair_complete"),
        "savings_transactions",
        "(source_vendor IS NULL) = (source_event_id IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_savings_transactions_auto_save_has_source_event"),
        "savings_transactions",
        "type <> 'auto_save' OR (source_vendor IS NOT NULL AND source_event_id IS NOT NULL)",
    )
    op.create_index(
        NEW_SOURCE_INDEX,
        "savings_transactions",
        ["source_vendor", "source_event_id"],
        unique=True,
        postgresql_where=AUTO_SAVE_ONLY,
    )

    # --- L48: late fees and INV-6 ------------------------------------------------
    op.add_column(
        "installments",
        sa.Column(
            "late_fees_accrued",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_installments_late_fees_accrued_nonneg"),
        "installments",
        "late_fees_accrued >= 0",
    )
    op.drop_constraint(op.f("ck_installments_paid_le_total"), "installments", type_="check")
    op.create_check_constraint(
        op.f("ck_installments_paid_le_total"),
        "installments",
        "paid_amount <= principal + fee_total + late_fees_accrued",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # --- L48 ---------------------------------------------------------------------
    op.drop_constraint(op.f("ck_installments_paid_le_total"), "installments", type_="check")
    op.create_check_constraint(
        op.f("ck_installments_paid_le_total"),
        "installments",
        "paid_amount <= principal + fee_total",
    )
    op.drop_constraint(
        op.f("ck_installments_late_fees_accrued_nonneg"), "installments", type_="check"
    )
    op.drop_column("installments", "late_fees_accrued")

    # --- L47 ---------------------------------------------------------------------
    op.drop_index(NEW_SOURCE_INDEX, table_name="savings_transactions")
    op.drop_constraint(
        op.f("ck_savings_transactions_auto_save_has_source_event"),
        "savings_transactions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_savings_transactions_source_event_pair_complete"),
        "savings_transactions",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_savings_transactions_source_vendor_webhook_events"),
        "savings_transactions",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("pk_webhook_events"), "webhook_events", type_="primary")
    op.create_primary_key(op.f("pk_webhook_events"), "webhook_events", ["event_id"])
    op.drop_column("savings_transactions", "source_vendor")
    op.create_check_constraint(
        op.f("ck_savings_transactions_auto_save_has_source_event"),
        "savings_transactions",
        "type <> 'auto_save' OR source_event_id IS NOT NULL",
    )
    op.create_index(
        OLD_SOURCE_INDEX,
        "savings_transactions",
        ["source_event_id"],
        unique=True,
        postgresql_where=AUTO_SAVE_ONLY,
    )
    op.create_foreign_key(
        op.f("fk_savings_transactions_source_event_id_webhook_events"),
        "savings_transactions",
        "webhook_events",
        ["source_event_id"],
        ["event_id"],
    )
