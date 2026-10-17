"""GET /debts/summary (04 section 9, L43, OR-04).

Owed means `active` or `disputed` with something left to pay. A disputed debt is
owed until the platform cancels it; a fully paid one disputed later is not owed again.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app.debts.service import add_months
from app.models import Installment
from app.notifications.copy import format_baht
from tests.webhooks.conftest import Webhook
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db

EMPTY = {
    "monthly_total": "0.00",
    "total_remaining": "0.00",
    "debt_free_date": None,
    "installments": [],
}


def open_debt(webhook: Webhook, n: int, user: str = "user_a", **contract: Any) -> None:
    data = payload(event_id=f"evt_{n}", user_ref=user)
    data["contract"] |= {"contract_id": f"c_{n}"} | contract
    assert webhook.post(data).status_code == 200


def pay(webhook: Webhook, n: int, amount: str) -> None:
    data = payload(
        "installment_payment_collected", event_id=f"evt_p{n}", contract_id=f"c_{n}", amount=amount
    )
    assert webhook.post(data).status_code == 200


def not_me(webhook: Webhook, n: int) -> None:
    installment_id = webhook.session.execute(
        select(Installment.id).where(Installment.contract_id == f"c_{n}")
    ).scalar_one()
    response = webhook.not_me(installment_id)
    assert response.status_code == 200, response.text


def summary(webhook: Webhook, user: str = "user_a") -> dict[str, Any]:
    response = webhook.get("/debts/summary", user)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def by_contract(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {line["contract_id"]: line for line in body["installments"]}


@pytest.mark.parametrize(
    "user",
    [None, "", "a" * 129, "user\x00a", "user\na"],
    ids=["none", "empty", "long", "nul", "lf"],
)
def test_summary_without_a_valid_demo_user_is_401(webhook: Webhook, user: str | None) -> None:
    response = webhook.get("/debts/summary", user)
    assert (response.status_code, response.json()) == (401, {"detail": "unauthorized"})


def test_summary_for_user_with_no_debts(webhook: Webhook) -> None:
    assert summary(webhook) == EMPTY


def test_summary_one_debt_exact_shape(webhook: Webhook) -> None:
    open_debt(webhook, 1)

    body = summary(webhook)

    [line] = body["installments"]
    assert line.pop("id")
    assert line == {
        "vendor": "shopdemo",
        "contract_id": "c_1",
        "kind": "purchase",
        "item_name": "Headphones",
        "principal": "20000.00",
        "monthly_amount": "3333.33",
        "months": 6,
        "paid_amount": "0.00",
        "late_fees_accrued": "0.00",
        "remaining": "20000.00",
        "status": "active",
        "disputed_at": None,
        "owed": True,
        "first_due_date": "2026-11-05",
        "last_due_date": "2027-04-05",
    }
    assert (body["monthly_total"], body["total_remaining"], body["debt_free_date"]) == (
        "3333.33",
        "20000.00",
        "2027-04-05",
    )


def test_summary_counts_only_owed_debts(webhook: Webhook) -> None:
    open_debt(webhook, 1, monthly_amount="1000.00", principal="6000.00", months=6)  # active
    open_debt(webhook, 2, monthly_amount="200.00", principal="400.00", months=2)  # paid off
    pay(webhook, 2, "400.00")
    open_debt(webhook, 3, monthly_amount="300.00", months=12)  # cancelled
    webhook.post(payload("installment_cancelled", event_id="evt_x3", contract_id="c_3"))
    open_debt(webhook, 4, monthly_amount="50.00", principal="500.00", months=10)  # disputed
    not_me(webhook, 4)
    pay(webhook, 1, "1000.00")

    body = summary(webhook)

    lines = by_contract(body)
    assert {c: (line["status"], line["owed"]) for c, line in lines.items()} == {
        "c_1": ("active", True),
        "c_2": ("paid_off", False),
        "c_3": ("cancelled", False),
        "c_4": ("disputed", True),  # owed until the platform cancels it
    }
    assert body["monthly_total"] == "1050.00"  # 1,000 + 50
    assert body["total_remaining"] == "5500.00"  # 5,000 + 500
    # c_1 ends 2027-04-05, c_4 2027-08-05; the cancelled c_3 (2027-10-05) does not count.
    assert body["debt_free_date"] == "2027-08-05"


def test_disputing_a_paid_off_debt_leaves_the_totals_unchanged(webhook: Webhook) -> None:
    """User correction (Session 9): a disputed debt counts only while still owed."""
    open_debt(webhook, 1, monthly_amount="1000.00", principal="6000.00")
    open_debt(webhook, 2, monthly_amount="200.00", principal="400.00", months=2)
    pay(webhook, 2, "400.00")
    before = summary(webhook)

    not_me(webhook, 2)

    after = summary(webhook)
    assert by_contract(after)["c_2"]["status"] == "disputed"
    assert by_contract(after)["c_2"]["owed"] is False
    for total in ("monthly_total", "total_remaining", "debt_free_date"):
        assert after[total] == before[total]
    assert after["monthly_total"] == "1000.00"


def test_late_fees_count_in_remaining(webhook: Webhook) -> None:
    open_debt(webhook, 1, principal="1000.00", fee_total="60.00")
    webhook.post(
        payload(
            "installment_overdue", event_id="evt_o", contract_id="c_1", late_fees_accrued="25.50"
        )
    )
    pay(webhook, 1, "100.00")

    line = by_contract(summary(webhook))["c_1"]
    assert (line["late_fees_accrued"], line["remaining"]) == ("25.50", "985.50")


def test_summary_shows_only_the_callers_debts(webhook: Webhook) -> None:
    open_debt(webhook, 1)
    open_debt(webhook, 2, user="user_b", monthly_amount="10.00")

    assert set(by_contract(summary(webhook))) == {"c_1"}
    assert summary(webhook, "user_b")["monthly_total"] == "10.00"
    assert summary(webhook, "user_c") == EMPTY


def test_L43_pushed_total_equals_the_summary_at_that_moment(webhook: Webhook) -> None:
    open_debt(webhook, 1, monthly_amount="1234.50")
    open_debt(webhook, 2, monthly_amount="1000.00")

    last_push = webhook.push.attempts[-1].body
    total = format_baht(Decimal(summary(webhook)["monthly_total"]))
    assert total == "2,234.50"
    assert f"ยอดผ่อนรวมต่อเดือนตอนนี้ {total} บาท" in last_push


@pytest.mark.parametrize(
    ("start", "months", "end"),
    [
        (date(2026, 11, 5), 0, date(2026, 11, 5)),
        (date(2026, 11, 5), 5, date(2027, 4, 5)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),  # leap year
        (date(2026, 8, 31), 1, date(2026, 9, 30)),
        (date(2026, 12, 15), 1, date(2027, 1, 15)),
        (date(2026, 1, 1), 599, date(2075, 12, 1)),  # MAX_MONTHS (600) - 1
    ],
)
def test_OR_04_last_due_date_month_arithmetic(start: date, months: int, end: date) -> None:
    assert add_months(start, months) == end
