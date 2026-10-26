"""MI-xx: POST /installments, manual entry (L62), saving by the user's rule (L63) and
the alert with the L43 monthly total. 05 has no IDs for this, so MI-01 to MI-12 are
new (Session 12). MI-05 and a committed MI-06 are in tests/concurrency, MI-10 and
MI-12 in tests/db."""

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.ledger.reconcile import InvariantViolationError
from app.models import (
    MANUAL_VENDOR,
    AuditLog,
    Installment,
    Notification,
    SavingsTransaction,
    UserBalance,
)
from app.savings import service as savings
from app.webhooks.signature import get_vendor_secrets
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

OPENING = Decimal("10000.00")
BOTH_MODES = pytest.mark.parametrize(
    "rule", [{"percent": 10}, {"fixed": "120.00"}], ids=["percent", "fixed"]
)


def entry(**overrides: Any) -> dict[str, Any]:
    return {
        "client_request_id": "req-1",
        "kind": "purchase",
        "item_price": "1200.00",
        "months": 10,
        "monthly_amount": "130.00",
        "first_due_month": "2026-11",
        "item_name": "หูฟัง",
    } | overrides


def post(api: Api, data: Any, user: str | None = USER) -> Any:
    return api.call("POST", "/installments", data, user=user)


def count(api: Api, model: Any, *where: Any) -> int:
    return api.session.execute(select(func.count()).select_from(model).where(*where)).scalar_one()


def installments(api: Api) -> list[Installment]:
    api.session.expire_all()
    return list(api.session.execute(select(Installment).order_by(Installment.created_at)).scalars())


def savings_amounts(api: Api) -> list[Decimal]:
    return list(api.session.execute(select(SavingsTransaction.amount)).scalars())


# --- MI-01: recorded in the Ledger --------------------------------------------------


def test_MI_01_entry_is_recorded_in_the_ledger(api: Api) -> None:
    response = post(api, entry())
    assert response.status_code == 201
    [row] = installments(api)
    assert response.json()["installment_id"] == str(row.id)
    assert response.json()["status"] == "created"
    assert (row.user_id, row.vendor, row.client_request_id, row.kind, row.item_name) == (
        USER,
        MANUAL_VENDOR,
        "req-1",
        "purchase",
        "หูฟัง",
    )
    assert (row.principal, row.months, row.monthly_amount) == (
        Decimal("1200.00"),
        10,
        Decimal("130.00"),
    )
    assert row.fee_total == Decimal("100.00")  # 10 x 130.00 - 1,200.00
    assert row.first_due_date == date(2026, 11, 1)
    assert (row.status, row.paid_amount) == ("active", Decimal("0.00"))
    # L41 platform debt data is unknown for a manual row: NULL, never a made-up 0.
    assert (row.min_payment, row.late_fee_per_period, row.monthly_rate) == (None, None, None)


def test_MI_01_fee_total_is_zero_when_schedule_is_below_price(api: Api) -> None:
    post(api, entry(item_price="1000.00", months=3, monthly_amount="333.33"))
    [row] = installments(api)
    assert row.fee_total == Decimal("0.00")


def test_MI_01_item_name_is_optional(api: Api) -> None:
    data = entry()
    del data["item_name"]
    assert post(api, data).status_code == 201
    [row] = installments(api)
    assert row.item_name == ""


def test_MI_01_entry_shows_in_debt_summary(api: Api) -> None:
    post(api, entry())
    summary = api.call("GET", "/debts/summary").json()
    assert summary["monthly_total"] == "130.00"
    [line] = summary["installments"]
    assert (line["vendor"], line["item_name"], line["owed"]) == (MANUAL_VENDOR, "หูฟัง", True)
    assert line["last_due_date"] == "2027-08-01"


# --- MI-02 and MI-03: saving by the user's rule ---------------------------------------


@pytest.mark.parametrize(
    ("rule", "price", "expected"),
    [
        ({"percent": 10}, "1200.00", "120.00"),
        ({"percent": 15}, "33.33", "4.99"),  # ROUND_DOWN
        ({"percent": 1}, "20000.00", "200.00"),  # no cap
        ({"fixed": "120.00"}, "1200.00", "120.00"),
        ({"fixed": "75.50"}, "10.00", "75.50"),  # fixed ignores the price
    ],
)
def test_MI_02_saves_by_the_users_rule(
    api: Api, rule: dict[str, Any], price: str, expected: str
) -> None:
    opt_in(api.session, **rule)
    response = post(api, entry(item_price=price))
    assert response.status_code == 201
    assert response.json()["saved_amount"] == expected

    [tx] = api.session.execute(select(SavingsTransaction)).scalars().all()
    [row] = installments(api)
    assert (tx.type, tx.amount, tx.user_id, tx.installment_id) == (
        "auto_save",
        Decimal(expected),
        USER,
        row.id,
    )
    assert (tx.source_vendor, tx.source_event_id) == (None, None)  # no webhook event
    balance = api.session.execute(select(UserBalance.savings_balance)).scalar_one()
    assert balance == Decimal(expected)  # INV-1
    assert api.bank.get_balance(USER) == OPENING - Decimal(expected)


