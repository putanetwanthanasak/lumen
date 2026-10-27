import pytest
from alembic import command
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import DBAPIError

from app.db import Base
from tests.conftest import alembic_config

pytestmark = pytest.mark.db


def test_upgrade_downgrade_upgrade_roundtrip(migration_engine: Engine) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "base")
    with migration_engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
        fn = "select count(*) from pg_proc where proname = 'audit_log_reject_mutation'"
        assert conn.execute(text(fn)).scalar_one() == 0

    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert set(Base.metadata.tables) <= set(inspect(conn).get_table_names())


def _columns(conn: Connection, table: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(table)}


def test_vendor_key_and_late_fees_downgrade_one_step(migration_engine: Engine) -> None:
    # The L47/L48 revision must undo cleanly: old single-column key, no late fees.
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "ec76c45447e9")  # the revision before it
    with migration_engine.connect() as conn:
        assert "late_fees_accrued" not in _columns(conn, "installments")
        assert "source_vendor" not in _columns(conn, "savings_transactions")
        pk = inspect(conn).get_pk_constraint("webhook_events")
        assert pk["constrained_columns"] == ["event_id"]

    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "late_fees_accrued" in _columns(conn, "installments")
        assert "source_vendor" in _columns(conn, "savings_transactions")
        pk = inspect(conn).get_pk_constraint("webhook_events")
        assert pk["constrained_columns"] == ["vendor", "event_id"]


def _indexes(conn: Connection, table: str) -> set[str]:
    return {i["name"] for i in inspect(conn).get_indexes(table)}


def test_new_debt_notification_guard_downgrade_one_step(migration_engine: Engine) -> None:
    index = "uq_notifications_new_debt_installment_id"
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "223146e7868a")
    with migration_engine.connect() as conn:
        assert index not in _indexes(conn, "notifications")
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert index in _indexes(conn, "notifications")


def test_not_me_dispute_downgrade_one_step(migration_engine: Engine) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "ba626805b6a1")
    with migration_engine.connect() as conn:
        assert "disputed_at" not in _columns(conn, "installments")
        assert "uq_audit_log_installment_disputed" not in _indexes(conn, "audit_log")
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "disputed_at" in _columns(conn, "installments")
        assert "uq_audit_log_installment_disputed" in _indexes(conn, "audit_log")


def test_ST_15_settings_migration_keeps_rows_from_before_L63(migration_engine: Engine) -> None:
    # Review F5: the old CHECK allowed a cap with nothing else. After the rename it
    # would be a budget without a profile, which profile_all_or_none refuses.
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "c4e6a8b0d2f4")
        conn.execute(
            text(
                "INSERT INTO user_settings (user_id, auto_save_enabled, monthly_installment_cap) "
                "VALUES ('mig-cap', true, 3000.00)"
            )
        )
    try:
        with migration_engine.begin() as conn:
            command.upgrade(alembic_config(conn), "head")
        with migration_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT auto_save_enabled, monthly_installment_budget, saving_mode "
                    "FROM user_settings WHERE user_id = 'mig-cap'"
                )
            ).one()
        assert tuple(row) == (True, None, None)  # kept, with no profile: saves nothing
    finally:
        with migration_engine.begin() as conn:
            command.upgrade(alembic_config(conn), "head")
            conn.execute(text("DELETE FROM user_settings WHERE user_id = 'mig-cap'"))


def test_MI_12_manual_installments_downgrade_one_step(migration_engine: Engine) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "13bb1d51a30c")
    with migration_engine.connect() as conn:
        assert "client_request_id" not in _columns(conn, "installments")
        assert "uq_installments_user_client_request_id" not in _indexes(conn, "installments")
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "client_request_id" in _columns(conn, "installments")


