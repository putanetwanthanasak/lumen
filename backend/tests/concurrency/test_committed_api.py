"""Writes through the app API must survive commit (review F2, Session 12).

The ST-xx and MI-xx tests share one rolled-back session with the app, so they read
uncommitted rows back and cannot see a missing or misplaced commit. These run on
the committed `race` harness and read from a fresh session afterwards.
"""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, delete, select

from app.models import UserSettings
from tests.concurrency.conftest import Race

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