def test_MI_02_percent_result_zero_saves_nothing(api: Api) -> None:
    opt_in(api.session, percent=1)
    response = post(api, entry(item_price="0.99"))
    assert response.status_code == 201
    assert response.json()["saved_amount"] == "0.00"
    assert savings_amounts(api) == []


@pytest.mark.parametrize(
    "settings", [None, {"enabled": False}, {"consent": False}], ids=["none", "off", "no-consent"]
)
def test_MI_02_no_saving_without_auto_save(api: Api, settings: dict[str, Any] | None) -> None:
    if settings is not None:
        opt_in(api.session, **settings)
    response = post(api, entry())
    assert response.status_code == 201  # the installment is recorded all the same
    assert response.json()["saved_amount"] == "0.00"
    assert savings_amounts(api) == []
    assert api.bank.get_balance(USER) == OPENING


@BOTH_MODES
@pytest.mark.parametrize("kind", ["cash_withdrawal", "cash_loan"])
def test_MI_03_cash_kinds_never_save(api: Api, kind: str, rule: dict[str, Any]) -> None:
    opt_in(api.session, **rule)
    response = post(api, entry(kind=kind, item_price="15000.00"))
    assert response.status_code == 201
    assert response.json()["saved_amount"] == "0.00"
    assert savings_amounts(api) == []
    assert api.bank.get_balance(USER) == OPENING
    [row] = installments(api)
    assert row.kind == kind


# --- MI-04: a double submit records once ------------------------------------------


@BOTH_MODES
def test_MI_04_sequential_double_submit_records_and_saves_once(
    api: Api, rule: dict[str, Any]
) -> None:
    opt_in(api.session, **rule)
    first = post(api, entry())
    second = post(api, entry())

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json() | {"status": "duplicate"}
    assert len(installments(api)) == 1
    assert savings_amounts(api) == [Decimal("120.00")]
    assert count(api, Notification) == 1
    assert len(api.push.attempts) == 1  # pushed once
    assert count(api, AuditLog, AuditLog.action == "installment_recorded") == 1
    assert api.bank.get_balance(USER) == OPENING - Decimal("120.00")  # debited once


def test_MI_04_third_submit_after_a_second_entry_still_replays(api: Api) -> None:
    opt_in(api.session)
    first = post(api, entry())
    post(api, entry(client_request_id="req-2", item_price="500.00", monthly_amount="50.00"))
    again = post(api, entry())
    assert again.status_code == 200
    assert again.json()["installment_id"] == first.json()["installment_id"]
    assert again.json()["saved_amount"] == "120.00"
    assert again.json()["monthly_total"] == "180.00"  # the total now, both owed
    assert len(installments(api)) == 2


# --- MI-06: the same request id with other fields ------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"item_price": "1300.00"},
        {"months": 12},
        {"monthly_amount": "131.00"},
        {"first_due_month": "2026-12"},
        {"kind": "cash_loan"},
        {"item_name": "ลำโพง"},
    ],
)
def test_MI_06_same_request_id_other_fields_conflicts(api: Api, change: dict[str, Any]) -> None:
    opt_in(api.session)
    post(api, entry())
    response = post(api, entry(**change))
    assert response.status_code == 409
    [row] = installments(api)
    assert row.principal == Decimal("1200.00")  # the first entry, unchanged
    assert savings_amounts(api) == [Decimal("120.00")]
    reused = api.session.execute(
        select(AuditLog).where(AuditLog.action == "client_request_id_reused")
    ).scalar_one()
    assert (reused.user_id, reused.actor, reused.ref_id) == (USER, "user", str(row.id))


def test_MI_06_same_request_id_from_another_user_is_a_new_entry(api: Api) -> None:
    assert post(api, entry()).status_code == 201
    assert post(api, entry(), user="user_b").status_code == 201
    assert sorted(row.user_id for row in installments(api)) == [USER, "user_b"]


# --- MI-07: validation ------------------------------------------------------------------


