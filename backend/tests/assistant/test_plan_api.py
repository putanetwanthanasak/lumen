"""AS-07, AS-08 and the AS-01/AS-05 numbers through GET /assistant/plan: the plan
over the Ledger, with "today" fixed at 2026-11-10 (the plan_api fixture)."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.clock import date_in_bangkok, today
from app.config import Settings, get_settings
from app.db import Base
from app.main import app
from app.models import UserSettings
from tests.db.factories import installment, manual_installment, profile, user_balance
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

SETTINGS_REQUIRED = {
    "detail": {
        "code": "SETTINGS_REQUIRED",
        "message": "set income and budget with POST /settings first",
    }
}


def configure(api: Api, budget: str = "5000.00") -> None:
    api.session.add(
        UserSettings(
            user_id=USER,
            auto_save_enabled=False,
            **profile() | {"monthly_installment_budget": Decimal(budget)},
        )
    )
    api.session.flush()


def manual(api: Api, monthly: str, months: int, first: date = date(2026, 11, 1), **kw: Any) -> None:
    fields = {
        "user_id": USER,
        "client_request_id": str(uuid.uuid4()),
        "principal": Decimal(monthly) * months,
        "monthly_amount": Decimal(monthly),
        "months": months,
        "first_due_date": first,
    } | kw
    api.session.add(manual_installment(**fields))
    api.session.flush()


def webhook(api: Api, monthly: str, months: int, **kw: Any) -> None:
    fields = {
        "user_id": USER,
        "contract_id": str(uuid.uuid4()),
        "principal": Decimal(monthly) * months,
        "monthly_amount": Decimal(monthly),
        "months": months,
    } | kw
    api.session.add(installment(**fields))
    api.session.flush()


def get_plan(api: Api, user: str | None = USER) -> Any:
    return api.call("GET", "/assistant/plan", user=user)


def row_counts(api: Api) -> dict[str, int]:
    return {
        table.name: api.session.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
    }


# --- AS-01 over HTTP: the doc example -----------------------------------------------


def test_AS_01_doc_example_over_http(plan_api: Api) -> None:
    configure(plan_api)
    manual(plan_api, "3700.00", 3)
    manual(plan_api, "2000.00", 2)
    plan_api.session.add(user_balance(user_id=USER, savings_balance=Decimal("1000.00")))
    plan_api.session.flush()

    response = get_plan(plan_api)

    assert response.status_code == 200
    assert response.json() == {
        "months": [
            {
                "month": "2026-11",
                "total": "5700.00",
                "budget": "5000.00",
                "over_budget": True,
                "headroom": "0.00",
            },
            {
                "month": "2026-12",
                "total": "5700.00",
                "budget": "5000.00",
                "over_budget": True,
                "headroom": "0.00",
            },
            {
                "month": "2027-01",
                "total": "3700.00",
                "budget": "5000.00",
                "over_budget": False,
                "headroom": "1300.00",
            },
        ],
        "months_truncated": False,
        "back_in_budget_month": "2027-01",
        "pause_until": "2027-01",
        "safe_new_monthly": "1300.00",
        "safe_new_from": "2027-01",
        "safe_new_months": 12,
        "buffer_plan": {
            "shortfall": "1400.00",
            "remaining_gap": "1400.00",
            "balance": "1000.00",
            "covered": False,
            "still_short": "400.00",
        },
        "consolidation": {"eligible": False, "reason": "NOT_NEEDED", "estimate": None},
    }


# --- AS-05 over HTTP: eligible, with the example-rate estimate ----------------------


def test_AS_05_eligible_plan_returns_the_estimate_labelled_as_an_example(plan_api: Api) -> None:
    configure(plan_api)
    manual(plan_api, "3700.00", 3)
    manual(plan_api, "2000.00", 3)

    body = get_plan(plan_api).json()

    assert body["consolidation"] == {
        "eligible": True,
        "reason": "ELIGIBLE",
        "estimate": {
            "principal": "17100.00",
            "annual_rate": "0.18",
            "rate_is_example": True,
            "rate_note": "example, not a real rate",
            "term_months": 24,
            "first_due_month": "2026-12",
            "monthly_payment": "853.71",
            "total_cost": "20489.04",
            "current_remaining_total": "17100.00",
            "extra_cost": "3389.04",
            "current_monthly_total": "5700.00",
            "monthly_reduction": "4846.29",
        },
    }


def test_AS_05_rate_and_term_come_from_config(plan_api: Api) -> None:
    configure(plan_api)
    manual(plan_api, "5700.00", 3)
    app.dependency_overrides[get_settings] = lambda: Settings(
        consolidation_example_annual_rate=Decimal("0.12"),
        consolidation_example_term_months=12,
    )
    try:
        estimate = get_plan(plan_api).json()["consolidation"]["estimate"]
    finally:
        del app.dependency_overrides[get_settings]

    assert (estimate["annual_rate"], estimate["term_months"]) == ("0.12", 12)
    assert estimate["monthly_payment"] == "1519.32"  # 17,100 at 1% a month over 12
    assert estimate["total_cost"] == "18231.84"


# --- AS-07: which installments count, and what each takes to pay off ---------------


def test_AS_07_only_the_owed_set_counts(plan_api: Api) -> None:
    configure(plan_api)
    manual(plan_api, "1000.00", 3)
    webhook(plan_api, "400.00", 3, status="paid_off", paid_amount=Decimal("1200.00"))
    webhook(plan_api, "800.00", 3, status="cancelled")

    body = get_plan(plan_api).json()

    assert [m["total"] for m in body["months"]] == ["1000.00", "1000.00", "1000.00"]


def test_AS_07_webhook_late_fees_and_past_manual_months_shape_the_principal(
    plan_api: Api,
) -> None:
    configure(plan_api)
    # August to January: 3 of 6 months left from November, 3 x 2,000.00.
    manual(plan_api, "2000.00", 6, first=date(2026, 8, 1))
    # 4 x 1,000.00 from November with 500.00 in late fees: the Ledger's 4,500.00 is
    # more than the 4,000.00 still scheduled.
    webhook(plan_api, "1000.00", 4, late_fees_accrued=Decimal("500.00"))
    manual(plan_api, "3700.00", 3)

    estimate = get_plan(plan_api).json()["consolidation"]["estimate"]

    assert estimate["principal"] == "21600.00"


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"overdue_days": 15}, "OVERDUE_DEBT"),
        (
            {
                "status": "disputed",
                "disputed_at": datetime(2026, 11, 2, tzinfo=UTC),
                "dispute_signal_status": "sent",
            },
            "DISPUTED_DEBT",
        ),
    ],
)
def test_AS_07_an_overdue_or_disputed_installment_in_the_ledger_blocks_eligibility(
    plan_api: Api, fields: dict[str, Any], reason: str
) -> None:
    configure(plan_api)
    manual(plan_api, "5700.00", 3)
    webhook(plan_api, "100.00", 2, **fields)

    assert get_plan(plan_api).json()["consolidation"] == {
        "eligible": False,
        "reason": reason,
        "estimate": None,
    }


def test_AS_07_another_users_installments_never_count(plan_api: Api) -> None:
    configure(plan_api)
    manual(plan_api, "5700.00", 3, user_id="someone_else")

    body = get_plan(plan_api).json()

    assert [m["total"] for m in body["months"]] == ["0.00"]


# --- AS-08: settings required, read-only, the clock --------------------------------


def test_AS_08_no_settings_is_409_settings_required(plan_api: Api) -> None:
    manual(plan_api, "5700.00", 3)

    response = get_plan(plan_api)

    assert response.status_code == 409
    assert response.json() == SETTINGS_REQUIRED


def test_AS_08_settings_from_before_L63_are_409(plan_api: Api) -> None:
    plan_api.session.add(UserSettings(user_id=USER, auto_save_enabled=False))
    plan_api.session.flush()

    assert get_plan(plan_api).status_code == 409


def test_AS_08_no_user_header_is_401(plan_api: Api) -> None:
    assert get_plan(plan_api, user=None).status_code == 401


def test_AS_08_plan_writes_nothing(plan_api: Api) -> None:
    configure(plan_api)
    manual(plan_api, "3700.00", 3)
    manual(plan_api, "2000.00", 3)
    before = row_counts(plan_api)

    assert get_plan(plan_api).status_code == 200

    assert row_counts(plan_api) == before


def test_AS_08_today_is_the_bangkok_date() -> None:
    # 17:30 UTC on 31 October is 00:30 on 1 November in Bangkok (UTC+7).
    assert date_in_bangkok(datetime(2026, 10, 31, 17, 30, tzinfo=UTC)) == date(2026, 11, 1)
    assert date_in_bangkok(datetime(2026, 10, 31, 16, 59, tzinfo=UTC)) == date(2026, 10, 31)
    assert type(today()) is date


def test_AS_08_the_month_comes_from_the_clock(api: Api) -> None:
    configure(api)
    manual(api, "1000.00", 3)
    app.dependency_overrides[today] = lambda: date(2026, 12, 31)

    months = get_plan(api).json()["months"]

    assert [m["month"] for m in months] == ["2026-12", "2027-01"]


def test_AS_08_example_rate_defaults_and_bounds() -> None:
    fields = Settings.model_fields
    assert fields["consolidation_example_annual_rate"].default == Decimal("0.18")
    assert fields["consolidation_example_term_months"].default == 24
    assert Settings(consolidation_example_annual_rate="0.18").consolidation_example_annual_rate == (
        Decimal("0.18")
    )
    for bad in (
        {"consolidation_example_annual_rate": "1"},
        {"consolidation_example_annual_rate": "-0.01"},
        {"consolidation_example_annual_rate": "0.12345"},
        {"consolidation_example_term_months": 0},
        {"consolidation_example_term_months": 601},
    ):
        with pytest.raises(ValidationError):
            Settings(**bad)


# --- Review F2: the safe amount never gets RED from "think before you buy" ----------


def test_AS_03_safe_new_monthly_previews_without_red_when_the_budget_is_above_a_third(
    plan_api: Api,
) -> None:
    # L64 saves a budget above a third of income with a warning; L65 still gives RED
    # above 4,000.00 a month here.
    plan_api.session.add(
        UserSettings(
            user_id=USER,
            auto_save_enabled=False,
            **profile()
            | {"income": Decimal("12000.00"), "monthly_installment_budget": Decimal("5000.00")},
        )
    )
    plan_api.session.flush()
    body = get_plan(plan_api).json()
    entry = {
        "client_request_id": "req-safe",
        "kind": "purchase",
        "item_price": "1.00",
        "months": 12,
        "monthly_amount": body["safe_new_monthly"],
        "first_due_month": body["safe_new_from"],
    }

    verdict = plan_api.call("POST", "/installments/preview", entry).json()["verdict"]

    assert verdict == "GREEN"
    assert body["safe_new_monthly"] == "4000.00"
