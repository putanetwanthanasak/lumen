"""Writes through the app API must survive commit (review F2, Session 12; NM-02,
Session 13).

The ST-xx and MI-xx tests share one rolled-back session with the app, so they read
uncommitted rows back and cannot see a missing or misplaced commit. These run on
the committed `race` harness and read from a fresh session afterwards.
"""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, delete, func, select

from app.models import AuditLog, Installment, UserSettings
from tests.concurrency.conftest import Race
from tests.concurrency.test_manual_entry_concurrency import entry

pytestmark = [pytest.mark.db, pytest.mark.concurrency]


def settings_body(**overrides: Any) -> dict[str, Any]:
    return {
        "income": "30000.00",
        "payday": 25,
        "monthly_installment_budget": "9000.00",
        "saving_rule": {"mode": "fixed", "amount": "40.00"},
        "auto_save_enabled": True,
        "auto_save_consent": True,
        "leftover_saving_enabled": True,
    } | overrides


def stored_settings(race: Race) -> UserSettings:
    with race.session() as s:
        row = s.execute(select(UserSettings).where(UserSettings.user_id == race.user)).scalar_one()
        s.expunge(row)
        return row


def test_ST_01_created_settings_persist_across_sessions(
    race: Race, migration_engine: Engine
) -> None:
    # The race fixture gave this user settings; only the owner may delete them (S2).
    with migration_engine.begin() as conn:
        conn.execute(delete(UserSettings).where(UserSettings.user_id == race.user))
    headers = {"X-Demo-User": race.user}

    response = race.client.post("/settings", json=settings_body(), headers=headers)

    assert response.status_code == 201
    row = stored_settings(race)
    assert (row.saving_mode, row.saving_fixed_amount, row.leftover_saving_enabled) == (
        "fixed",
        Decimal("40.00"),
        True,
    )
    assert row.consent_at is not None


def test_ST_07_replaced_settings_persist_across_sessions(race: Race) -> None:
    # The race fixture already gave this user settings (10%).
    body = settings_body(saving_rule={"mode": "percent", "percent": 7})
    response = race.client.put("/settings", json=body, headers={"X-Demo-User": race.user})

    assert response.status_code == 200
    row = stored_settings(race)
    assert (row.saving_mode, row.saving_percent, row.saving_fixed_amount) == ("percent", 7, None)


def test_MI_06_conflict_audit_survives_commit(race: Race) -> None:
    # The 409 must still commit its audit row (as L55), so the router commits before
    # it raises.
    first = entry(race.id("req_conflict"))
    assert race.post_manual(first).status_code == 201
    assert race.post_manual(first | {"months": 5}).status_code == 409

    with race.session() as s:
        actions = s.scalars(
            select(AuditLog.action).where(AuditLog.user_id == race.user).order_by(AuditLog.id)
        ).all()
        assert actions == ["installment_recorded", "client_request_id_reused"]
        assert s.scalar(select(func.count()).where(Installment.user_id == race.user)) == 1


def test_NM_02_refused_not_me_audit_survives_commit(race: Race) -> None:
    # L68: the 409 must still commit its audit row, so the router commits first.
    created = race.post_manual(entry(race.id("req_not_me")))
    assert created.status_code == 201
    installment_id = created.json()["installment_id"]

    response = race.client.post(
        f"/debts/{installment_id}/not-me", headers={"X-Demo-User": race.user}
    )

    assert response.status_code == 409
    assert race.platform.signals == []
    with race.session() as s:
        actions = s.scalars(
            select(AuditLog.action).where(AuditLog.user_id == race.user).order_by(AuditLog.id)
        ).all()
        assert actions == ["installment_recorded", "not_me_rejected_manual_entry"]
        assert s.scalar(select(Installment.status).where(Installment.user_id == race.user)) == (
            "active"
        )


def test_BF_08_move_conflict_audit_survives_commit(race: Race) -> None:
    created = race.post_manual(entry(race.id("req_seed"), "5000.00"))  # saves 500.00
    assert created.status_code == 201
    headers = {"X-Demo-User": race.user}
    body = {"client_request_id": race.id("move"), "amount": "100.00"}

    assert race.client.post("/buffer/move-to-main", json=body, headers=headers).status_code == 201
    conflict = race.client.post(
        "/buffer/move-to-main", json=body | {"amount": "120.00"}, headers=headers
    )

    assert conflict.status_code == 409
    with race.session() as s:
        actions = s.scalars(
            select(AuditLog.action).where(AuditLog.user_id == race.user).order_by(AuditLog.id)
        ).all()
        assert actions == [
            "installment_recorded",
            "buffer_moved_to_main",
            "client_request_id_reused",
        ]
