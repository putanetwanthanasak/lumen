"""L42 "Not me" over HTTP: POST /debts/{installment_id}/not-me (05 NT-05; L59 3).

Disputed: status `disputed` with `disputed_at`, one audit row, the alert marked
not_me, one platform signal after commit, and mock contact data. Only the owner may
dispute; anyone else gets the same 404 as an unknown id.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger.reconcile import check_user_invariants
from app.models import AuditLog, Installment, Notification
from app.providers.mock_platform import DisputeSignal
from tests.webhooks.conftest import Webhook
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db

NOT_FOUND = {"detail": "installment not found"}
MESSAGE = (
    "บันทึกแล้วว่ารายการนี้ไม่ใช่คุณ และส่งเรื่องให้ ShopDemo ตรวจสอบแล้ว "
    "Lumen หยุดหรือยกเลิกรายการแทนไม่ได้ กรุณาติดต่อ ShopDemo โดยตรงตามช่องทางด้านล่าง"
)
CONTACT = {
    "mock": True,
    "label": "MOCK DATA for the Lumen prototype. Not a real contact channel.",
    "vendor": "ShopDemo",
    "phone": "000-000-0000",
    "url": "https://help.shopdemo.example/report",
    "hours": "ทุกวัน 09:00-18:00 (mock)",
}


def open_debt(webhook: Webhook, **contract: Any) -> uuid.UUID:
    data = payload()
    data["contract"] |= contract
    assert webhook.post(data).status_code == 200
    return installment(webhook.session).id


def installment(session: Session) -> Installment:
    session.expire_all()
    return session.execute(select(Installment)).scalar_one()


def dispute_audits(session: Session) -> list[AuditLog]:
    return list(
        session.execute(select(AuditLog).where(AuditLog.action == "installment_disputed")).scalars()
    )


def audit_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(AuditLog)).scalar_one()


def event(event_type: str, event_id: str, **fields: Any) -> dict[str, Any]:
    return payload(event_type, event_id=event_id, occurred_at="2026-10-12T11:00:00Z", **fields)


def test_NT_05_not_me_disputes_audits_signals_and_returns_contact(webhook: Webhook) -> None:
    installment_id = open_debt(webhook)

    response = webhook.not_me(installment_id)

    assert response.status_code == 200, response.text
    body = response.json()
    inst = installment(webhook.session)
    assert (inst.status, inst.disputed_at is not None) == ("disputed", True)
    assert body == {
        "installment_id": str(installment_id),
        "status": "disputed",
        "disputed_at": body["disputed_at"],
        "message": MESSAGE,
        "contact": CONTACT,
    }
    assert body["disputed_at"] == inst.disputed_at.isoformat().replace("+00:00", "Z")
    [entry] = dispute_audits(webhook.session)
    assert (entry.actor, entry.user_id, entry.ref_type, entry.ref_id) == (
        "user",
        "user_a",
        "installment",
        str(installment_id),
    )
    assert entry.detail == {
        "vendor": "shopdemo",
        "contract_id": "ctr_88213",
        "previous_status": "active",
    }
    assert webhook.platform.signals == [DisputeSignal("shopdemo", "ctr_88213", "user_a")]
    alert = webhook.session.execute(select(Notification)).scalar_one()
    assert alert.user_response == "not_me"
    assert check_user_invariants(webhook.session, "user_a") == []


def test_L42_never_claims_the_platform_transaction_is_stopped(webhook: Webhook) -> None:
    body = webhook.not_me(open_debt(webhook)).json()

    assert "หยุดหรือยกเลิกรายการแทนไม่ได้" in body["message"]  # "cannot stop or cancel it"
    assert body["contact"]["mock"] is True
    assert "MOCK DATA" in body["contact"]["label"]
    assert ".example/" in body["contact"]["url"]  # a reserved, never-real domain


def test_not_me_twice_is_idempotent(webhook: Webhook) -> None:
    installment_id = open_debt(webhook)
    first = webhook.not_me(installment_id)
    audits = audit_count(webhook.session)

    repeats = [webhook.not_me(installment_id) for _ in range(3)]

    assert [(r.status_code, r.json()) for r in repeats] == [(200, first.json())] * 3
    assert len(dispute_audits(webhook.session)) == 1
    assert audit_count(webhook.session) == audits
    assert len(webhook.platform.signals) == 1


@pytest.mark.parametrize(
    "target",
    [
        "other_user",
        "unknown_id",
        "not_a_uuid",
    ],
)
def test_L42_only_the_owner_can_dispute_others_get_the_same_404(
    webhook: Webhook, target: str
) -> None:
    installment_id = open_debt(webhook)
    path_id: object = {
        "other_user": installment_id,
        "unknown_id": uuid.uuid4(),
        "not_a_uuid": "x' OR '1'='1",
    }[target]
    user = "user_b" if target == "other_user" else "user_a"
    audits = audit_count(webhook.session)

    response = webhook.not_me(path_id, user)

    assert (response.status_code, response.json()) == (404, NOT_FOUND)
    inst = installment(webhook.session)
    assert (inst.status, inst.disputed_at) == ("active", None)
    assert audit_count(webhook.session) == audits
    assert webhook.platform.signals == []


@pytest.mark.parametrize("user", [None, "", "user\x00a"], ids=["none", "empty", "nul"])
def test_not_me_without_a_valid_demo_user_is_401(webhook: Webhook, user: str | None) -> None:
    response = webhook.not_me(open_debt(webhook), user)

    assert (response.status_code, response.json()) == (401, {"detail": "unauthorized"})
    assert installment(webhook.session).disputed_at is None


def test_L59_3_cancel_after_dispute_keeps_the_dispute_history(webhook: Webhook) -> None:
    installment_id = open_debt(webhook)
    disputed_at = webhook.not_me(installment_id).json()["disputed_at"]

    cancel = event("installment_cancelled", "evt_x")
    assert webhook.post(cancel).json() == {"status": "processed"}

    inst = installment(webhook.session)
    assert inst.status == "cancelled"
    assert inst.disputed_at is not None
    assert inst.disputed_at.isoformat().replace("+00:00", "Z") == disputed_at
    assert len(dispute_audits(webhook.session)) == 1
    # The UI can say "cancelled after you reported it".
    [line] = webhook.get("/debts/summary").json()["installments"]
    assert (line["status"], line["disputed_at"]) == ("cancelled", disputed_at)
    # And a repeat of "Not me" now answers with the cancelled status, still once.
    again = webhook.not_me(installment_id).json()
    assert (again["status"], again["disputed_at"]) == ("cancelled", disputed_at)
    assert len(webhook.platform.signals) == 1


def test_not_me_on_a_cancelled_debt_records_the_report_status_stays_cancelled(
    webhook: Webhook,
) -> None:
    """Agreed answer (Session 9 plan, 2): the debt is not owed, but the report is kept."""
    installment_id = open_debt(webhook)
    webhook.post(event("installment_cancelled", "evt_x"))

    body = webhook.not_me(installment_id).json()

    inst = installment(webhook.session)
    assert (body["status"], inst.status, inst.disputed_at is not None) == (
        "cancelled",
        "cancelled",
        True,
    )
    [entry] = dispute_audits(webhook.session)
    assert entry.detail["previous_status"] == "cancelled"
    assert len(webhook.platform.signals) == 1


def test_not_me_on_a_paid_off_debt_disputes_it(webhook: Webhook) -> None:
    installment_id = open_debt(webhook, principal="100.00")
    webhook.post(event("installment_payment_collected", "evt_p", amount="100.00"))
    assert installment(webhook.session).status == "paid_off"

    assert webhook.not_me(installment_id).json()["status"] == "disputed"
    assert dispute_audits(webhook.session)[0].detail["previous_status"] == "paid_off"


@pytest.mark.parametrize(
    ("data", "paid", "late_fees"),
    [
        (event("installment_payment_collected", "evt_p", amount="20000.00"), "20000.00", "0.00"),
        (event("installment_overdue", "evt_o", late_fees_accrued="50.00"), "0.00", "50.00"),
    ],
    ids=["payment_in_full", "late_fee"],
)
def test_settle_never_changes_disputed(
    webhook: Webhook, data: dict[str, Any], paid: str, late_fees: str
) -> None:
    """Events on a disputed debt are still recorded (money the platform reports), but
    only a cancel moves it out of disputed."""
    webhook.not_me(open_debt(webhook))

    assert webhook.post(data).json() == {"status": "processed"}

    inst = installment(webhook.session)
    assert (str(inst.paid_amount), str(inst.late_fees_accrued), inst.status) == (
        paid,
        late_fees,
        "disputed",
    )
    assert check_user_invariants(webhook.session, "user_a") == []


def test_platform_signal_failure_still_records_the_dispute(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(**_: object) -> None:
        raise ConnectionError("platform down")

    monkeypatch.setattr(webhook.platform, "signal_dispute", down)

    response = webhook.not_me(open_debt(webhook))

    assert response.status_code == 200
    assert installment(webhook.session).status == "disputed"
    assert len(dispute_audits(webhook.session)) == 1
