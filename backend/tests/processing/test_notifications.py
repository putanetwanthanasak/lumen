"""New-debt alerts at the service level (04 step 5e; 05 NT-01, NT-04, SV-03, SV-03a;
L43, L50, L58)."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.debts.service import summary
from app.ledger.reconcile import check_user_invariants
from app.models import Installment, Notification
from app.notifications.copy import format_baht
from app.notifications.service import notify_new_debt
from app.providers.mock_bank import MockBankAccountProvider
from app.schemas import InstallmentCreated, parse_event
from app.webhooks.processor import Outcome
from tests.processing.conftest import USER, created, process, run
from tests.webhooks.payloads import encode, payload

pytestmark = pytest.mark.db


def alerts(session: Session, user: str = USER) -> list[Notification]:
    session.expire_all()
    return list(session.execute(select(Notification).where(Notification.user_id == user)).scalars())


def monthly_total_in(body: str) -> str:
    return body.split("ยอดผ่อนรวมต่อเดือนตอนนี้ ")[1].split(" บาท")[0]


def installment_id(session: Session, contract_id: str) -> object:
    return session.execute(
        select(Installment.id).where(Installment.contract_id == contract_id)
    ).scalar_one()


def test_NT_01_new_installment_gets_one_new_debt_alert(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    result = process(db_session, created("evt_1", "c_1", "20000.00"), bank)

    [alert] = alerts(db_session)
    assert result.notification_id == alert.id
    assert (alert.kind, alert.title, alert.delivery_status) == (
        "new_debt",
        "รายการผ่อนใหม่",
        "pending",  # the push happens after commit, in the router
    )
    assert alert.installment_id == installment_id(db_session, "c_1")
    assert alert.body == (
        "มีรายการผ่อนใหม่จาก ShopDemo 20,000 บาท ผ่อน 6 เดือน "
        "ยอดผ่อนรวมต่อเดือนตอนนี้ 3,333.33 บาท ถ้าไม่ใช่คุณ แตะเพื่อแจ้ง"
    )


@pytest.mark.parametrize(
    ("event_type", "kind", "title"),
    [
        ("cash_withdrawal_created", "cash_withdrawal", "แจ้งเตือนเบิกเงินสด"),
        ("cash_loan_created", "cash_loan", "แจ้งเตือนกู้เงินสด"),
    ],
)
def test_SV_03_SV_03a_L50_cash_events_get_the_strong_alert(
    db_session: Session, bank: MockBankAccountProvider, event_type: str, kind: str, title: str
) -> None:
    run(db_session, created("evt_1", "c_1", "5000.00", event_type=event_type), bank)

    [alert] = alerts(db_session)
    assert (alert.kind, alert.title) == (kind, title)
    assert "5,000 บาท จาก ShopDemo ถ้าไม่ใช่คุณ แจ้งได้ทันที" in alert.body


def test_L43_alert_total_includes_the_new_debt_and_equals_the_summary(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, created("evt_1", "c_1", monthly_amount="1250.00"), bank)
    run(db_session, created("evt_2", "c_2", monthly_amount="0.50"), bank)
    run(db_session, created("evt_3", "c_3", monthly_amount="333.33"), bank)

    contracts = dict(db_session.execute(select(Installment.id, Installment.contract_id)).all())
    totals = {contracts[a.installment_id]: monthly_total_in(a.body) for a in alerts(db_session)}
    assert totals == {"c_1": "1,250", "c_2": "1,250.50", "c_3": "1,583.83"}
    # The last alert's total is what the summary returns now.
    assert totals["c_3"] == format_baht(summary(db_session, USER).monthly_total)


def test_L43_total_excludes_debts_no_longer_owed(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, created("evt_1", "c_1", "100.00", monthly_amount="100.00"), bank)
    paid = payload("installment_payment_collected", event_id="evt_p", contract_id="c_1")
    run(db_session, paid | {"amount": "100.00"}, bank)  # c_1 paid off
    run(db_session, created("evt_2", "c_2", monthly_amount="200.00"), bank)

    c_2 = installment_id(db_session, "c_2")
    [alert] = [a for a in alerts(db_session) if a.installment_id == c_2]
    assert monthly_total_in(alert.body) == "200"


@pytest.mark.parametrize("pending_type", ["installment_cancelled", "installment_payment_collected"])
def test_L58_alert_sent_even_when_a_replayed_event_changed_the_installment(
    db_session: Session, bank: MockBankAccountProvider, pending_type: str
) -> None:
    """A cancel (or a payment in full) that arrived first is replayed in 5f, before
    5e: the debt still alerts, and its total is the one at commit."""
    early = payload(pending_type, event_id="evt_early", contract_id="c_1")
    if pending_type == "installment_payment_collected":
        early |= {"amount": "800.00"}
    assert run(db_session, early, bank) == Outcome.PENDING_PARENT
    assert alerts(db_session) == []

    run(db_session, created("evt_1", "c_1", "800.00", monthly_amount="200.00"), bank)

    status = db_session.execute(select(Installment.status)).scalar_one()
    assert status == ("cancelled" if pending_type == "installment_cancelled" else "paid_off")
    [alert] = alerts(db_session)
    assert alert.installment_id == installment_id(db_session, "c_1")
    assert "ยอดผ่อนรวมต่อเดือนตอนนี้ 0 บาท" in alert.body
    assert summary(db_session, USER).monthly_total == Decimal("0.00")


def test_NT_04_resend_creates_no_second_alert(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    data = created("evt_1", "c_1")
    run(db_session, data, bank)

    again = process(db_session, data, bank)

    assert (again.outcome, again.notification_id) == (Outcome.DUPLICATE, None)
    assert len(alerts(db_session)) == 1


def test_NT_04_ID_05_same_contract_under_new_event_id_creates_no_second_alert(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, created("evt_1", "c_1"), bank)

    resent = process(db_session, created("evt_2", "c_1"), bank)
    changed = process(db_session, created("evt_3", "c_1", "900.00"), bank)

    assert (resent.outcome, resent.notification_id) == (Outcome.DUPLICATE, None)
    assert (changed.outcome, changed.notification_id) == (Outcome.CONTRACT_CONFLICT, None)
    assert len(alerts(db_session)) == 1


def test_NT_04_notify_twice_for_one_installment_keeps_one_row(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    """The DB guard on its own: a second call (as a racing transaction would make)
    gets nothing back and adds nothing."""
    data = created("evt_1", "c_1")
    first = process(db_session, data, bank).notification_id
    event = parse_event(encode(data))
    assert isinstance(event, InstallmentCreated)

    second = notify_new_debt(
        db_session, vendor="shopdemo", event=event, installment_id=installment_id(db_session, "c_1")
    )

    assert first is not None
    assert second is None
    assert [a.id for a in alerts(db_session)] == [first]


def test_alerts_belong_to_the_event_user(
    db_session: Session, bank: MockBankAccountProvider
) -> None:
    run(db_session, created("evt_1", "c_1", user="user_b"), bank)

    assert alerts(db_session) == []
    assert len(alerts(db_session, "user_b")) == 1
    assert check_user_invariants(db_session, "user_b") == []
