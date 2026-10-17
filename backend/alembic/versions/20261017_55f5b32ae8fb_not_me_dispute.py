"""not me dispute

L42 "Not me": installments.disputed_at, a CHECK that a disputed installment has it,
and a partial UNIQUE index so one installment gets at most one dispute audit row.
The CHECK and the index WHERE clause are hand-written (autogenerate sees neither;
tests/db/test_schema_snapshot.py does). Literals, not imports, so this migration
stays fixed if the model changes later.

Downgrade drops disputed_at. Run it only before any real dispute exists: the
dispute history it holds would be lost.

Revision ID: 55f5b32ae8fb
Revises: ba626805b6a1
Create Date: 2026-10-17 23:05:12.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "55f5b32ae8fb"
down_revision: str | Sequence[str] | None = "ba626805b6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_installments_disputed_has_disputed_at"
INDEX = "uq_audit_log_installment_disputed"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "installments", sa.Column("disputed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f(CHECK), "installments", "status <> 'disputed' OR disputed_at IS NOT NULL"
    )
    op.create_index(
        op.f(INDEX),
        "audit_log",
        ["ref_id"],
        unique=True,
        postgresql_where=sa.text("action = 'installment_disputed'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f(INDEX), table_name="audit_log")
    op.drop_constraint(op.f(CHECK), "installments", type_="check")
    op.drop_column("installments", "disputed_at")
