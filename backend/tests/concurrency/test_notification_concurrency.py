"""NT-04 under concurrency: one new-debt alert per installment, however many copies of
its created event race (same event_id, or ID-05 resends under new event_ids).

Demo:  cd backend && uv run pytest -m concurrency -v
"""

from collections import Counter

import pytest
from sqlalchemy import select

from app.models import Installment, Notification
from tests.concurrency.conftest import Race
from tests.processing.conftest import created

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

COPIES = 8


def _alerts(race: Race) -> list[Notification]:
    with race.session() as s:
        return list(s.scalars(select(Notification).where(Notification.user_id == race.user)))


@pytest.mark.parametrize("same_event_id", [True, False], ids=["same_event_id", "ID_05_new_ids"])
def test_NT_04_concurrent_copies_of_a_created_event_alert_once(
    race: Race, same_event_id: bool
) -> None:
    contract = race.id("c_1")
    events = [
        created(race.id("evt_1" if same_event_id else f"evt_{n}"), contract, user=race.user)
        for n in range(COPIES)
    ]

    responses = race.fire(events)

    assert Counter(r.json()["status"] for r in responses) == {"processed": 1, "duplicate": 7}
    [alert] = _alerts(race)
    with race.session() as s:
        installment_id = s.scalars(
            select(Installment.id).where(Installment.contract_id == contract)
        ).one()
    assert (alert.installment_id, alert.delivery_status, alert.push_attempts) == (
        installment_id,
        "pushed",
        1,
    )
    [push] = race.push.attempts
    assert (push.user_id, push.body) == (race.user, alert.body)