def _raw(data: dict[str, Any], key: str, raw: bytes) -> bytes:
    return json.dumps(data | {key: "@"}).encode().replace(b'"@"', raw)


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("months", b"0"),
        ("months", b"601"),
        ("months", b'"10"'),
        ("months", b"10.0"),
        ("item_price", b'"0.00"'),
        ("item_price", b"1200.00"),  # JSON number (L49)
        ("item_price", b'"1200.001"'),
        ("monthly_amount", b'"0"'),
        ("monthly_amount", b'"-130.00"'),
        ("first_due_month", b'"2026-13"'),
        ("first_due_month", b'"2026-1"'),
        ("first_due_month", b'"2026-11-01"'),
        ("first_due_month", b'"0000-01"'),
        ("first_due_month", b"202611"),
        ("kind", b'"credit_card"'),
        ("item_name", b'"a\\u0000b"'),
        ("item_name", b'"a\\nb"'),
        ("client_request_id", b'""'),
        ("client_request_id", b'"r\\u0007"'),
        ("unknown", b'"x"'),
    ],
)
def test_MI_07_bad_fields_rejected(api: Api, key: str, raw: bytes) -> None:
    response = post(api, _raw(entry(), key, raw))
    assert response.status_code == 422, response.text
    assert all(set(e) == {"type", "loc"} for e in response.json()["detail"])  # R5
    assert installments(api) == []


@pytest.mark.parametrize("field", ["client_request_id", "kind", "item_price", "first_due_month"])
def test_MI_07_required_fields(api: Api, field: str) -> None:
    data = entry()
    del data[field]
    assert post(api, data).status_code == 422


def test_MI_07_schedule_too_large_for_numeric_rejected(api: Api) -> None:
    # 600 x 9,999,999,999.99 would overflow Numeric(12,2): a 422, not a 500.
    response = post(api, entry(months=600, monthly_amount="9999999999.99"))
    assert response.status_code == 422
    assert installments(api) == []


@pytest.mark.parametrize(("month", "months"), [("9999-12", 2), ("9999-01", 13), ("9990-01", 600)])
def test_MI_07_schedule_ending_after_year_9999_rejected(api: Api, month: str, months: int) -> None:
    # Review F3: the last due date would be past date.max, a 500 on every retry.
    response = post(api, entry(first_due_month=month, months=months))
    assert response.status_code == 422
    assert installments(api) == []


@pytest.mark.parametrize(("month", "months"), [("9999-12", 1), ("9999-01", 12)])
def test_MI_07_schedule_ending_in_year_9999_accepted(api: Api, month: str, months: int) -> None:
    assert post(api, entry(first_due_month=month, months=months)).status_code == 201


@pytest.mark.parametrize("user", [None, "", "a\nb"])
def test_MI_07_missing_or_bad_user_is_401(api: Api, user: str | None) -> None:
    assert post(api, entry(), user=user).status_code == 401
    assert installments(api) == []


# --- MI-08: the alert (L43) ------------------------------------------------------------


def test_MI_08_alert_carries_the_new_monthly_total(api: Api) -> None:
    post(api, entry(client_request_id="req-0", item_price="500.00", monthly_amount="50.00"))
    response = post(api, entry())
    assert response.json()["monthly_total"] == "180.00"

    [_, second] = api.push.delivered
    assert second.title == "บันทึกรายการผ่อนแล้ว"
    assert second.body == (
        "หูฟัง ราคา 1,200 บาท ผ่อน 10 เดือน เดือนละ 130 บาท ยอดผ่อนรวมต่อเดือนตอนนี้ 180 บาท"
    )
    stored = api.session.execute(
        select(Notification.kind, Notification.body, Notification.delivery_status).where(
            Notification.installment_id == response.json()["installment_id"]
        )
    ).one()
    assert stored == ("new_debt", second.body, "pushed")


def test_MI_08_alert_without_item_name_starts_with_price(api: Api) -> None:
    data = entry(item_price="999.50", monthly_amount="99.95")
    del data["item_name"]
    post(api, data)
    [push] = api.push.delivered
    assert push.body.startswith("ราคา 999.50 บาท")


@pytest.mark.parametrize(
    ("kind", "title", "notification_kind"),
    [
        ("cash_withdrawal", "บันทึกการเบิกเงินสดแล้ว", "cash_withdrawal"),
        ("cash_loan", "บันทึกการกู้เงินสดแล้ว", "cash_loan"),
    ],
)
def test_MI_08_cash_alert_titles(api: Api, kind: str, title: str, notification_kind: str) -> None:
    post(api, entry(kind=kind))
    [push] = api.push.delivered
    assert push.title == title
    assert "ยอดผ่อนรวมต่อเดือนตอนนี้ 130 บาท" in push.body
    assert api.session.execute(select(Notification.kind)).scalar_one() == notification_kind