def test_MI_12_manual_installments_downgrade_refuses_while_manual_rows_exist(
    migration_engine: Engine,
) -> None:
    # Their NULL debt data cannot become NOT NULL, so the downgrade must stop, not
    # fail half-way or drop data.
    insert = (
        "INSERT INTO installments (user_id, vendor, contract_id, client_request_id, kind, "
        "item_name, principal, months, monthly_amount, first_due_date) VALUES ('mig-user', "
        "'manual', 'mig-c1', 'mig-r1', 'purchase', '', 100.00, 1, 100.00, '2026-11-01')"
    )
    with migration_engine.begin() as conn:
        conn.execute(text(insert))
    try:
        with (
            pytest.raises(DBAPIError, match="manual installments exist"),
            migration_engine.begin() as conn,
        ):
            command.downgrade(alembic_config(conn), "13bb1d51a30c")
        with migration_engine.connect() as conn:
            assert "client_request_id" in _columns(conn, "installments")  # rolled back
    finally:
        with migration_engine.begin() as conn:
            conn.execute(text("DELETE FROM installments WHERE user_id = 'mig-user'"))


def test_BF_10_buffer_withdrawals_downgrade_one_step(migration_engine: Engine) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "fe7ea21fcc85")
    with migration_engine.connect() as conn:
        assert "client_request_id" not in _columns(conn, "savings_transactions")
        assert "uq_savings_transactions_user_client_request_id" not in _indexes(
            conn, "savings_transactions"
        )
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "client_request_id" in _columns(conn, "savings_transactions")


def test_BF_10_buffer_withdrawals_downgrade_refuses_while_withdrawals_exist(
    migration_engine: Engine,
) -> None:
    # Review F4: without the column the row stays, and the CHECK rejects it on the
    # next upgrade. Stop instead.
    insert = (
        "INSERT INTO savings_transactions (user_id, type, amount, client_request_id) "
        "VALUES ('mig-user', 'withdrawal', 1.00, 'mig-r1')"
    )
    with migration_engine.begin() as conn:
        conn.execute(text(insert))
    try:
        with (
            pytest.raises(DBAPIError, match="buffer withdrawals exist"),
            migration_engine.begin() as conn,
        ):
            command.downgrade(alembic_config(conn), "fe7ea21fcc85")
        with migration_engine.connect() as conn:
            assert "client_request_id" in _columns(conn, "savings_transactions")  # rolled back
    finally:
        with migration_engine.begin() as conn:
            conn.execute(text("DELETE FROM savings_transactions WHERE user_id = 'mig-user'"))


def test_PD_08_payday_runs_downgrade_one_step(migration_engine: Engine) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "3d9b7e2a4c61")
    with migration_engine.connect() as conn:
        assert "payday_runs" not in inspect(conn).get_table_names()
        assert "payday_month" not in _columns(conn, "savings_transactions")
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "payday_runs" in inspect(conn).get_table_names()


def test_PD_08_payday_runs_downgrade_refuses_while_runs_exist(migration_engine: Engine) -> None:
    # Their savings rows and alerts would not fit the narrower CHECKs: stop, do not
    # fail half-way or drop data.
    insert = (
        "INSERT INTO payday_runs (user_id, month, month_total, budget, outcome, amount, "
        "buffer_balance) VALUES ('mig-user', '2026-11-01', 0, 0, 'no_leftover', 0, 0)"
    )
    with migration_engine.begin() as conn:
        conn.execute(text(insert))
    try:
        with (
            pytest.raises(DBAPIError, match="payday runs exist"),
            migration_engine.begin() as conn,
        ):
            command.downgrade(alembic_config(conn), "3d9b7e2a4c61")
        with migration_engine.connect() as conn:
            assert "payday_runs" in inspect(conn).get_table_names()  # rolled back
    finally:
        with migration_engine.begin() as conn:
            conn.execute(text("DELETE FROM payday_runs WHERE user_id = 'mig-user'"))


def test_alembic_check_no_drift(migration_engine: Engine) -> None:
    # Raises AutogenerateDiffsDetected if models and migrations disagree.
    with migration_engine.connect() as conn:
        command.check(alembic_config(conn))
