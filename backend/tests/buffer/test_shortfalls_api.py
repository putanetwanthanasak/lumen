"""BS-04: GET /buffer/shortfalls over the Ledger and the buffer, "today" fixed at
2026-11-10 (the plan_api fixture). The arithmetic itself is BS-01 to BS-03."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models import UserSettings
from tests.db.factories import manual_installment, profile, user_balance
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
        "covered": False,
        "still_short": "300.00",
        "months": [
            {
                "month": "2026-11",
                "total": "6500.00",
                "budget": "5000.00",
                "shortfall": "1500.00",
                "covered_by_buffer": "1500.00",
                "still_short": "0.00",
            },
            {
                "month": "2026-12",
                "total": "6500.00",
                "budget": "5000.00",
                "shortfall": "1500.00",
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
