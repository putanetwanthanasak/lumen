# ruff: noqa: E501  (each definition stays on one line, exactly as Postgres renders it)
"""Schema snapshot (review M3): the exact definitions Postgres holds after `upgrade head`.

`alembic check` compares tables, columns, types, index columns, FKs and (with
compare_server_default) server defaults. It does not see CHECK expressions,
primary-key changes or partial-index WHERE clauses. Verified by break tests: a
migration whose INV-6 CHECK omits `+ late_fees_accrued`, or whose INV-3 index says
`WHERE type = 'withdrawal'`, passes `alembic check`; both fail here.

The expected values are Postgres's own rendering (pg_get_constraintdef, pg_indexes,
information_schema). They were captured once from a fresh `upgrade head` and each
line was checked by hand against app/models.py. A schema change must update this
file in the same PR, which makes every constraint change visible in review.

It reads the catalogs as the schema owner: information_schema hides from the app
role whatever it has no grant on. EXPECTED_APP_GRANTS pins what lumen_app may do (S2),
so a new table without a grant, or a widened grant, shows up here.
"""

import pytest
from sqlalchemy import Connection, Engine, text

pytestmark = pytest.mark.db

EXPECTED_CONSTRAINTS: dict[str, dict[str, str]] = {
    "audit_log": {
        "ck_audit_log_actor_valid": "CHECK ((actor = ANY (ARRAY['system'::text, 'user'::text])))",
        "pk_audit_log": "PRIMARY KEY (id)",
    },
    "installments": {
        "ck_installments_dispute_signal_status_valid": "CHECK ((dispute_signal_status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text])))",
        "ck_installments_dispute_signal_status_with_report": "CHECK (((disputed_at IS NULL) = (dispute_signal_status IS NULL)))",
        "ck_installments_disputed_has_disputed_at": "CHECK (((status <> 'disputed'::text) OR (disputed_at IS NOT NULL)))",
        "ck_installments_fee_total_nonneg": "CHECK ((fee_total >= (0)::numeric))",
        "ck_installments_kind_valid": "CHECK ((kind = ANY (ARRAY['purchase'::text, 'cash_withdrawal'::text, 'cash_loan'::text])))",
        "ck_installments_late_fee_nonneg": "CHECK ((late_fee_per_period >= (0)::numeric))",
        "ck_installments_late_fees_accrued_nonneg": "CHECK ((late_fees_accrued >= (0)::numeric))",
        "ck_installments_min_payment_nonneg": "CHECK ((min_payment >= (0)::numeric))",
        "ck_installments_monthly_amount_nonneg": "CHECK ((monthly_amount >= (0)::numeric))",
        "ck_installments_monthly_rate_nonneg": "CHECK ((monthly_rate >= (0)::numeric))",
        "ck_installments_months_positive": "CHECK ((months > 0))",
        "ck_installments_overdue_days_nonneg": "CHECK ((overdue_days >= 0))",
        "ck_installments_paid_amount_nonneg": "CHECK ((paid_amount >= (0)::numeric))",
        "ck_installments_paid_le_total": "CHECK ((paid_amount <= ((principal + fee_total) + late_fees_accrued)))",
        "ck_installments_principal_positive": "CHECK ((principal > (0)::numeric))",
        "ck_installments_status_valid": "CHECK ((status = ANY (ARRAY['active'::text, 'paid_off'::text, 'cancelled'::text, 'disputed'::text])))",
        "pk_installments": "PRIMARY KEY (id)",
        "uq_installments_vendor_contract_id": "UNIQUE (vendor, contract_id)",
    },
    "notifications": {
        "ck_notifications_delivery_status_valid": "CHECK ((delivery_status = ANY (ARRAY['pending'::text, 'pushed'::text, 'inbox_only'::text])))",
        "ck_notifications_new_debt_has_installment": "CHECK (((NOT (kind = ANY (ARRAY['new_debt'::text, 'cash_withdrawal'::text, 'cash_loan'::text]))) OR (installment_id IS NOT NULL)))",
        "ck_notifications_kind_valid": "CHECK ((kind = ANY (ARRAY['new_debt'::text, 'cash_withdrawal'::text, 'cash_loan'::text, 'over_cap'::text])))",
        "ck_notifications_push_attempts_nonneg": "CHECK ((push_attempts >= 0))",
        "ck_notifications_user_response_valid": "CHECK ((user_response = ANY (ARRAY['none'::text, 'not_me'::text])))",
        "fk_notifications_installment_id_installments": "FOREIGN KEY (installment_id) REFERENCES installments(id)",
        "pk_notifications": "PRIMARY KEY (id)",
    },
    "savings_transactions": {
        "ck_savings_transactions_amount_positive": "CHECK ((amount > (0)::numeric))",
        "ck_savings_transactions_auto_save_has_installment": "CHECK (((type <> 'auto_save'::text) OR (installment_id IS NOT NULL)))",
        "ck_savings_transactions_auto_save_has_source_event": "CHECK (((type <> 'auto_save'::text) OR ((source_vendor IS NOT NULL) AND (source_event_id IS NOT NULL))))",
        "ck_savings_transactions_source_event_pair_complete": "CHECK (((source_vendor IS NULL) = (source_event_id IS NULL)))",
        "ck_savings_transactions_type_valid": "CHECK ((type = ANY (ARRAY['auto_save'::text, 'withdrawal'::text])))",
        "fk_savings_transactions_installment_id_installments": "FOREIGN KEY (installment_id) REFERENCES installments(id)",
        "fk_savings_transactions_source_vendor_webhook_events": "FOREIGN KEY (source_vendor, source_event_id) REFERENCES webhook_events(vendor, event_id)",
        "pk_savings_transactions": "PRIMARY KEY (id)",
    },
    "user_balances": {
        "ck_user_balances_savings_balance_nonneg": "CHECK ((savings_balance >= (0)::numeric))",
        "ck_user_balances_version_nonneg": "CHECK ((version >= 0))",
        "pk_user_balances": "PRIMARY KEY (user_id)",
    },
    "user_settings": {
        "ck_user_settings_income_positive": "CHECK ((income > (0)::numeric))",
        "ck_user_settings_monthly_budget_nonneg": "CHECK ((monthly_installment_budget >= (0)::numeric))",
        "ck_user_settings_payday_day_of_month": "CHECK (((payday >= 1) AND (payday <= 31)))",
        "ck_user_settings_profile_all_or_none": "CHECK ((num_nulls(income, payday, monthly_installment_budget, saving_mode) = ANY (ARRAY[0, 4])))",
        "ck_user_settings_saving_fixed_amount_positive": "CHECK ((saving_fixed_amount > (0)::numeric))",
        "ck_user_settings_saving_fixed_amount_with_mode": "CHECK (((saving_fixed_amount IS NOT NULL) = (NOT (saving_mode IS DISTINCT FROM 'fixed'::text))))",
        "ck_user_settings_saving_mode_valid": "CHECK ((saving_mode = ANY (ARRAY['percent'::text, 'fixed'::text])))",
        "ck_user_settings_saving_percent_range": "CHECK (((saving_percent >= 1) AND (saving_percent <= 100)))",
        "ck_user_settings_saving_percent_with_mode": "CHECK (((saving_percent IS NOT NULL) = (NOT (saving_mode IS DISTINCT FROM 'percent'::text))))",
        "pk_user_settings": "PRIMARY KEY (user_id)",
    },
    "webhook_events": {
        "ck_webhook_events_event_type_valid": "CHECK ((event_type = ANY (ARRAY['installment_created'::text, 'cash_withdrawal_created'::text, 'cash_loan_created'::text, 'installment_payment_collected'::text, 'installment_overdue'::text, 'installment_cancelled'::text])))",
        "ck_webhook_events_status_valid": "CHECK ((status = ANY (ARRAY['processed'::text, 'pending_parent'::text, 'rejected'::text])))",
        "pk_webhook_events": "PRIMARY KEY (vendor, event_id)",
    },
}

