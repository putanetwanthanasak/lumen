"""DM-01 to DM-08: GET /debts/months, each month from now with its total, its L65
flags and the installments due in it. "Today" is 2026-11-10 (the plan_api fixture).
DM-08 (Session 17): over_by, each line's last month and its platform_name."""

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.models import UserSettings
from tests.db.factories import approved_consolidation, installment, manual_installment, profile
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

CLOCK = itertools.count()

SETTINGS_REQUIRED = {
    "detail": {
        "code": "SETTINGS_REQUIRED",
        "message": "set income and budget with POST /settings first",
    }
}


def configure(api: Api, *, income: str = "30000.00", budget: str = "9000.00") -> None:
    api.session.add(
        UserSettings(
            user_id=USER,
            auto_save_enabled=False,
            **profile()
            | {"income": Decimal(income), "monthly_installment_budget": Decimal(budget)},
        )
    )
    api.session.flush()


def manual(
    api: Api, monthly: str, months: int, first: date, name: str = "", **kw: Any
) -> uuid.UUID:
    """A recorded entry. created_at goes up per call, as separate requests would get:
    in one test transaction now() is the same for every row."""
    recorded = datetime(2026, 11, 1, tzinfo=UTC) + timedelta(seconds=next(CLOCK))
    row = manual_installment(
        **{
            "user_id": USER,
            "created_at": recorded,
            "client_request_id": str(uuid.uuid4()),
            "item_name": name,
            "principal": Decimal(monthly) * months,
            "monthly_amount": Decimal(monthly),
            "months": months,
            "first_due_date": first,
        }
        | kw
    )
    api.session.add(row)
    api.session.flush()
    return row.id


def get_months(api: Api, query: str = "", user: str | None = USER) -> Any:
    return api.call("GET", f"/debts/months{query}", user=user)


def line(id_: uuid.UUID, name: str, monthly: str, no: int, of: int, last: str) -> dict[str, Any]:
    return {
        "installment_id": str(id_),
        "item_name": name,
        "platform_name": None,
        "monthly_amount": monthly,
        "installment_no": no,
        "installments_total": of,
        "is_last": no == of,
        "last_month": last,
    }


def row(month: str, total: str, lines: list[dict[str, Any]], **flags: bool) -> dict[str, Any]:
    return {
        "month": month,
        "total": total,
        "budget": "9000.00",
        "over_budget": flags.get("over_budget", False),
        "over_by": "0.00",
        "over_one_third": flags.get("over_one_third", False),
        "installments": lines,
    }


# --- DM-01, DM-02: month boundaries and the installment numbers ---------------------------


