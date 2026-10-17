"""Installment creation (04 step 5a) and ID-05 (05 section 4.4, decision D1)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Installment, WebhookEvent
from app.providers.mock_bank import MockBankAccountProvider
from app.webhooks.processor import Outcome, contract_hash
from tests.processing.conftest import USER, VENDOR, auto_saves, balance, created, opt_in, run

pytestmark = pytest.mark.db


def test_installment_created_from_contract(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    data = created("evt_1", "c_1", "20000.00")
    run(db_session, data, bank)

    row = db_session.execute(select(Installment)).scalar_one()
    assert (row.user_id, row.vendor, row.contract_id, row.kind) == (
        USER,
        VENDOR,
        "c_1",
        "purchase",
    )
    assert (row.item_name, row.principal, row.months) == ("Headphones", Decimal("20000.00"), 6)
    assert (row.monthly_amount, row.fee_total, row.first_due_date) == (
        Decimal("3333.33"),
        Decimal("0.00"),
        date(2026, 11, 5),
    )
    assert (row.min_payment, row.late_fee_per_period, row.monthly_rate, row.overdue_days) == (
        Decimal("3333.33"),
        Decimal("100.00"),
        Decimal("0.020833"),
        0,
    )
    assert (row.status, row.paid_amount, row.late_fees_accrued) == (
        "active",
        Decimal("0.00"),
        Decimal("0.00"),
    )


def event_status(session: Session, event_id: str) -> str:
    return session.execute(
        select(WebhookEvent.status).where(WebhookEvent.event_id == event_id)
    ).scalar_one()


def reuse_entry(session: Session) -> AuditLog:
    return session.execute(
        select(AuditLog).where(AuditLog.action == "contract_id_reused")
    ).scalar_one()


def test_ID_05_same_contract_new_event_id_is_duplicate(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    assert run(db_session, created("evt_1", "c_1"), bank) == Outcome.PROCESSED
    assert run(db_session, created("evt_2", "c_1"), bank) == Outcome.DUPLICATE

    installment_id = db_session.execute(select(Installment.id)).scalar_one()  # still one
    [tx] = auto_saves(db_session)
    assert tx.source_event_id == "evt_1"
    assert balance(db_session) == (Decimal("80.00"), 1)
    assert bank.get_balance(USER) == Decimal("9920.00")  # debited once
    assert (event_status(db_session, "evt_1"), event_status(db_session, "evt_2")) == (
        "processed",
        "rejected",
    )
    entry = reuse_entry(db_session)
    assert (entry.ref_type, entry.ref_id) == ("installment", str(installment_id))
    assert entry.detail == {
        "installment_id": str(installment_id),
        "original_event_id": "evt_1",
        "event_id": "evt_2",
        "same_contract": True,
    }
    # A resend of the rejected event gets its first answer again (L59 1).
    assert run(db_session, created("evt_2", "c_1"), bank) == Outcome.DUPLICATE


@pytest.mark.parametrize(
    "change",
    [
        {"principal": "900.00"},
        {"item_name": "Other item"},
        {"monthly_rate": "0.000000"},
        {"user": "user_b"},  # same contract claimed for another user
    ],
    ids=["principal", "item_name", "monthly_rate", "user_ref"],
)
def test_ID_05_same_contract_different_content_is_conflict(
    db_session: Session, bank: MockBankAccountProvider, change: dict[str, str]
) -> None:
    opt_in(db_session)
    original = created("evt_1", "c_1")
    resent = created("evt_2", "c_1", **({"principal": "800.00"} | change))
    run(db_session, original, bank)
    assert run(db_session, resent, bank) == Outcome.CONTRACT_CONFLICT

    row = db_session.execute(select(Installment)).scalar_one()
    assert (row.principal, row.item_name, row.user_id) == (Decimal("800.00"), "Headphones", USER)
    assert len(auto_saves(db_session)) == 1
    assert auto_saves(db_session, "user_b") == []
    assert bank.get_balance(USER) == Decimal("9920.00")
    assert event_status(db_session, "evt_2") == "rejected"
    detail = reuse_entry(db_session).detail
    assert detail["same_contract"] is False
    assert detail["stored_hash"] == contract_hash(original)
    assert detail["received_hash"] == contract_hash(resent)
    assert detail["stored_hash"] != detail["received_hash"]
    # L59 (1): a resend gets the 409 again and writes nothing (still one reuse entry).
    assert run(db_session, resent, bank) == Outcome.CONTRACT_CONFLICT
    assert reuse_entry(db_session).detail == detail


def test_ID_05_cash_contract_resent_saves_nothing(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    opt_in(db_session)
    data = created("evt_1", "c_1", event_type="cash_loan_created")
    run(db_session, data, bank)
    assert run(db_session, created("evt_2", "c_1", event_type="cash_loan_created"), bank) == (
        Outcome.DUPLICATE
    )
    assert auto_saves(db_session) == []
