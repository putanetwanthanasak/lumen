"""app role grants

S2 (security review 2026-10-18): the app connects as `lumen_app`, a login role that
is not a superuser and owns no table, so it cannot disable the audit trigger,
TRUNCATE, ALTER or DROP anything. Migrations run as the superuser
(MIGRATION_DATABASE_URL). The role itself is created by
docker/postgres/init/02-create-app-role.sh; this migration fails if it is missing.

Grants are the least the app uses: no DELETE or TRUNCATE anywhere, and audit_log
and savings_transactions are append-only (SELECT, INSERT). A new table gets no
grant until a migration adds one; tests/db/test_schema_snapshot.py pins the set.

Revision ID: a1c3e5f7b9d2
Revises: 55f5b32ae8fb
Create Date: 2026-10-18 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3e5f7b9d2"
down_revision: str | Sequence[str] | None = "55f5b32ae8fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "lumen_app"
GRANTS = {
    "audit_log": "SELECT, INSERT",
    "savings_transactions": "SELECT, INSERT",
    "installments": "SELECT, INSERT, UPDATE",
    "notifications": "SELECT, INSERT, UPDATE",
    "user_balances": "SELECT, INSERT, UPDATE",
    "user_settings": "SELECT, INSERT, UPDATE",
    "webhook_events": "SELECT, INSERT, UPDATE",
}


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    for table, privileges in GRANTS.items():
        op.execute(f"GRANT {privileges} ON {table} TO {ROLE}")


def downgrade() -> None:
    """Downgrade schema."""
    for table in GRANTS:
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
