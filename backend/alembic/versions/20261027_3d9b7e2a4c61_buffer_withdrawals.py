"""buffer withdrawals

L66: the user moves buffer (savings) money back to the main account. Each move
is a `withdrawal` row carrying the client's request id; with the user it is the
idempotency key, through a partial UNIQUE index on (user_id, client_request_id).
A CHECK keeps the id on withdrawals and only on withdrawals.

The app never wrote a withdrawal before this revision, so no existing row lacks
an id. The downgrade refuses while withdrawals exist: dropping the column would
leave rows that the CHECK rejects on the next upgrade (review F4).

Revision ID: 3d9b7e2a4c61
Revises: fe7ea21fcc85
Create Date: 2026-10-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d9b7e2a4c61"
down_revision: str | Sequence[str] | None = "fe7ea21fcc85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_savings_transactions_withdrawal_has_client_request_id"
INDEX = "uq_savings_transactions_user_client_request_id"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("savings_transactions", sa.Column("client_request_id", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f(CHECK),
        "savings_transactions",
        "(type = 'withdrawal') = (client_request_id IS NOT NULL)",
    )
    op.create_index(
        INDEX,
        "savings_transactions",
        ["user_id", "client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM savings_transactions "
        "WHERE type = 'withdrawal') THEN "
        "RAISE EXCEPTION 'buffer withdrawals exist; cannot downgrade'; END IF; END $$"
    )
    op.drop_index(INDEX, table_name="savings_transactions")
    op.drop_constraint(op.f(CHECK), "savings_transactions", type_="check")
    op.drop_column("savings_transactions", "client_request_id")