def test_DM_01_DM_02_rows_run_from_this_month_to_the_last_month_due(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    # Owed, but its last month was October: never in a row from November.
    manual(api, "1000.00", 3, date(2026, 8, 1), "ended")
    phone = manual(api, "500.00", 4, date(2026, 9, 1), "phone")  # Sep..Dec
    bag = manual(api, "300.00", 2, date(2026, 12, 1), "bag")  # Dec..Jan

    response = get_months(api)

    assert response.status_code == 200
    assert response.json() == {
        "months": [
            row("2026-11", "500.00", [line(phone, "phone", "500.00", 3, 4, "2026-12")]),
            row(
                "2026-12",
                "800.00",
                [
                    line(phone, "phone", "500.00", 4, 4, "2026-12"),
                    line(bag, "bag", "300.00", 1, 2, "2027-01"),
                ],
            ),
            row("2027-01", "300.00", [line(bag, "bag", "300.00", 2, 2, "2027-01")]),
        ],
        "months_truncated": False,
    }


def test_DM_01_an_installment_first_due_this_month_starts_at_number_one(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    # A webhook due date late in the month is placed in that month (AF-03).
    api.session.add(
        installment(
            user_id=USER,
            contract_id="c-late",
            first_due_date=date(2026, 11, 30),
            months=2,
            principal=Decimal("1000.00"),
        )
    )
    api.session.flush()
    months = get_months(api).json()["months"]
    assert [(m["month"], [i["installment_no"] for i in m["installments"]]) for m in months] == [
        ("2026-11", [1]),
        ("2026-12", [2]),
    ]
    assert [m["installments"][0]["is_last"] for m in months] == [False, True]


def test_DM_01_nothing_owed_gives_the_current_month_only(plan_api: Api) -> None:
    configure(plan_api)
    assert get_months(plan_api).json() == {
        "months": [row("2026-11", "0.00", [])],
        "months_truncated": False,
    }


def test_DM_02_a_one_month_installment_is_first_and_last(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    once = manual(api, "250.00", 1, date(2026, 11, 1), "once")
    assert get_months(api).json()["months"] == [
        row("2026-11", "250.00", [line(once, "once", "250.00", 1, 1, "2026-11")])
    ]


def test_DM_02_installments_are_listed_in_recorded_order(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    ids = [manual(api, "100.00", 1, date(2026, 11, 1), name) for name in ["c", "a", "b"]]
    lines = get_months(api).json()["months"][0]["installments"]
    assert [i["installment_id"] for i in lines] == [str(i) for i in ids]


# --- DM-03: totals and flags, as the L65 verdict and the plan compute them ----------------


@pytest.mark.parametrize(
    ("monthly", "over_budget", "over_one_third"),
    [
        ("4000.00", False, False),  # exactly the budget is within it
        ("4000.01", True, False),
        ("5000.00", True, False),  # exactly a third of 15,000.00 is not RED
        ("5000.01", True, True),
    ],
)
def test_DM_03_flags_use_the_L65_edges(
    plan_api: Api, monthly: str, over_budget: bool, over_one_third: bool
) -> None:
    configure(plan_api, income="15000.00", budget="4000.00")
    manual(plan_api, monthly, 1, date(2026, 11, 1))
    [month] = get_months(plan_api).json()["months"]
    assert (month["total"], month["budget"]) == (monthly, "4000.00")
    assert (month["over_budget"], month["over_one_third"]) == (over_budget, over_one_third)


def test_DM_03_totals_match_the_payoff_plan_month_by_month(plan_api: Api) -> None:
    api = plan_api
    configure(api, budget="1000.00")
    manual(api, "700.00", 5, date(2026, 10, 1))
    manual(api, "450.50", 3, date(2027, 1, 1))
    api.session.add(installment(user_id=USER, contract_id="c-w", months=2))
    api.session.flush()
    months = get_months(api).json()["months"]
    plan = api.call("GET", "/assistant/plan").json()["months"]
    assert [(m["month"], m["total"], m["over_budget"]) for m in months] == [
        (p["month"], p["total"], p["over_budget"]) for p in plan
    ]
    # Each total is the sum of the lines listed under it.
    for m in months:
        assert Decimal(m["total"]) == sum(
            (Decimal(i["monthly_amount"]) for i in m["installments"]), Decimal("0.00")
        )


# --- DM-04: count -------------------------------------------------------------------------


def test_DM_04_count_gives_exactly_that_many_months(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    manual(api, "500.00", 2, date(2026, 11, 1))
    months = get_months(api, "?count=6").json()["months"]
    assert [(m["month"], m["total"], len(m["installments"])) for m in months] == [
        ("2026-11", "500.00", 1),
        ("2026-12", "500.00", 1),
        ("2027-01", "0.00", 0),
        ("2027-02", "0.00", 0),
        ("2027-03", "0.00", 0),
        ("2027-04", "0.00", 0),
    ]
    assert len(get_months(api, "?count=1").json()["months"]) == 1
    assert len(get_months(api, "?count=600").json()["months"]) == 600


@pytest.mark.parametrize(
    "query",
    [
        "?count=0",
        "?count=601",
        "?count=6.0",
        "?count=%2B6",  # "+6"
        "?count=-1",
        "?count=",
        "?count=six",
        "?count=%E0%B9%96",  # Thai digit six
        "?count=1&count=2",
        "?months=6",
    ],
)
def test_DM_04_a_bad_count_is_422(plan_api: Api, query: str) -> None:
    configure(plan_api)
    response = get_months(plan_api, query)
    assert response.status_code == 422
    assert all(set(e) == {"type", "loc"} for e in response.json()["detail"])


# --- DM-05: which installments count --------------------------------------------------------

DISPUTED = {"status": "disputed", "disputed_at": datetime(2026, 10, 1, tzinfo=UTC)}


@pytest.mark.parametrize(
    ("fields", "counted"),
    [
        ({}, True),
        (DISPUTED | {"dispute_signal_status": "sent"}, True),  # owed until cancelled
        ({"status": "paid_off", "paid_amount": Decimal("2000.00")}, False),
        ({"status": "cancelled"}, False),
        ({"paid_amount": Decimal("2000.00")}, False),  # nothing left to pay
    ],
    ids=["active", "disputed", "paid_off", "cancelled", "fully_paid"],
)
def test_DM_05_which_installments_count(
    plan_api: Api, fields: dict[str, Any], counted: bool
) -> None:
    api = plan_api
    configure(api)
    api.session.add(installment(**{"user_id": USER, "contract_id": "c-1"} | fields))
    api.session.flush()
    [month, *_] = get_months(api).json()["months"]
    assert (month["total"], len(month["installments"])) == (
        ("500.00", 1) if counted else ("0.00", 0)
    )


def test_DM_05_a_consolidated_installment_gives_way_to_its_loan(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    paid_off = installment(user_id=USER, contract_id="c-old")
    api.session.add(paid_off)
    api.session.flush()
    loan = approved_consolidation(api.session, paid_off, Decimal("2000.00"))
    months = get_months(api).json()["months"]
    listed = {i["installment_id"] for m in months for i in m["installments"]}
    assert listed == {str(loan.id)}


# --- DM-06: settings, auth and other users ---------------------------------------------------


def test_DM_06_no_settings_is_409(plan_api: Api) -> None:
    response = get_months(plan_api)
    assert (response.status_code, response.json()) == (409, SETTINGS_REQUIRED)


def test_DM_06_no_user_is_401(plan_api: Api) -> None:
    assert get_months(plan_api, user=None).status_code == 401


def test_DM_06_another_users_installments_never_appear(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    api.session.add(installment(user_id="user_b", contract_id="c-b"))
    api.session.flush()
    assert get_months(api).json()["months"] == [row("2026-11", "0.00", [])]


# --- DM-07: the 600-month cap ------------------------------------------------------------------


def test_DM_07_rows_stop_at_600_months_and_say_so(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    manual(api, "10.00", 600, date(2026, 12, 1))  # Dec 2026 .. Nov 2076: 601 months from now
    body = get_months(api).json()
    assert (len(body["months"]), body["months_truncated"]) == (600, True)
    assert body["months"][-1]["month"] == "2076-10"
    # With count, the caller chose the length: nothing is cut.
    assert get_months(api, "?count=600").json()["months_truncated"] is False


def test_DM_07_exactly_600_months_is_not_truncated(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    manual(api, "10.00", 600, date(2026, 11, 1))  # Nov 2026 .. Oct 2076
    body = get_months(api).json()
    assert (len(body["months"]), body["months_truncated"]) == (600, False)
    assert body["months"][-1]["installments"][0]["is_last"] is True


# --- DM-08: over_by, last_month and platform_name (Session 17) -----------------------------


@pytest.mark.parametrize(
    ("monthly", "over_by"),
    [
        ("3999.99", "0.00"),  # under the budget
        ("4000.00", "0.00"),  # exactly the budget is not over
        ("4000.01", "0.01"),
        ("6500.00", "2500.00"),
    ],
)
def test_DM_08_over_by_is_total_minus_budget_only_when_over(
    plan_api: Api, monthly: str, over_by: str
) -> None:
    configure(plan_api, budget="4000.00")
    manual(plan_api, monthly, 1, date(2026, 11, 1))
    [month] = get_months(plan_api).json()["months"]
    assert month["over_by"] == over_by
    assert month["over_budget"] is (over_by != "0.00")


def test_DM_08_a_month_with_nothing_due_is_not_over(plan_api: Api) -> None:
    configure(plan_api, budget="0.00")
    months = get_months(plan_api, "?count=2").json()["months"]
    assert [(m["total"], m["over_by"]) for m in months] == [("0.00", "0.00"), ("0.00", "0.00")]


def test_DM_08_each_line_names_its_last_month_and_its_app(plan_api: Api) -> None:
    api = plan_api
    configure(api)
    phone = manual(api, "500.00", 14, date(2026, 9, 1), "phone", platform_name="ShopDemo")
    bag = manual(api, "300.00", 2, date(2026, 12, 1), "bag")
    months = get_months(api, "?count=2").json()["months"]
    assert [
        [(i["installment_id"], i["platform_name"], i["last_month"]) for i in m["installments"]]
        for m in months
    ] == [
        [(str(phone), "ShopDemo", "2027-10")],
        [(str(phone), "ShopDemo", "2027-10"), (str(bag), None, "2027-01")],
    ]
