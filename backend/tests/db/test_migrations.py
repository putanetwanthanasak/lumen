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


def _checks(conn: Connection, table: str) -> set[str]:
    return {str(c["name"]) for c in inspect(conn).get_check_constraints(table)}


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


# The installments CHECKs as they were before L72 (the snapshot on main).
CHECKS_BEFORE_L72 = {
    "ck_installments_kind_valid": (
        "CHECK ((kind = ANY (ARRAY['purchase'::text, 'cash_withdrawal'::text, 'cash_loan'::text])))"
    ),
    "ck_installments_status_valid": (
        "CHECK ((status = ANY (ARRAY['active'::text, 'paid_off'::text, 'cancelled'::text, "
        "'disputed'::text])))"
    ),
    "ck_installments_platform_debt_data_complete": (
        "CHECK (((vendor = 'manual'::text) OR ((min_payment IS NOT NULL) AND "
        "(late_fee_per_period IS NOT NULL) AND (monthly_rate IS NOT NULL))))"
    ),
}


def _check_texts(conn: Connection, names: list[str]) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = ANY(:names)"
        ),
        {"names": names},
    )
    return {str(name): str(definition) for name, definition in rows.all()}


def test_CO_05_consolidation_loan_kind_downgrade_one_step(migration_engine: Engine) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "8f1c2d4e6a90")
    with migration_engine.connect() as conn:
        checks = _checks(conn, "installments")
        assert "ck_installments_consolidation_loan_vendor" not in checks
        assert "ck_installments_consolidation_loan_terms" not in checks
        # The widened CHECKs are narrowed back exactly (review F3).
        assert _check_texts(conn, list(CHECKS_BEFORE_L72)) == CHECKS_BEFORE_L72
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "ck_installments_consolidation_loan_vendor" in _checks(conn, "installments")


@pytest.mark.parametrize(
    "row",
    [
        {"vendor": "consolidation", "kind": "consolidation_loan", "status": "active"},
        {"vendor": "shopdemo", "kind": "purchase", "status": "consolidated"},
    ],
)
def test_CO_05_consolidation_loan_kind_downgrade_refuses_while_rows_exist(
    migration_engine: Engine, row: dict[str, str]
) -> None:
    # The narrower CHECKs would reject the row on the way down: stop instead.
    insert = text(
        "INSERT INTO installments (user_id, vendor, kind, status, contract_id, item_name, "
        "principal, months, monthly_amount, first_due_date, min_payment, monthly_rate, "
        "late_fee_per_period) VALUES ('mig-user', :vendor, :kind, :status, 'mig-c1', 'x', "
        "1.00, 1, 1.00, '2026-11-01', 1.00, 0, 0)"
    )
    with migration_engine.begin() as conn:
        conn.execute(insert, row)
    try:
        with (
            pytest.raises(DBAPIError, match="consolidation rows exist"),
            migration_engine.begin() as conn,
        ):
            command.downgrade(alembic_config(conn), "8f1c2d4e6a90")
        with migration_engine.connect() as conn:
            assert "ck_installments_consolidation_loan_vendor" in _checks(conn, "installments")
    finally:
        with migration_engine.begin() as conn:
            conn.execute(text("DELETE FROM installments WHERE user_id = 'mig-user'"))


NOTIFICATIONS_BEFORE_CONSOLIDATION = {
    "ck_notifications_kind_valid": (
        "CHECK ((kind = ANY (ARRAY['new_debt'::text, 'cash_withdrawal'::text, 'cash_loan'::text, "
        "'over_cap'::text, 'payday_shortfall'::text, 'leftover_saved'::text])))"
    ),
    "ck_notifications_new_debt_has_installment": (
        "CHECK (((NOT (kind = ANY (ARRAY['new_debt'::text, 'cash_withdrawal'::text, "
        "'cash_loan'::text]))) OR (installment_id IS NOT NULL)))"
    ),
}


def test_CO_05_consolidation_requests_downgrade_one_step(migration_engine: Engine) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "31616ed1dc70")
    with migration_engine.connect() as conn:
        tables = inspect(conn).get_table_names()
        assert "consolidation_requests" not in tables
        assert "consolidation_payouts" not in tables
        checks = _check_texts(conn, list(NOTIFICATIONS_BEFORE_CONSOLIDATION))
        assert checks == NOTIFICATIONS_BEFORE_CONSOLIDATION
        assert "'consolidation_loan'" not in str(
            conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'uq_notifications_new_debt_installment_id'"
                )
            ).scalar_one()
        )
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "consolidation_requests" in inspect(conn).get_table_names()


def test_CO_05_consolidation_requests_downgrade_refuses_while_requests_exist(
    migration_engine: Engine,
) -> None:
    # A decided request is the record of what the bank was asked: never dropped.
    insert = text(
        "INSERT INTO consolidation_requests (id, user_id, client_request_id, status, payoffs, "
        "principal, annual_rate, term_months, monthly_payment, total_cost, "
        "decision_reference) VALUES (gen_random_uuid(), 'mig-user', 'req-1', 'declined', "
        "'[]', 1.00, 0, 1, 1.00, 1.00, 'MOCK-mig')"
    )
    with migration_engine.begin() as conn:
        conn.execute(insert)
    try:
        with (
            pytest.raises(DBAPIError, match="consolidation requests exist"),
            migration_engine.begin() as conn,
        ):
            command.downgrade(alembic_config(conn), "31616ed1dc70")
        with migration_engine.connect() as conn:
            assert "consolidation_requests" in inspect(conn).get_table_names()  # rolled back
    finally:
        with migration_engine.begin() as conn:
            conn.execute(text("DELETE FROM consolidation_requests WHERE user_id = 'mig-user'"))


def test_BF_11_MI_13_for_month_and_platform_name_downgrade_one_step(
    migration_engine: Engine,
) -> None:
    with migration_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "0663a31734bc")
    with migration_engine.connect() as conn:
        assert "for_month" not in _columns(conn, "savings_transactions")
        assert "platform_name" not in _columns(conn, "installments")
    with migration_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with migration_engine.connect() as conn:
        assert "for_month" in _columns(conn, "savings_transactions")
        assert "platform_name" in _columns(conn, "installments")
