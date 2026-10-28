"""NT-08 to NT-10: GET /notifications, the user's alerts newest first with a count
(Session 15A). No read or unread state."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.models import Notification
from tests.db.factories import installment, notification
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def alert(api: Api, minutes: int, user: str = USER, **fields: Any) -> uuid.UUID:
    row = notification(user_id=user, created_at=T0 + timedelta(minutes=minutes), **fields)
    api.session.add(row)
    api.session.flush()
    return row.id


def payday(api: Api, minutes: int, user: str = USER) -> uuid.UUID:
    return alert(api, minutes, user, kind="leftover_saved", title="t", body="b")


def get_inbox(api: Api, user: str | None = USER) -> Any:
    return api.call("GET", "/notifications", user=user)


def test_NT_08_newest_first_with_the_stored_text(api: Api) -> None:
    owned = installment(user_id=USER, contract_id="c-1")
    api.session.add(owned)
    api.session.flush()
    first = alert(
        api,
        0,
        kind="new_debt",
        installment_id=owned.id,
        title="มีรายการผ่อนใหม่",
        body="ยอดผ่อนต่อเดือนรวม 500 บาท",
    )
    second = alert(api, 30, kind="payday_shortfall", title="เดือนนี้ค่างวดเกินงบ", body="เกินงบ 500 บาท")

    response = get_inbox(api)

    assert response.status_code == 200
    assert response.json() == {
        "notifications": [
            {
                "id": str(second),
                "kind": "payday_shortfall",
                "title": "เดือนนี้ค่างวดเกินงบ",
                "body": "เกินงบ 500 บาท",
                "installment_id": None,
                "created_at": "2026-11-01T09:30:00Z",
            },
            {
                "id": str(first),
                "kind": "new_debt",
                "title": "มีรายการผ่อนใหม่",
                "body": "ยอดผ่อนต่อเดือนรวม 500 บาท",
                "installment_id": str(owned.id),
                "created_at": "2026-11-01T09:00:00Z",
            },
        ],
        "count": 2,
    }


@pytest.mark.parametrize(
    "kind",
    ["new_debt", "cash_withdrawal", "cash_loan", "consolidation_loan"],
)
def test_NT_08_every_installment_alert_kind_is_listed(api: Api, kind: str) -> None:
    owned = installment(user_id=USER, contract_id="c-1")
    api.session.add(owned)
    api.session.flush()
    alert(api, 0, kind=kind, installment_id=owned.id)
    [listed] = get_inbox(api).json()["notifications"]
    assert listed["kind"] == kind


@pytest.mark.parametrize("kind", ["payday_shortfall", "leftover_saved", "over_cap"])
def test_NT_08_every_other_alert_kind_is_listed(api: Api, kind: str) -> None:
    alert(api, 0, kind=kind)
    [listed] = get_inbox(api).json()["notifications"]
    assert (listed["kind"], listed["installment_id"]) == (kind, None)


def test_NT_08_alerts_at_the_same_instant_keep_one_order(api: Api) -> None:
    ids = [payday(api, 0) for _ in range(3)]
    listed = [n["id"] for n in get_inbox(api).json()["notifications"]]
    assert listed == sorted((str(i) for i in ids), reverse=True)


def test_NT_08_delivery_status_does_not_hide_an_alert(api: Api) -> None:
    for status in ["pending", "pushed", "inbox_only"]:
        alert(api, 0, kind="over_cap", delivery_status=status)
    assert get_inbox(api).json()["count"] == 3


def test_NT_09_lists_the_100_newest_and_counts_them_all(api: Api) -> None:
    ids = [payday(api, minutes) for minutes in range(105)]
    payday(api, 500, user="user_b")  # another user's, newer than all

    body = get_inbox(api).json()

    assert body["count"] == 105
    assert [n["id"] for n in body["notifications"]] == [str(i) for i in reversed(ids[5:])]


def test_NT_09_only_the_users_own_alerts(api: Api) -> None:
    payday(api, 0, user="user_b")
    mine = payday(api, 1)
    body = get_inbox(api).json()
    assert ([n["id"] for n in body["notifications"]], body["count"]) == ([str(mine)], 1)
    assert get_inbox(api, user="user_b").json()["count"] == 1


def test_NT_10_an_empty_inbox(api: Api) -> None:
    assert get_inbox(api).json() == {"notifications": [], "count": 0}


def test_NT_10_no_user_is_401(api: Api) -> None:
    assert get_inbox(api, user=None).status_code == 401


def test_NT_10_reading_the_inbox_writes_nothing(api: Api) -> None:
    payday(api, 0)
    before = api.session.execute(select(Notification.__table__)).all()
    get_inbox(api)
    api.session.expire_all()
    assert api.session.execute(select(Notification.__table__)).all() == before
