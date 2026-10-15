"""Webhook payload schemas, without HTTP. The router tests (WH-04, WH-05) check
that each of these rejections reaches the client as a 422.
"""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import InstallmentKind
from app.schemas import (
    CashLoanCreated,
    InstallmentCancelled,
    InstallmentCreated,
    InstallmentOverdue,
    PaymentCollected,
    parse_event,
)
from tests.webhooks.payloads import EVENT_TYPES, encode, payload, raw_with, with_contract


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_every_event_type_parses(event_type: str) -> None:
    event = parse_event(encode(payload(event_type)))
    assert event.event_type == event_type
    assert event.contract_id == "ctr_88213"


def test_contract_money_and_rate_are_decimal() -> None:
    event = parse_event(encode(payload()))
    assert isinstance(event, InstallmentCreated)
    c = event.contract
    assert (c.principal, c.monthly_amount, c.fee_total) == (
        Decimal("20000.00"),
        Decimal("3333.33"),
        Decimal("0.00"),
    )
    assert (c.min_payment, c.late_fee_per_period) == (Decimal("3333.33"), Decimal("100.00"))
    assert c.monthly_rate == Decimal("0.020833")
    assert c.kind is InstallmentKind.PURCHASE
    for value in (c.principal, c.monthly_amount, c.min_payment, c.monthly_rate):
        assert type(value) is Decimal


def test_non_contract_events_carry_their_fields() -> None:
    paid = parse_event(encode(payload("installment_payment_collected")))
    assert isinstance(paid, PaymentCollected)
    assert (paid.amount, paid.installment_no) == (Decimal("3333.33"), 1)
    overdue = parse_event(encode(payload("installment_overdue")))
    assert isinstance(overdue, InstallmentOverdue)
    assert (overdue.overdue_days, overdue.late_fees_accrued) == (3, Decimal("100.00"))
    cancelled = parse_event(encode(payload("installment_cancelled")))
    assert isinstance(cancelled, InstallmentCancelled)
    assert cancelled.reason == "Order cancelled by buyer"


def test_cash_loan_event_carries_cash_loan_kind() -> None:
    event = parse_event(encode(payload("cash_loan_created")))
    assert isinstance(event, CashLoanCreated)
    assert event.contract.kind is InstallmentKind.CASH_LOAN


def _rejected(raw: bytes, message: str | None = None) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_event(raw)


# --- Required fields and ranges (WH-04) -------------------------------------------


@pytest.mark.parametrize("field", ["event_id", "event_type", "occurred_at", "user_ref", "contract"])
def test_missing_top_level_field_rejected(field: str) -> None:
    data = payload()
    del data[field]
    _rejected(encode(data))


@pytest.mark.parametrize(
    "field",
    [
        "principal",
        "months",
        "first_due_date",
        "min_payment",
        "late_fee_per_period",
        "monthly_rate",
        "overdue_days",
        "kind",
    ],
)
def test_missing_contract_field_rejected(field: str) -> None:
    # L41 fields are required: a silent default would make debt look free.
    data = payload()
    del data["contract"][field]
    _rejected(encode(data), "Field required")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"principal": "0.00"}, "greater than"),
        ({"principal": "-1.00"}, "plain decimal string"),
        ({"months": 0}, "greater than 0"),
        ({"months": -1}, "greater than 0"),
        ({"months": "6"}, "valid integer"),
        ({"overdue_days": -1}, "greater than or equal to 0"),
        ({"item_name": ""}, "at least 1 character"),
        ({"kind": "credit_card"}, "purchase"),
        ({"first_due_date": 1700000000}, "valid date"),
        ({"first_due_date": "05/11/2026"}, "valid date"),
    ],
)
def test_bad_contract_values_rejected(overrides: dict[str, Any], message: str) -> None:
    _rejected(encode(with_contract(**overrides)), message)


@pytest.mark.parametrize("literal", ["6.0", "6.5", "true"])
def test_months_must_be_a_json_integer(literal: str) -> None:
    _rejected(raw_with("months", literal), "valid integer")


@pytest.mark.parametrize(
    ("event_type", "overrides", "message"),
    [
        ("installment_payment_collected", {"amount": "0.00"}, "greater than"),
        ("installment_payment_collected", {"installment_no": 0}, "greater than or equal to 1"),
        ("installment_overdue", {"overdue_days": 0}, "greater than or equal to 1"),
        ("installment_overdue", {"late_fees_accrued": "-5.00"}, "plain decimal string"),
        ("installment_cancelled", {"reason": ""}, "at least 1 character"),
        ("installment_cancelled", {"contract_id": ""}, "at least 1 character"),
    ],
)
def test_bad_event_values_rejected(
    event_type: str, overrides: dict[str, Any], message: str
) -> None:
    _rejected(encode(payload(event_type, **overrides)), message)


def test_naive_occurred_at_rejected() -> None:
    _rejected(encode(payload(occurred_at="2026-10-12T09:30:00")), "timezone")


def test_unknown_event_type_rejected() -> None:
    data = payload()
    data["event_type"] = "installment_deleted"
    _rejected(encode(data), "does not match any")


@pytest.mark.parametrize(
    ("event_type", "kind"),
    [
        ("installment_created", "cash_withdrawal"),
        ("installment_created", "cash_loan"),
        ("cash_withdrawal_created", "purchase"),
        ("cash_loan_created", "cash_withdrawal"),
    ],
)
def test_kind_must_match_event_type(event_type: str, kind: str) -> None:
    # A cash event disguised as a purchase would otherwise be auto-saved (INV-5).
    data = payload(event_type)
    data["contract"]["kind"] = kind
    _rejected(encode(data), "must carry contract.kind")


def test_extra_top_level_field_rejected() -> None:
    _rejected(encode(payload(vendor="shopdemo")), "Extra inputs are not permitted")


def test_extra_contract_field_rejected() -> None:
    _rejected(encode(with_contract(discount="10.00")), "Extra inputs are not permitted")


@pytest.mark.parametrize("raw", [b"", b"not json", b"[]", b"null", b'{"event_id": "e"'])
def test_non_object_or_invalid_json_rejected(raw: bytes) -> None:
    _rejected(raw)


# --- Money (WH-05, L49) -------------------------------------------------------------


@pytest.mark.parametrize("literal", ["20000.00", "20000", "2e4"])
def test_money_as_json_number_rejected(literal: str) -> None:
    _rejected(raw_with("principal", literal), "must be a JSON string")


def test_rate_as_json_number_rejected() -> None:
    _rejected(raw_with("monthly_rate", "0.020833"), "must be a JSON string")


@pytest.mark.parametrize(
    "value", ["1.005", "1e3", " 1.00", "1_000.00", "+1.00", "๑๐.00", "10000000000.00", "10."]
)
def test_bad_money_strings_rejected(value: str) -> None:
    _rejected(encode(with_contract(principal=value)), "plain decimal string")


def test_L3_schema_rejects_what_postgres_would_round() -> None:
    # Postgres stores 123.455 as 123.46 without error (see test_money_types), so the
    # schema is the only place that can refuse it.
    _rejected(encode(with_contract(principal="123.455")), "plain decimal string")
