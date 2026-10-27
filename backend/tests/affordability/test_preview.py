"""AF-03, AF-07 to AF-11: the L65 verdict over HTTP, from POST /installments/preview
and in POST /installments `warnings`. The profile from opt_in is income 30,000.00
and budget 9,000.00, so RED starts above 10,000.00 a month."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select

from app.db import Base
from app.models import UserSettings
from tests.db.factories import installment, manual_installment
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

SETTINGS_REQUIRED = {
    "detail": {
        "code": "SETTINGS_REQUIRED",
        "message": "set income and budget with POST /settings first",
    }
}


def entry(**overrides: Any) -> dict[str, Any]:
    return {
        "client_request_id": "req-1",
        "kind": "purchase",
        "item_price": "6000.00",
        "months": 3,
        "monthly_amount": "2000.00",
        "first_due_month": "2026-11",
        "item_name": "โน้ตบุ๊ก",
    } | overrides


def preview(api: Api, data: Any, user: str | None = USER) -> Any:
    return api.call("POST", "/installments/preview", data, user=user)


def record(api: Api, data: Any, user: str | None = USER) -> Any:
    return api.call("POST", "/installments", data, user=user)


def existing(api: Api, **overrides: Any) -> None:
    """A webhook installment of this user, valid by default: 500.00 a month for 4
    months from November 2026."""
    fields = {"user_id": USER, "contract_id": str(uuid.uuid4())} | overrides
    api.session.add(installment(**fields))
    api.session.flush()


def row_counts(api: Api) -> dict[str, int]:
    return {
        table.name: api.session.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
    }


def months_of(body: dict[str, Any]) -> list[tuple[str, str]]:
    return [(m["month"], m["total"]) for m in body["months"]]


# --- AF-07: the response ----------------------------------------------------------------


def test_AF_07_preview_returns_the_month_by_month_verdict(api: Api) -> None:
    opt_in(api.session)
    existing(api, monthly_amount=Decimal("7500.00"), principal=Decimal("15000.00"), months=2)

    response = preview(api, entry())

    assert response.status_code == 200
    assert response.json() == {
        "verdict": "YELLOW",
        "months": [
            {"month": "2026-11", "total": "9500.00", "over_budget": True, "over_one_third": False},
            {"month": "2026-12", "total": "9500.00", "over_budget": True, "over_one_third": False},
            {"month": "2027-01", "total": "2000.00", "over_budget": False, "over_one_third": False},
        ],
        "over_budget_months": ["2026-11", "2026-12"],
        "monthly_total": "7500.00",  # owed now; the previewed entry is not recorded
    }


def test_AF_07_red_month_is_flagged_over_one_third(api: Api) -> None:
    opt_in(api.session)
    existing(api, monthly_amount=Decimal("8000.01"), principal=Decimal("8000.01"), months=1)
    body = preview(api, entry()).json()
    assert body["verdict"] == "RED"
    assert body["months"][0] == {
        "month": "2026-11",
        "total": "10000.01",
        "over_budget": True,
        "over_one_third": True,
    }


# --- AF-03: which installments count ---------------------------------------------------

DISPUTED = {"status": "disputed", "disputed_at": datetime(2026, 10, 1, tzinfo=UTC)}


@pytest.mark.parametrize(
    ("fields", "counted"),
    [
        ({}, True),
        (DISPUTED | {"dispute_signal_status": "sent"}, True),  # owed until cancelled
        ({"status": "paid_off", "paid_amount": Decimal("2000.00")}, False),
        ({"status": "cancelled"}, False),
        ({"paid_amount": Decimal("2000.00")}, False),  # nothing left to pay
        ({"paid_amount": Decimal("1500.00")}, True),  # partly prepaid: full monthly amount
        ({"user_id": "user_b"}, False),
    ],
    ids=["active", "disputed", "paid_off", "cancelled", "fully_paid", "partly_paid", "other"],
)
def test_AF_03_which_installments_count(api: Api, fields: dict[str, Any], counted: bool) -> None:
    opt_in(api.session)
    existing(api, **fields)
    body = preview(api, entry(months=1, monthly_amount="100.00", item_price="100.00")).json()
    assert months_of(body) == [("2026-11", "600.00" if counted else "100.00")]


def test_AF_03_manual_entries_count_like_webhook_ones(api: Api) -> None:
    opt_in(api.session)
    api.session.add(manual_installment(user_id=USER, first_due_date=date(2026, 12, 1)))
    api.session.flush()
    body = preview(api, entry()).json()
    assert months_of(body) == [
        ("2026-11", "2000.00"),
        ("2026-12", "2500.00"),
        ("2027-01", "2500.00"),
    ]


def test_AF_03_webhook_due_date_is_placed_in_its_calendar_month(api: Api) -> None:
    opt_in(api.session)
    existing(api, first_due_date=date(2026, 12, 28), months=1, principal=Decimal("500.00"))
    body = preview(api, entry()).json()
    assert months_of(body)[1] == ("2026-12", "2500.00")


# --- AF-08: preview writes nothing -----------------------------------------------------


def test_AF_08_preview_writes_nothing(api: Api) -> None:
    opt_in(api.session)
    existing(api)
    before = row_counts(api)

    for _ in range(2):
        assert preview(api, entry()).status_code == 200

    api.session.expire_all()
    assert row_counts(api) == before
    assert api.bank.get_balance(USER) == Decimal("10000.00")
    assert api.push.attempts == []


# --- AF-09: the verdict on a recorded entry --------------------------------------------


@pytest.mark.parametrize(
    ("monthly", "verdict"),
    [("2000.00", "GREEN"), ("9000.01", "YELLOW"), ("10000.01", "RED")],
)
def test_AF_09_recording_succeeds_for_every_verdict(api: Api, monthly: str, verdict: str) -> None:
    opt_in(api.session)
    data = entry(monthly_amount=monthly, item_price=str(Decimal(monthly) * 3))

    previewed = preview(api, data).json()
    recorded = record(api, data)

    assert recorded.status_code == 201
    warnings = recorded.json()["warnings"]
    assert warnings["verdict"] == previewed["verdict"] == verdict
    # The same months as the preview; the recorded entry is counted once, not twice.
    assert warnings["months"] == previewed["months"]
    assert warnings["over_budget_months"] == previewed["over_budget_months"]
    assert warnings["monthly_total"] == monthly  # now owed
    assert previewed["monthly_total"] == "0.00"


def test_AF_09_repeat_submit_carries_the_verdict_as_it_is_now(api: Api) -> None:
    opt_in(api.session)
    first = record(api, entry())
    existing(api, monthly_amount=Decimal("7500.00"), principal=Decimal("7500.00"), months=1)
    again = record(api, entry())

    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["warnings"]["verdict"] == "GREEN"
    assert again.json()["warnings"]["verdict"] == "YELLOW"  # 9,500.00 in November
    assert again.json()["warnings"]["months"][0]["total"] == "9500.00"


# --- AF-10: no settings -----------------------------------------------------------------


def legacy_row(api: Api) -> None:
    """A row from before L63: the auto-save switch only, no income or budget."""
    api.session.add(UserSettings(user_id=USER, auto_save_enabled=False))
    api.session.flush()


@pytest.mark.parametrize("setup", [lambda api: None, legacy_row], ids=["none", "before_L63"])
def test_AF_10_preview_without_a_profile_is_409(api: Api, setup: Any) -> None:
    setup(api)
    response = preview(api, entry())
    assert response.status_code == 409
    assert response.json() == SETTINGS_REQUIRED


@pytest.mark.parametrize("setup", [lambda api: None, legacy_row], ids=["none", "before_L63"])
def test_AF_10_record_without_a_profile_is_409_and_writes_nothing(api: Api, setup: Any) -> None:
    setup(api)
    before = row_counts(api)

    response = record(api, entry())

    assert response.status_code == 409
    assert response.json() == SETTINGS_REQUIRED
    api.session.expire_all()
    assert row_counts(api) == before
    assert api.push.attempts == []


# --- AF-11: validation and auth --------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"months": 0},
        {"monthly_amount": "0"},
        {"first_due_month": "2026-13"},
        {"kind": "loan"},
        {"extra": "x"},
    ],
)
def test_AF_11_preview_rejects_what_record_rejects(api: Api, change: dict[str, Any]) -> None:
    opt_in(api.session)
    data = entry() | change
    assert preview(api, data).status_code == 422
    assert record(api, data).status_code == 422


def test_AF_11_preview_rejects_a_json_number_for_money(api: Api) -> None:
    opt_in(api.session)
    raw = b'{"client_request_id": "r", "kind": "purchase", "item_price": 100, "months": 1, '
    raw += b'"monthly_amount": "100.00", "first_due_month": "2026-11"}'
    assert preview(api, raw).status_code == 422


@pytest.mark.parametrize("user", [None, ""])
def test_AF_11_preview_without_a_user_is_401(api: Api, user: str | None) -> None:
    assert preview(api, entry(), user=user).status_code == 401
