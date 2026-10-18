"""Step 9 over HTTP: the alert is pushed after commit, and a failing push never fails
the webhook and never loses the alert (05 NT-02, NT-03, NT-04, RS-03)."""

import pytest
from sqlalchemy import select

from app.models import Notification
from app.notifications import service as notifications
from tests.webhooks.conftest import Webhook
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db

PROCESSED = {"status": "processed"}


def stored(webhook: Webhook) -> list[Notification]:
    webhook.session.expire_all()
    return list(webhook.session.execute(select(Notification)).scalars())


def test_NT_02_push_succeeds_status_pushed(webhook: Webhook) -> None:
    assert webhook.post(payload()).json() == PROCESSED

    [alert] = stored(webhook)
    assert (alert.delivery_status, alert.push_attempts) == ("pushed", 1)
    [push] = webhook.push.attempts
    assert (push.user_id, push.title, push.body) == ("user_a", alert.title, alert.body)


def test_NT_03_push_fails_three_times_inbox_only(webhook: Webhook) -> None:
    webhook.push.fail = True

    assert webhook.post(payload()).json() == PROCESSED

    [alert] = stored(webhook)
    assert (alert.delivery_status, alert.push_attempts) == ("inbox_only", 3)
    assert len(webhook.push.attempts) == 3
    assert webhook.push.delivered == []


def test_NT_03_push_succeeds_on_a_retry(webhook: Webhook, monkeypatch: pytest.MonkeyPatch) -> None:
    results = iter([False, True])
    monkeypatch.setattr(webhook.push, "send", lambda *_: next(results))

    webhook.post(payload())

    [alert] = stored(webhook)
    assert (alert.delivery_status, alert.push_attempts) == ("pushed", 2)


def test_RS_03_push_provider_raising_does_not_fail_the_webhook(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*_: object) -> bool:
        raise ConnectionError("push service down")

    monkeypatch.setattr(webhook.push, "send", down)

    response = webhook.post(payload())

    assert (response.status_code, response.json()) == (200, PROCESSED)
    [alert] = stored(webhook)
    assert (alert.delivery_status, alert.push_attempts) == ("inbox_only", 3)


def test_RS_03_delivery_failing_entirely_leaves_the_alert_pending(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> None:
        raise RuntimeError("rules unavailable")

    monkeypatch.setattr(notifications, "load_rules", broken)

    response = webhook.post(payload())

    assert (response.status_code, response.json()) == (200, PROCESSED)
    [alert] = stored(webhook)
    assert (alert.delivery_status, alert.push_attempts) == ("pending", 0)
    assert webhook.push.attempts == []


def test_NT_04_resend_does_not_push_again(webhook: Webhook) -> None:
    data = payload()
    webhook.post(data)

    assert webhook.post(data).json() == {"status": "duplicate"}
    assert webhook.post(payload(event_id="evt_new_id")).json() == {"status": "duplicate"}  # ID-05

    assert len(stored(webhook)) == 1
    assert len(webhook.push.attempts) == 1


@pytest.mark.parametrize(
    "event_type", ["installment_payment_collected", "installment_overdue", "installment_cancelled"]
)
def test_only_created_events_alert(webhook: Webhook, event_type: str) -> None:
    webhook.post(payload())

    webhook.post(payload(event_type, event_id="evt_other"))

    assert len(stored(webhook)) == 1
    assert len(webhook.push.attempts) == 1