def test_MI_08_failed_push_does_not_fail_the_entry(api: Api) -> None:
    api.push.fail = True
    response = post(api, entry())
    assert response.status_code == 201
    status = api.session.execute(select(Notification.delivery_status)).scalar_one()
    assert status == "inbox_only"


# --- MI-09: the safety net on manual entry ----------------------------------------------


@BOTH_MODES
def test_MI_09_safety_net_skips_below_protected_min(api: Api, rule: dict[str, Any]) -> None:
    opt_in(api.session, **rule)
    api.bank.set_balance(USER, Decimal("619.99"))  # 619.99 - 120.00 = 499.99
    response = post(api, entry())
    assert response.status_code == 201
    assert response.json()["saved_amount"] == "0.00"
    assert savings_amounts(api) == []
    assert api.bank.get_balance(USER) == Decimal("619.99")


@BOTH_MODES
def test_MI_09_safety_net_saves_at_exact_protected_min(api: Api, rule: dict[str, Any]) -> None:
    opt_in(api.session, **rule)
    api.bank.set_balance(USER, Decimal("620.00"))  # leaves exactly 500.00
    assert post(api, entry()).json()["saved_amount"] == "120.00"
    assert api.bank.get_balance(USER) == Decimal("500.00")


# --- MI-11: "manual" is never a webhook vendor --------------------------------------------


def test_MI_11_manual_is_not_a_webhook_vendor() -> None:
    # Webhook vendors come from configured secrets; "manual" has none, so no signed
    # webhook can create or change a manual row.
    assert MANUAL_VENDOR not in get_vendor_secrets()


def test_RS_02_violation_rolls_back_the_whole_entry(
    api: Api, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A simulated bug: the balance is credited one baht too much. Nothing of the
    entry may persist and no money may move."""
    opt_in(api.session)
    real_credit = savings._credit
    monkeypatch.setattr(
        savings,
        "_credit",
        lambda session, user_id, amount: real_credit(session, user_id, amount + Decimal(1)),
    )
    with caplog.at_level(logging.ERROR), pytest.raises(InvariantViolationError) as exc:
        post(api, entry())

    assert exc.value.violations == ["INV-1"]
    for model in (Installment, SavingsTransaction, UserBalance, Notification, AuditLog):
        assert count(api, model) == 0, model.__name__
    assert api.bank.get_balance(USER) == OPENING
    assert api.push.attempts == []
    [record] = caplog.records
    assert "manual entry rolled back" in record.getMessage()
    assert USER not in record.getMessage()  # S12


# --- S1 for manual entry: the bank moves the saving at most once -----------------------


def test_S1_manual_transfer_key_is_stable_per_request_and_distinct() -> None:
    key = savings.manual_transfer_key(USER, "req-1")
    assert key == savings.manual_transfer_key(USER, "req-1")
    assert key != savings.manual_transfer_key(USER, "req-2")
    assert key != savings.manual_transfer_key("user_b", "req-1")
    # No separator games: ("a:b", "c") and ("a", "b:c") are different requests.
    assert savings.manual_transfer_key("a:b", "c") != savings.manual_transfer_key("a", "b:c")
    # Never the same key as a webhook event's auto-save.
    assert key != savings.transfer_key(USER, "req-1")


def test_S1_manual_commit_fails_after_transfer_retry_debits_the_bank_once(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The transfer runs before COMMIT. If the commit fails, the rows roll back but the
    # money has moved; the user's retry carries the same client_request_id, so the
    # same key, and the bank does nothing the second time.
    opt_in(api.session)
    api.session.commit()  # kept by the rollback below: only the lost request rolls back
    session = api.session
    real_commit = session.commit

    def commit_fails_once() -> None:
        monkeypatch.setattr(session, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails_once)

    lost = post(api, entry())
    session.rollback()  # what get_session's close does after the failed request
    assert lost.status_code == 500
    assert installments(api) == []
    assert api.bank.get_balance(USER) == OPENING - Decimal("120.00")

    retry = post(api, entry())

    assert retry.status_code == 201, retry.text
    assert api.bank.get_balance(USER) == OPENING - Decimal("120.00")  # debited once
    assert savings_amounts(api) == [Decimal("120.00")]  # the retry did record the saving
