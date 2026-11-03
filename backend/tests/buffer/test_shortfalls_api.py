"""BS-04 to BS-06: GET /buffer/shortfalls over the Ledger and the buffer, "today"
fixed at 2026-11-10 (the plan_api fixture). The arithmetic itself is BS-01 to BS-03
and BS-05 to BS-07 in tests/assistant/test_shortfalls.py; here, what was moved for a
month (Session 17) is read from the database and shown per month."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import update

from app.affordability.months import Month
from app.assistant import service as assistant_service
from app.buffer.service import prepared_by_month
from app.clock import today
from app.main import app
from app.models import UserBalance, UserSettings
from tests.db.factories import manual_installment, profile, savings_tx, user_balance
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db


def configure(api: Api, budget: str = "5000.00", buffer: str = "2700.00") -> None:
    api.session.add(
        UserSettings(
            user_id=USER,
            auto_save_enabled=False,
            **profile() | {"monthly_installment_budget": Decimal(budget)},
        )
    )
    api.session.add(user_balance(user_id=USER, savings_balance=Decimal(buffer)))
    if Decimal(buffer) > 0:
        # Where the buffer came from, so a move through the API reconciles.
        api.session.add(
            savings_tx(
                user_id=USER,
                type="leftover_save",
                amount=Decimal(buffer),
                payday_month=date(2026, 10, 1),
                source_vendor=None,
                source_event_id=None,
            )
        )
    api.session.flush()


def moved(api: Api, amount: str, for_month: date | None, user: str = USER) -> None:
    """A move already in the Ledger, as POST /buffer/move-to-main writes it."""
    api.session.add(
        savings_tx(
            user_id=user,
            type="withdrawal",
            amount=Decimal(amount),
            client_request_id=str(uuid.uuid4()),
            for_month=for_month,
            source_vendor=None,
            source_event_id=None,
        )
    )
    api.session.flush()


def manual(api: Api, monthly: str, months: int, first: date, user: str = USER) -> None:
    api.session.add(
        manual_installment(
            user_id=user,
            client_request_id=str(uuid.uuid4()),
            principal=Decimal(monthly) * months,
            monthly_amount=Decimal(monthly),
            months=months,
            first_due_date=first,
        )
    )
    api.session.flush()


def test_BS_04_shortfalls_over_http(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    manual(api, "2000.00", 6, date(2026, 8, 1))  # Aug..Jan
    manual(api, "4500.00", 2, date(2026, 11, 1))  # Nov..Dec
    manual(api, "9999.00", 1, date(2026, 10, 1))  # October: past, never a shortfall

    response = api.call("GET", "/buffer/shortfalls")

    assert response.status_code == 200
    assert response.json() == {
        "balance": "2700.00",
        "shortfall": "3000.00",
        "remaining_gap": "3000.00",
        "covered": False,
        "still_short": "300.00",
        "months": [
            {
                "month": "2026-11",
                "total": "6500.00",
                "budget": "5000.00",
                "shortfall": "1500.00",
                "prepared": "0.00",
                "remaining_gap": "1500.00",
                "state": "not_prepared",
                "covered_by_buffer": "1500.00",
                "still_short": "0.00",
            },
            {
                "month": "2026-12",
                "total": "6500.00",
                "budget": "5000.00",
                "shortfall": "1500.00",
                "prepared": "0.00",
                "remaining_gap": "1500.00",
                "state": "not_prepared",
                "covered_by_buffer": "1200.00",
                "still_short": "300.00",
            },
        ],
        "months_truncated": False,
    }


def test_BS_04_totals_equal_the_assistant_plans_buffer(plan_api: Api) -> None:
    api = plan_api
    configure(api, buffer="999.99")
    manual(api, "5300.00", 4, date(2026, 11, 1))
    shortfalls = api.call("GET", "/buffer/shortfalls").json()
    plan = api.call("GET", "/assistant/plan").json()["buffer_plan"]
    assert {k: shortfalls[k] for k in plan} == plan
    assert (plan["balance"], plan["shortfall"], plan["still_short"]) == (
        "999.99",
        "1200.00",
        "200.01",
    )


def test_BS_04_within_budget_is_an_empty_list(plan_api: Api) -> None:
    api = plan_api
    configure(api, buffer="0.00")
    manual(api, "5000.00", 3, date(2026, 11, 1))  # exactly the budget
    manual(api, "9000.00", 2, date(2026, 11, 1), user="user_b")  # another user's
    assert api.call("GET", "/buffer/shortfalls").json() == {
        "balance": "0.00",
        "shortfall": "0.00",
        "remaining_gap": "0.00",
        "covered": True,
        "still_short": "0.00",
        "months": [],
        "months_truncated": False,
    }


def test_BS_04_no_settings_is_409_and_no_user_is_401(plan_api: Api) -> None:
    response = plan_api.call("GET", "/buffer/shortfalls")
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "SETTINGS_REQUIRED")
    assert plan_api.call("GET", "/buffer/shortfalls", user=None).status_code == 401


def test_BS_04_rows_stop_at_600(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    manual(api, "5000.01", 600, date(2026, 11, 1))
    manual(api, "5000.01", 3, date(2076, 11, 1))
    body = api.call("GET", "/buffer/shortfalls").json()
    assert (len(body["months"]), body["months_truncated"]) == (600, True)
    assert body["shortfall"] == "6.03"  # 603 months of 0.01, shown or not


# --- BS-05, BS-06: moves made for a month, from the database ------------------------------


def rows(api: Api) -> list[tuple[str, str, str, str, str]]:
    body = api.call("GET", "/buffer/shortfalls").json()
    return [
        (m["month"], m["shortfall"], m["prepared"], m["remaining_gap"], m["state"])
        for m in body["months"]
    ]


def test_BS_05_moves_for_a_month_are_summed_and_shown_per_month(plan_api: Api) -> None:
    api = plan_api
    configure(api, buffer="0.00")
    manual(api, "6500.00", 3, date(2026, 11, 1))  # Nov..Jan, 1,500 over each
    moved(api, "1000.00", date(2026, 11, 1))
    moved(api, "500.00", date(2026, 11, 1))  # two moves for Nov: 1,500 in all
    moved(api, "400.00", date(2026, 12, 1))
    moved(api, "700.00", None)  # a free move prepares no month
    moved(api, "1500.00", date(2027, 1, 1), user="user_b")  # another user's

    assert rows(api) == [
        ("2026-11", "1500.00", "1500.00", "0.00", "prepared"),
        ("2026-12", "1500.00", "400.00", "1100.00", "partly_prepared"),
        ("2027-01", "1500.00", "0.00", "1500.00", "not_prepared"),
    ]
    body = api.call("GET", "/buffer/shortfalls").json()
    assert (body["shortfall"], body["remaining_gap"], body["still_short"]) == (
        "4500.00",
        "2600.00",
        "2600.00",
    )


def test_BS_06_a_move_for_last_month_is_over_once_the_month_turns(plan_api: Api) -> None:
    api = plan_api
    configure(api, buffer="0.00")
    manual(api, "6500.00", 3, date(2026, 10, 1))  # Oct..Dec
    moved(api, "1500.00", date(2026, 10, 1))  # prepared October
    moved(api, "1500.00", date(2026, 11, 1))  # prepared November

    app.dependency_overrides[today] = lambda: date(2026, 10, 31)
    assert [r[4] for r in rows(api)] == ["prepared", "prepared", "not_prepared"]

    app.dependency_overrides[today] = lambda: date(2026, 11, 1)  # the month turns
    assert rows(api) == [
        ("2026-11", "1500.00", "1500.00", "0.00", "prepared"),
        ("2026-12", "1500.00", "0.00", "1500.00", "not_prepared"),
    ]
    body = api.call("GET", "/buffer/shortfalls").json()
    assert body["remaining_gap"] == "1500.00"  # October's 1,500 closes nothing any more


def test_BS_07_after_moves_the_totals_still_equal_the_assistant_plans_buffer(
    plan_api: Api,
) -> None:
    api = plan_api
    configure(api, buffer="999.99")
    manual(api, "5300.00", 4, date(2026, 11, 1))
    moved(api, "300.00", date(2026, 11, 1))
    moved(api, "100.00", date(2026, 12, 1))
    shortfalls = api.call("GET", "/buffer/shortfalls").json()
    plan = api.call("GET", "/assistant/plan").json()["buffer_plan"]
    assert {k: shortfalls[k] for k in plan} == plan
    assert (plan["shortfall"], plan["remaining_gap"], plan["covered"]) == (
        "1200.00",
        "800.00",
        True,
    )


def test_BS_05_a_move_through_the_api_prepares_its_month_once(plan_api: Api) -> None:
    api = plan_api
    configure(api, buffer="2700.00")
    manual(api, "6500.00", 2, date(2026, 11, 1))
    body = {"client_request_id": "prep-nov", "amount": "1500.00", "for_month": "2026-11"}

    first = api.call("POST", "/buffer/move-to-main", body)
    again = api.call("POST", "/buffer/move-to-main", body)  # a double tap

    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["for_month"] == "2026-11"
    assert again.json()["status"] == "duplicate"
    shortfalls = api.call("GET", "/buffer/shortfalls").json()
    assert (shortfalls["balance"], shortfalls["shortfall"], shortfalls["remaining_gap"]) == (
        "1200.00",
        "3000.00",
        "1500.00",
    )
    assert rows(api) == [
        ("2026-11", "1500.00", "1500.00", "0.00", "prepared"),
        ("2026-12", "1500.00", "0.00", "1500.00", "not_prepared"),
    ]


def test_BS_05_new_installment_after_prepared_reopens_gap(plan_api: Api) -> None:
    """Session 20: a month fully prepared, then a new installment due that month, is only
    partly prepared: its shortfall grows, the move stays, and the gap is the difference.
    The months screen draws this gap in amber and offers the move again (UI-56)."""
    api = plan_api
    configure(api, buffer="2700.00")
    manual(api, "6500.00", 2, date(2026, 11, 1))  # Nov and Dec, 1,500 over each
    move = {"client_request_id": "prep-nov", "amount": "1500.00", "for_month": "2026-11"}
    assert api.call("POST", "/buffer/move-to-main", move).status_code == 201
    assert rows(api)[0] == ("2026-11", "1500.00", "1500.00", "0.00", "prepared")

    recorded = api.call(
        "POST",
        "/installments",
        {
            "client_request_id": "after-prep",
            "kind": "purchase",
            "item_price": "400.00",
            "months": 1,
            "monthly_amount": "400.00",
            "first_due_month": "2026-11",
            "item_name": "สายชาร์จ",
        },
    )
    assert recorded.status_code == 201

    # Nov: 6,900 against 5,000 is 1,900 over; 1,500 moved leaves 400. Dec is untouched.
    assert rows(api) == [
        ("2026-11", "1900.00", "1500.00", "400.00", "partly_prepared"),
        ("2026-12", "1500.00", "0.00", "1500.00", "not_prepared"),
    ]
    body = api.call("GET", "/buffer/shortfalls").json()
    assert (body["shortfall"], body["remaining_gap"]) == ("3400.00", "1900.00")


def test_BS_06_prepared_by_month_reads_this_month_on_only(plan_api: Api) -> None:
    # Its own month bound, not only the plan's: the plan also ignores past months, so
    # without this test a query that reads every month would go unseen (B139).
    api = plan_api
    moved(api, "100.00", date(2026, 10, 1))  # last month
    moved(api, "200.00", date(2026, 11, 1))
    moved(api, "300.00", date(2026, 11, 1))
    moved(api, "400.00", date(2027, 1, 1))
    moved(api, "500.00", None)  # a free move
    moved(api, "600.00", date(2026, 11, 1), user="user_b")
    assert prepared_by_month(api.session, USER, since=Month.of(date(2026, 11, 10))) == {
        Month.of(date(2026, 11, 1)): Decimal("500.00"),
        Month.of(date(2027, 1, 1)): Decimal("400.00"),
    }


@pytest.mark.parametrize("endpoint", ["/buffer/shortfalls", "/assistant/plan"])
def test_BS_07_a_move_between_the_reads_is_never_counted_twice(
    plan_api: Api, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    # Review R2-F1: prepared and balance are two statements. A move that lands between
    # them must understate the coverage for that response, never overstate it.
    api = plan_api
    configure(api, buffer="5700.00")
    manual(api, "6500.00", 2, date(2026, 11, 1))  # 1,500.00 over in Nov and Dec
    real = assistant_service.prepared_by_month

    def then_a_move_lands(*args: Any, **kwargs: Any) -> Any:
        found = real(*args, **kwargs)
        moved(api, "1500.00", date(2026, 11, 1))
        api.session.execute(
            update(UserBalance)
            .where(UserBalance.user_id == USER)
            .values(savings_balance=UserBalance.savings_balance - Decimal("1500.00"))
        )
        return found

    monkeypatch.setattr(assistant_service, "prepared_by_month", then_a_move_lands)
    body = api.call("GET", endpoint).json()
    buffer = body if endpoint == "/buffer/shortfalls" else body["buffer_plan"]
    # The lower balance, and Nov not yet prepared: 4,200.00 against 3,000.00 open.
    assert (buffer["balance"], buffer["remaining_gap"]) == ("4200.00", "3000.00")