EXPECTED_INDEXES: dict[str, dict[str, str]] = {
    "audit_log": {
        "ix_audit_log_user_id": "CREATE INDEX ix_audit_log_user_id ON public.audit_log USING btree (user_id)",
        "pk_audit_log": "CREATE UNIQUE INDEX pk_audit_log ON public.audit_log USING btree (id)",
        "uq_audit_log_installment_disputed": "CREATE UNIQUE INDEX uq_audit_log_installment_disputed ON public.audit_log USING btree (ref_id) WHERE (action = 'installment_disputed'::text)",
    },
    "installments": {
        "ix_installments_user_id": "CREATE INDEX ix_installments_user_id ON public.installments USING btree (user_id)",
        "pk_installments": "CREATE UNIQUE INDEX pk_installments ON public.installments USING btree (id)",
        "uq_installments_vendor_contract_id": "CREATE UNIQUE INDEX uq_installments_vendor_contract_id ON public.installments USING btree (vendor, contract_id)",
    },
    "notifications": {
        "ix_notifications_user_id": "CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id)",
        "pk_notifications": "CREATE UNIQUE INDEX pk_notifications ON public.notifications USING btree (id)",
        "uq_notifications_new_debt_installment_id": "CREATE UNIQUE INDEX uq_notifications_new_debt_installment_id ON public.notifications USING btree (installment_id) WHERE (kind = ANY (ARRAY['new_debt'::text, 'cash_withdrawal'::text, 'cash_loan'::text]))",
    },
    "savings_transactions": {
        "ix_savings_transactions_user_id": "CREATE INDEX ix_savings_transactions_user_id ON public.savings_transactions USING btree (user_id)",
        "pk_savings_transactions": "CREATE UNIQUE INDEX pk_savings_transactions ON public.savings_transactions USING btree (id)",
        "uq_savings_transactions_auto_save_installment_id": "CREATE UNIQUE INDEX uq_savings_transactions_auto_save_installment_id ON public.savings_transactions USING btree (installment_id) WHERE (type = 'auto_save'::text)",
        "uq_savings_transactions_auto_save_source_event": "CREATE UNIQUE INDEX uq_savings_transactions_auto_save_source_event ON public.savings_transactions USING btree (source_vendor, source_event_id) WHERE (type = 'auto_save'::text)",
    },
    "user_balances": {
        "pk_user_balances": "CREATE UNIQUE INDEX pk_user_balances ON public.user_balances USING btree (user_id)",
    },
    "user_settings": {
        "pk_user_settings": "CREATE UNIQUE INDEX pk_user_settings ON public.user_settings USING btree (user_id)",
    },
    "webhook_events": {
        "ix_webhook_events_user_id": "CREATE INDEX ix_webhook_events_user_id ON public.webhook_events USING btree (user_id)",
        "pk_webhook_events": "CREATE UNIQUE INDEX pk_webhook_events ON public.webhook_events USING btree (vendor, event_id)",
    },
}

