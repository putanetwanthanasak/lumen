"""NM-01 to NM-04: "Not me" is refused on an installment the user recorded (L68).

There is no platform to report a manual entry to, so the request gets 409 with a
code, nothing changes, no signal is sent, and the attempt is audited. Webhook rows
keep the L42 behaviour (tests/disputes/test_not_me.py, unchanged). NM-02 after a
real commit is in tests/concurrency/test_committed_api.py.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.models import AuditLog, Installment, Notification
from tests.db.factories import manual_installment
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

REFUSED = {
    "detail": {
        "code": "NOT_ME_UNAVAILABLE_FOR_MANUAL_ENTRY",
        "message": "you recorded this installment yourself; there is no platform to report it to",
    }
}
ENTRY = {
    "client_request_id": "req-1",
    "kind": "purchase",
    "item_price": "1200.00",
    "months": 10,
    "monthly_amount": "120.00",
    "first_due_month": "2026-11",
}


def recorded(api: Api) -> str:
    opt_in(api.session, enabled=False, consent=False)
    response = api.call("POST", "/installments", ENTRY)
    assert response.status_code == 201
    return str(response.json()["installment_id"])


def not_me(api: Api, installment_id: str, user: str = USER) -> Any:
    return api.call("POST", f"/debts/{installment_id}/not-me", user=user)


def state(api: Api, installment_id: str) -> tuple[str, Any, Any, str]:
    api.session.expire_all()
    row = api.session.get(Installment, installment_id)
    assert row is not None
    alert = api.session.execute(
        select(Notification.user_response).where(Notification.installment_id == row.id)
    ).scalar_one()
    return row.status, row.disputed_at, row.dispute_signal_status, alert


def rejected_audits(api: Api) -> list[AuditLog]:
    return list(
        api.session.execute(
            select(AuditLog)
            .where(AuditLog.action == "not_me_rejected_manual_entry")
            .order_by(AuditLog.id)
        ).scalars()
    )


def test_NM_01_not_me_on_a_manual_entry_is_refused_and_changes_nothing(api: Api) -> None:
    installment_id = recorded(api)

    response = not_me(api, installment_id)

    assert response.status_code == 409
    assert response.json() == REFUSED
    assert state(api, installment_id) == ("active", None, None, "none")
    assert api.platform.signals == []  # no signal to any platform
    assert (
        api.session.execute(
            select(AuditLog.id).where(AuditLog.action == "installment_disputed")
        ).all()
        == []
    )


def test_NM_02_the_refused_attempt_is_audited(api: Api) -> None:
    installment_id = recorded(api)
    not_me(api, installment_id)

    [audit] = rejected_audits(api)
    assert (audit.user_id, audit.actor, audit.ref_type, audit.ref_id) == (
        USER,
        "user",
        "installment",
        installment_id,
    )
    assert audit.detail["vendor"] == "manual"


def test_NM_03_every_tap_is_refused_and_audited(api: Api) -> None:
    installment_id = recorded(api)

    responses = [not_me(api, installment_id) for _ in range(3)]

    assert [r.status_code for r in responses] == [409, 409, 409]
    assert len(rejected_audits(api)) == 3
    assert state(api, installment_id) == ("active", None, None, "none")
    assert api.platform.signals == []


def test_NM_03_another_users_manual_entry_is_still_404(api: Api) -> None:
    installment_id = recorded(api)
    response = not_me(api, installment_id, user="user_b")
    assert response.status_code == 404  # nothing to probe: same as an unknown id
    assert rejected_audits(api) == []


def test_NM_04_manual_entry_disputed_before_L68_is_refused_and_kept(api: Api) -> None:
    # Session 12 allowed "Not me" on a manual entry; such a row stays as it is.
    when = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    row = manual_installment(
        user_id=USER, status="disputed", disputed_at=when, dispute_signal_status="sent"
    )
    api.session.add(row)
    api.session.flush()

    response = not_me(api, str(row.id))

    assert response.status_code == 409
    api.session.expire_all()
    assert (row.status, row.disputed_at, row.dispute_signal_status) == ("disputed", when, "sent")
    assert api.platform.signals == []
