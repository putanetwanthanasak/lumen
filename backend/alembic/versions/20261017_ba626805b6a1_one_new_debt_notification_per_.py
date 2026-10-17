"""one new-debt notification per installment

Session 9, 04 step 5e and NT-04: a partial UNIQUE index on
notifications(installment_id) over the three new-debt kinds, plus a CHECK that
those kinds carry an installment_id (NULLs never collide in a UNIQUE index).
Hand-written: autogenerate does not see the CHECK or the index WHERE clause
(tests/db/test_schema_snapshot.py does). The kinds are literals here, not imported,
so this migration stays fixed if the model changes later.

Revision ID: ba626805b6a1
Revises: 223146e7868a
Create Date: 2026-10-17 21:41:34.793636

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ba626805b6a1"
down_revision: str | Sequence[str] | None = "223146e7868a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_DEBT_KINDS = "kind IN ('new_debt', 'cash_withdrawal', 'cash_loan')"
INDEX = "uq_notifications_new_debt_installment_id"
CHECK = "ck_notifications_new_debt_has_installment"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        op.f(CHECK), "notifications", f"NOT ({NEW_DEBT_KINDS}) OR installment_id IS NOT NULL"
    )
    op.create_index(
        op.f(INDEX),
        "notifications",
        ["installment_id"],
        unique=True,
        postgresql_where=sa.text(NEW_DEBT_KINDS),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f(INDEX), table_name="notifications")
    op.drop_constraint(op.f(CHECK), "notifications", type_="check")
