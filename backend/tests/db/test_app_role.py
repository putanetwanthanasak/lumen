"""S2: the app connects as lumen_app, which cannot erase or rewrite history.

The review found the app connected as the Postgres superuser that owns every table,
so one session could switch off the audit trigger and delete dispute history. These
tests connect exactly as the app does (TEST_DATABASE_URL) and try each attack.
The grants themselves are pinned in tests/db/test_schema_snapshot.py.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import models

pytestmark = pytest.mark.db

INSUFFICIENT_PRIVILEGE = "42501"
APPEND_ONLY = (
    "audit_log",
    "consolidation_payouts",
    "consolidation_requests",
    "payday_runs",
    "savings_transactions",
)
# From app.models, not app.db: Base.metadata is empty until the models are imported.
TABLES = sorted(models.Base.metadata.tables)


def test_S2_app_role_is_not_superuser_and_owns_nothing(engine: Engine) -> None:
    with engine.connect() as conn:
        role = conn.execute(
            text(
                "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, "
                "rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        owned = conn.execute(
            text(
                "SELECT count(*) FROM pg_class WHERE relowner = "
                "(SELECT oid FROM pg_roles WHERE rolname = current_user)"
            )
        ).scalar_one()
    assert tuple(role) == ("lumen_app", False, False, False, False, False)
    assert owned == 0


def test_S2_every_table_is_checked() -> None:
    assert len(TABLES) == 10  # a silent empty list once skipped the test below


@pytest.mark.parametrize("table", TABLES)
def test_S2_app_role_has_no_delete_or_truncate(engine: Engine, table: str) -> None:
    with engine.connect() as conn:
        allowed = conn.execute(
            text(
                "SELECT has_table_privilege(current_user, :t, 'DELETE'), "
                "has_table_privilege(current_user, :t, 'TRUNCATE'), "
                "has_table_privilege(current_user, :t, 'UPDATE'), "
                "has_table_privilege(current_user, :t, 'INSERT')"
            ),
            {"t": table},
        ).one()
    delete, truncate, update, insert = allowed
    assert (delete, truncate) == (False, False)
    assert update is (table not in APPEND_ONLY)
    assert insert is True


ATTACKS = {
    "replica_mode_skips_triggers": "SET session_replication_role = replica",
    "disable_audit_trigger": "ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only",
    "delete_audit": "DELETE FROM audit_log",
    "update_audit": "UPDATE audit_log SET action = 'edited'",
    "truncate_audit": "TRUNCATE audit_log",
    "drop_audit": "DROP TABLE audit_log",
    "delete_savings": "DELETE FROM savings_transactions",
    "update_savings": "UPDATE savings_transactions SET amount = amount",
    # L67: the payday run is the once-per-month key; erasing it would allow a rerun.
    "delete_payday_run": "DELETE FROM payday_runs",
    "update_payday_run": "UPDATE payday_runs SET amount = amount",
    # L72: a decided request and its payouts are the record of what the bank paid.
    "delete_consolidation_request": "DELETE FROM consolidation_requests",
    "update_consolidation_request": "UPDATE consolidation_requests SET status = 'declined'",
    "delete_consolidation_payout": "DELETE FROM consolidation_payouts",
    "update_consolidation_payout": "UPDATE consolidation_payouts SET amount = amount",
    "delete_installments": "DELETE FROM installments",
    "drop_dispute_check": (
        "ALTER TABLE installments DROP CONSTRAINT ck_installments_disputed_has_disputed_at"
    ),
    "run_os_command": "COPY (SELECT 1) TO PROGRAM 'true'",
    "create_table": "CREATE TABLE public.lumen_probe (id int)",
}


@pytest.mark.parametrize("sql", list(ATTACKS.values()), ids=list(ATTACKS))
def test_S2_app_role_cannot_tamper(db_session: Session, sql: str) -> None:
    with pytest.raises(DBAPIError) as exc:
        db_session.execute(text(sql))
    assert exc.value.orig is not None
    assert exc.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE  # type: ignore[attr-defined]
    # Refused by the grants, before any trigger runs.
    assert "append-only" not in str(exc.value.orig)
