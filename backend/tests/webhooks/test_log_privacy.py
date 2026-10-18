"""S12: a DB error must not carry the user's ref or alert text into the server log.

Two sources put them in an error's text: SQLAlchemy prints bound parameters
(make_engine sets hide_parameters), and Postgres's DETAIL quotes the failing row
("Failing row contains (...)"), which hide_parameters does not touch. So the places
that log a DB error log describe_db_error(exc) instead: the app's 500 handler and
the push step.
"""

import logging
from typing import Any

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import describe_db_error
from app.models import Notification
from app.notifications import service as notifications
from tests.webhooks.conftest import Webhook
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db

USER_REF = "user_s12_private_ref"
BODY = "S12 private alert body"


def _bad_insert(session: Session) -> IntegrityError:
    with pytest.raises(IntegrityError) as exc:
        session.execute(
            insert(Notification).values(user_id=USER_REF, kind="not_a_kind", title="t", body=BODY)
        )
    return exc.value


def test_S12_engine_hides_bound_parameters(db_session: Session) -> None:
    assert "SQL parameters hidden" in str(_bad_insert(db_session))


def test_S12_describe_db_error_keeps_state_and_constraint_only(db_session: Session) -> None:
    exc = _bad_insert(db_session)
    assert USER_REF in str(exc)  # why describe_db_error exists: Postgres quotes the row
    described = describe_db_error(exc)
    assert described == ("IntegrityError sqlstate=23514 constraint=ck_notifications_kind_valid")
    assert describe_db_error(ValueError("user_a")) == "ValueError"


def _bad_alert(**_: Any) -> tuple[str, str, str]:
    return "not_a_kind", "t", BODY


def test_S12_webhook_db_error_is_a_bare_500_and_logs_no_user_data(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(notifications, "new_debt_alert", _bad_alert)
    data = payload()
    with caplog.at_level(logging.INFO):
        response = webhook.post(data)
    assert response.status_code == 500
    assert response.json() == {"detail": "internal error"}
    assert "ck_notifications_kind_valid" in caplog.text
    assert data["user_ref"] not in caplog.text
    assert BODY not in caplog.text


def test_S12_push_step_db_error_logs_no_user_data(
    db_session: Session, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = Notification(user_id=USER_REF, kind="over_cap", title="t", body=BODY)
    db_session.add(row)
    db_session.flush()

    class BrokenStatus:
        PUSHED = "not_a_status"
        INBOX_ONLY = "not_a_status"

    monkeypatch.setattr(notifications, "DeliveryStatus", BrokenStatus)
    with caplog.at_level(logging.INFO):
        notifications.deliver(db_session, row.id, push=_AlwaysPush())
    assert "ck_notifications_delivery_status_valid" in caplog.text
    assert USER_REF not in caplog.text
    assert BODY not in caplog.text


class _AlwaysPush:
    def send(self, user_id: str, title: str, body: str) -> bool:
        return True