EXPECTED_DEFAULTS: dict[str, dict[str, str]] = {
    "audit_log": {
        "created_at": "now()",
        "detail": "'{}'::jsonb",
    },
    "installments": {
        "created_at": "now()",
        "fee_total": "0",
        "id": "gen_random_uuid()",
        "late_fees_accrued": "0",
        "overdue_days": "0",
        "paid_amount": "0",
        "status": "'active'::text",
    },
    "notifications": {
        "created_at": "now()",
        "delivery_status": "'pending'::text",
        "id": "gen_random_uuid()",
        "push_attempts": "0",
        "user_response": "'none'::text",
    },
    "savings_transactions": {
        "created_at": "now()",
        "id": "gen_random_uuid()",
    },
    "user_balances": {
        "savings_balance": "0",
        "version": "0",
    },
    "user_settings": {
        "auto_save_enabled": "false",
        "leftover_saving_enabled": "false",
    },
    "webhook_events": {
        "received_at": "now()",
    },
}


EXPECTED_APP_GRANTS: dict[str, str] = {
    "audit_log": "INSERT, SELECT",
    "installments": "INSERT, SELECT, UPDATE",
    "notifications": "INSERT, SELECT, UPDATE",
    "savings_transactions": "INSERT, SELECT",
    "user_balances": "INSERT, SELECT, UPDATE",
    "user_settings": "INSERT, SELECT, UPDATE",
    "webhook_events": "INSERT, SELECT, UPDATE",
}


def _rows(conn: Connection, sql: str) -> dict[str, dict[str, str]]:
    by_table: dict[str, dict[str, str]] = {}
    for table, name, value in conn.execute(text(sql)):
        by_table.setdefault(table, {})[name] = value
    return by_table


def test_M3_constraint_definitions_match(migration_engine: Engine) -> None:
    # PK, UNIQUE, FK and CHECK constraints, with their full expressions.
    with migration_engine.connect() as conn:
        actual = _rows(
            conn,
            "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
            "FROM pg_constraint "
            "WHERE connamespace = 'public'::regnamespace AND contype IN ('c', 'f', 'p', 'u') "
            "AND conrelid::regclass::text <> 'alembic_version'",
        )
    assert actual == EXPECTED_CONSTRAINTS


def test_M3_index_definitions_match(migration_engine: Engine) -> None:
    # Includes the WHERE clause of each partial UNIQUE index (INV-3, ID-05).
    with migration_engine.connect() as conn:
        actual = _rows(
            conn,
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'",
        )
    assert actual == EXPECTED_INDEXES


def test_M3_server_defaults_match(migration_engine: Engine) -> None:
    with migration_engine.connect() as conn:
        actual = _rows(
            conn,
            "SELECT table_name, column_name, column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_default IS NOT NULL",
        )
    assert actual == EXPECTED_DEFAULTS


def test_S2_app_role_grants_match(migration_engine: Engine) -> None:
    # Every relation in public (tables and sequences) with what lumen_app holds on it.
    with migration_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname, string_agg(a.privilege_type, ', ' "
                "ORDER BY a.privilege_type) "
                "FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a "
                "WHERE c.relnamespace = 'public'::regnamespace "
                "AND a.grantee = 'lumen_app'::regrole GROUP BY c.relname"
            )
        )
        actual = dict(rows.all())  # not dict(rows): a Result has .keys()
    assert actual == EXPECTED_APP_GRANTS
