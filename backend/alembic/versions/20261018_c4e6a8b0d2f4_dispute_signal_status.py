"""dispute signal status

L60 (2) / S4: installments.dispute_signal_status records whether the platform got
the "Not me" report (pending / sent / failed), so the message never claims it was
sent when it was not, and a repeat tap can try again. Two hand-written CHECKs
(tests/db/test_schema_snapshot.py sees them): the allowed values, and "a status
exactly when there is a report".

Existing reports are backfilled as 'pending': nothing recorded whether their
signal went out, so the next tap re-sends rather than claim it was sent.

Revision ID: c4e6a8b0d2f4
Revises: a1c3e5f7b9d2
Create Date: 2026-10-18 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e6a8b0d2f4"
down_revision: str | Sequence[str] | None = "a1c3e5f7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VALID = "ck_installments_dispute_signal_status_valid"
WITH_REPORT = "ck_installments_dispute_signal_status_with_report"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("installments", sa.Column("dispute_signal_status", sa.Text(), nullable=True))
    op.execute(
        "UPDATE installments SET dispute_signal_status = 'pending' WHERE disputed_at IS NOT NULL"
    )
    op.create_check_constraint(
        op.f(VALID), "installments", "dispute_signal_status IN ('pending', 'sent', 'failed')"
    )
    op.create_check_constraint(
        op.f(WITH_REPORT),
        "installments",
        "(disputed_at IS NULL) = (dispute_signal_status IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f(WITH_REPORT), "installments", type_="check")
    op.drop_constraint(op.f(VALID), "installments", type_="check")
    op.drop_column("installments", "dispute_signal_status")
