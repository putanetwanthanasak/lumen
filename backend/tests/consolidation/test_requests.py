"""CO-02, CO-06 to CO-14: POST /consolidation/requests and the approval (L70, L71, L72).

The eligible setup: income 30,000.00 and budget 9,000.00 (the default profile), with
auto-save off, and two manual entries of 6,000.00 and 4,000.00 a month for 3 months
from 2026-11. That is 10,000.00 a month, 3 months over budget. Paying both off takes
30,000.00, which at the example 18% a year over 24 months is 1,497.73 a month,
35,945.52 in all. "Today" is 2026-11-10 (the `co` fixture). The concurrent cases
are in tests/concurrency/test_consolidation_concurrency.py.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.affordability.months import Month
from app.assistant import service as assistant_service
from app.assistant.plan import remaining_for_payoff
from app.config import get_settings
from app.consolidation import service
from app.consolidation.schemas import MOCK_NOTE, ConsolidationRequestIn
from app.db import Base
from app.ledger import reconcile
from app.models import (
    AuditLog,
    ConsolidationPayout,
    ConsolidationRequest,
    Installment,
    Notification,
    SavingsTransaction,
    UserSettings,
)
from app.notifications.copy import CONSOLIDATION_BODY, CONSOLIDATION_TITLE
from app.providers.base import Application, Decision
from app.providers.mock_consolidation import MockConsolidationBank
from tests.consolidation.conftest import TODAY, Co
from tests.db.factories import installment, manual_installment, profile
from tests.user_settings.conftest import USER

pytestmark = pytest.mark.db


def configure(co: Co, user: str = USER) -> None:
    co.api.session.add(UserSettings(user_id=user, auto_save_enabled=False, **profile()))
    co.api.session.flush()


def manual(co: Co, monthly: str, months: int = 3, user: str = USER) -> uuid.UUID:
    row = manual_installment(
        user_id=user,
        client_request_id=str(uuid.uuid4()),
        principal=Decimal(monthly) * months,
        monthly_amount=Decimal(monthly),
        months=months,
        first_due_date=date(2026, 11, 1),
    )
    co.api.session.add(row)
    co.api.session.flush()
    return row.id


def eligible(co: Co) -> tuple[uuid.UUID, uuid.UUID]:
    configure(co)
    return manual(co, "6000.00"), manual(co, "4000.00")


def body(
    ids: tuple[uuid.UUID, ...], amounts: tuple[str, ...] = ("18000.00", "12000.00"), **extra: Any
) -> dict[str, Any]:
    return {
        "client_request_id": "req-1",
        "consent": True,
        "payoffs": [
            {"installment_id": str(i), "payoff_amount": a}
            for i, a in zip(ids, amounts, strict=True)
        ],
    } | extra


def submit(co: Co, data: Any, user: str | None = USER) -> Any:
    return co.api.call("POST", "/consolidation/requests", data, user=user)


def payout_out(co: Co, installment_id: uuid.UUID, amount: str) -> dict[str, str]:
    row = co.api.session.get_one(Installment, installment_id)
    return {
        "installment_id": str(installment_id),
        "vendor": row.vendor,
        "contract_id": row.contract_id,
        "amount": amount,
    }


def count(session: Session, model: Any) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def statuses(co: Co) -> dict[uuid.UUID, str]:
    co.api.session.expire_all()
    rows = co.api.session.execute(select(Installment.id, Installment.status)).all()
    return dict(rows)  # type: ignore[arg-type]


def audits(co: Co, action: str) -> list[AuditLog]:
    return list(co.api.session.execute(select(AuditLog).where(AuditLog.action == action)).scalars())


def row_counts(co: Co) -> dict[str, int]:
    return {t.name: count(co.api.session, t) for t in Base.metadata.sorted_tables}


# --- CO-08: approval, and a sequential double submit -------------------------------


def test_CO_08_approval_returns_the_loan_and_one_payout_per_installment(co: Co) -> None:
    a, b = eligible(co)

    response = submit(co, body((a, b)))

    assert response.status_code == 201, response.text
    data = response.json()
    loan_id = data["loan"]["installment_id"]
    assert data == {
        "request_id": data["request_id"],
        "client_request_id": "req-1",
        "status": "created",
        "decision": "approved",
        "mock": True,
        "note": MOCK_NOTE,
        "loan": {
            "installment_id": loan_id,
            "principal": "30000.00",
            "annual_rate": "0.18",
            "rate_is_example": True,
            "term_months": 24,
            "first_due_month": "2026-12",
            "monthly_payment": "1497.73",
            "total_cost": "35945.52",
        },
        "payouts": sorted(
            [payout_out(co, a, "18000.00"), payout_out(co, b, "12000.00")],
            key=lambda p: p["installment_id"],
        ),
        "monthly_total": "1497.73",  # L43: the loan, not what it replaced
    }
    # The Ledger: the loan, and the two paid-off rows kept with their history.
    assert statuses(co) == {a: "consolidated", b: "consolidated", uuid.UUID(loan_id): "active"}
    loan = co.api.session.get_one(Installment, uuid.UUID(loan_id))
    assert (loan.kind, loan.vendor, loan.months, loan.monthly_amount, loan.fee_total) == (
        "consolidation_loan",
        "consolidation",
        24,
        Decimal("1497.73"),
        Decimal("5945.52"),
    )
    assert (loan.first_due_date, loan.min_payment, loan.monthly_rate, loan.late_fee_per_period) == (
        date(2026, 12, 1),
        Decimal("1497.73"),
        Decimal("0.015000"),
        None,
    )
    # The mock bank paid each platform once.
    assert sorted(p.amount for p in co.bank.payouts) == [Decimal("12000.00"), Decimal("18000.00")]
    [entry] = audits(co, "consolidation_approved")
    assert entry.detail["principal"] == "30000.00"
    assert reconcile.check_user_invariants(co.api.session, USER) == []


def test_CO_08_double_submit_approves_once_and_answers_the_same(co: Co) -> None:
    a, b = eligible(co)

    first = submit(co, body((a, b)))
    counts = row_counts(co)
    second = submit(co, body((a, b)))

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json() | {"status": "duplicate"}
    assert row_counts(co) == counts  # nothing new written
    assert count(co.api.session, ConsolidationRequest) == 1
    assert len(co.bank.payouts) == 2  # paid once, the repeat paid nothing more


def test_CO_08_approval_saves_nothing(co: Co) -> None:
    """L72: the loan never triggers saving, even with auto-save on. 1% of 30,000.00
    is 300.00, well inside the 10,000.00 balance, so only the kind rule can stop it,
    not the safety net (B89 blind spot: 100% was stopped by the safety net)."""
    a, b = eligible(co)
    settings = co.api.session.get_one(UserSettings, USER)
    settings.auto_save_enabled, settings.consent_at = True, datetime(2026, 10, 1, tzinfo=UTC)
    settings.saving_percent = 1
    co.api.session.flush()
    bank_before = co.api.bank.get_balance(USER)

    assert submit(co, body((a, b))).status_code == 201

    assert count(co.api.session, SavingsTransaction) == 0
    assert co.api.bank.get_balance(USER) == bank_before


def test_CO_08_approval_stores_the_alert_in_your_wording(co: Co) -> None:
    a, b = eligible(co)

    loan_id = submit(co, body((a, b))).json()["loan"]["installment_id"]

    alert = co.api.session.execute(
        select(Notification).where(Notification.kind == "consolidation_loan")
    ).scalar_one()
    assert str(alert.installment_id) == loan_id
    assert alert.title == "อนุมัติสินเชื่อรวมหนี้แล้ว" == CONSOLIDATION_TITLE
    assert alert.body == (
        "ผ่อนเดือนละ 1,497.73 บาท 24 เดือน ยอดรวมทั้งหมด 35,945.52 บาท ค่างวดรวมต่อเดือนตอนนี้ 1,497.73 บาท"
    )
    assert "—" not in CONSOLIDATION_TITLE + CONSOLIDATION_BODY  # rule 10
    assert alert.delivery_status == "pushed"
    assert [(p.user_id, p.title, p.body) for p in co.api.push.attempts] == [
        (USER, alert.title, alert.body)
    ]


# --- CO-02: the loan counts in the plan; the paid-off rows do not -------------------


def test_CO_02_after_approval_the_plan_shows_the_loan_and_no_run(co: Co) -> None:
    a, b = eligible(co)
    assert submit(co, body((a, b))).status_code == 201

    plan = co.api.call("GET", "/assistant/plan").json()

    assert [m["total"] for m in plan["months"][:3]] == ["0.00", "1497.73", "1497.73"]
    assert len(plan["months"]) == 25  # November, then the 24 months of the loan
    assert plan["back_in_budget_month"] is None
    assert plan["consolidation"]["reason"] == "NOT_NEEDED"
    preview = co.api.call(
        "POST",
        "/installments/preview",
        {
            "client_request_id": "req-p",
            "kind": "purchase",
            "item_price": "100.00",
            "months": 1,
            "monthly_amount": "100.00",
            "first_due_month": "2026-12",
        },
    ).json()
    assert preview["months"] == [
        {"month": "2026-12", "total": "1597.73", "over_budget": False, "over_one_third": False}
    ]


def test_CO_02_not_me_on_the_approved_loan_is_refused(co: Co) -> None:
    a, b = eligible(co)
    loan_id = submit(co, body((a, b))).json()["loan"]["installment_id"]

    response = co.api.call("POST", f"/debts/{loan_id}/not-me")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NOT_ME_UNAVAILABLE_FOR_CONSOLIDATION_LOAN"


# --- CO-06: the body -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "loc"),
    [
        ({"consent": False}, ["consent"]),
        ({"consent": "true"}, ["consent"]),
        ({"consent": 1}, ["consent"]),  # bug found: Literal[True] took 1 and 1.0
        ({"consent": 1.0}, ["consent"]),
        ({"consent": None}, ["consent"]),
        ({"payoffs": []}, ["payoffs"]),
        ({"extra": 1}, ["extra"]),
        ({"client_request_id": ""}, ["client_request_id"]),
    ],
)
def test_CO_06_invalid_bodies_are_422_and_write_nothing(
    co: Co, change: dict[str, Any], loc: list[str]
) -> None:
    a, b = eligible(co)
    before = row_counts(co)

    response = submit(co, body((a, b)) | change)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == loc
    assert row_counts(co) == before
    assert co.bank.payouts == []


def test_CO_06_missing_consent_is_422(co: Co) -> None:
    a, b = eligible(co)
    data = body((a, b))
    del data["consent"]

    response = submit(co, data)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["consent"]


@pytest.mark.parametrize(
    "payoff",
    [
        {"payoff_amount": "12000.001"},  # L49: never rounded
        {"payoff_amount": "0.00"},
        {"payoff_amount": "-1.00"},
    ],
)
def test_CO_06_payoff_amounts_follow_the_money_rules(co: Co, payoff: dict[str, str]) -> None:
    a, b = eligible(co)
    data = body((a, b))
    data["payoffs"][1] |= payoff

    assert submit(co, data).status_code == 422


def test_CO_06_a_json_number_payoff_is_422(co: Co) -> None:
    a, b = eligible(co)
    raw = (
        '{"client_request_id": "req-1", "consent": true, "payoffs": ['
        f'{{"installment_id": "{a}", "payoff_amount": 18000.00}},'
        f'{{"installment_id": "{b}", "payoff_amount": "12000.00"}}]}}'
    ).encode()

    assert submit(co, raw).status_code == 422


def test_CO_06_the_same_installment_twice_is_422(co: Co) -> None:
    a, _ = eligible(co)

    assert submit(co, body((a, a))).status_code == 422


def test_CO_06_no_user_header_is_401(co: Co) -> None:
    a, b = eligible(co)

    assert submit(co, body((a, b)), user=None).status_code == 401


def test_CO_06_no_settings_is_409_settings_required(co: Co) -> None:
    a, b = manual(co, "6000.00"), manual(co, "4000.00")

    response = submit(co, body((a, b)))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SETTINGS_REQUIRED"


# --- CO-07: not eligible -------------------------------------------------------------


def not_eligible(reason: str) -> dict[str, Any]:
    return {
        "detail": {
            "code": "NOT_ELIGIBLE",
            "message": "consolidation is not available now",
            "reason": reason,
        }
    }


def test_CO_07_two_months_over_budget_is_409_not_needed_and_changes_nothing(co: Co) -> None:
    configure(co)
    a, b = manual(co, "6000.00", 2), manual(co, "4000.00", 2)
    before = statuses(co)

    response = submit(co, body((a, b)))

    assert response.status_code == 409
    assert response.json() == not_eligible("NOT_NEEDED")
    assert statuses(co) == before
    assert count(co.api.session, ConsolidationRequest) == 0
    assert count(co.api.session, ConsolidationPayout) == 0
    assert co.bank.payouts == []
    [entry] = audits(co, "consolidation_not_eligible")
    assert entry.detail == {"client_request_id": "req-1", "reason": "NOT_NEEDED"}


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"overdue_days": 10}, "OVERDUE_DEBT"),
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
def test_CO_07_an_overdue_or_disputed_debt_is_409(
    co: Co, fields: dict[str, Any], reason: str
) -> None:
    a, b = eligible(co)
    extra = installment(user_id=USER, contract_id="c-x", **fields)
    co.api.session.add(extra)
    co.api.session.flush()

    response = submit(co, body((a, b, extra.id), ("18000.00", "12000.00", "2000.00")))

    assert response.json() == not_eligible(reason)
    assert count(co.api.session, ConsolidationRequest) == 0


@pytest.mark.parametrize("which", ["missing", "extra", "other_user"])
def test_CO_07_payoffs_that_do_not_match_the_counted_set_are_409(co: Co, which: str) -> None:
    a, b = eligible(co)
    configure(co, "someone_else")
    other = manual(co, "1000.00", user="someone_else")
    ids, amounts = {
        "missing": ((a,), ("18000.00",)),
        "extra": ((a, b, uuid.uuid4()), ("18000.00", "12000.00", "1.00")),
        "other_user": ((a, b, other), ("18000.00", "12000.00", "3000.00")),
    }[which]
    before = statuses(co)

    response = submit(co, body(ids, amounts))

    assert response.json() == not_eligible("PAYOFFS_DO_NOT_MATCH_PLAN")
    assert statuses(co) == before
    assert co.bank.payouts == []


def test_CO_07_once_eligible_the_same_id_can_be_used(co: Co) -> None:
    """A refusal stores no request row (open question 9), so the id is free."""
    configure(co)
    a, b = manual(co, "6000.00", 2), manual(co, "4000.00", 2)
    assert submit(co, body((a, b), ("12000.00", "8000.00"))).status_code == 409
    # 9,500.00 for 3 months: 19,500.00, 19,500.00 and 9,500.00, all over 9,000.00.
    c = manual(co, "9500.00", 3)

    response = submit(co, body((a, b, c), ("12000.00", "8000.00", "28500.00")))

    assert response.status_code == 201


# --- CO-10: the same id with other payoffs -------------------------------------------


def test_CO_10_same_id_with_other_payoffs_is_409_and_audited(co: Co) -> None:
    a, b = eligible(co)
    assert submit(co, body((a, b))).status_code == 201

    response = submit(co, body((a, b), ("18000.00", "12000.01")))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CLIENT_REQUEST_ID_REUSED"
    assert len(audits(co, "client_request_id_reused")) == 1
    assert count(co.api.session, ConsolidationRequest) == 1


# --- CO-11: decline ------------------------------------------------------------------


def test_CO_11_decline_changes_nothing_but_the_request_record_and_the_audit(co: Co) -> None:
    a, b = eligible(co)
    co.use_bank(MockConsolidationBank("decline"))
    before = row_counts(co)

    response = submit(co, body((a, b)))

    assert response.status_code == 201
    data = response.json()
    assert (data["decision"], data["loan"], data["payouts"], data["monthly_total"]) == (
        "declined",
        None,
        [],
        "10000.00",
    )
    after = row_counts(co)
    assert {t: after[t] - before[t] for t in after if after[t] != before[t]} == {
        "consolidation_requests": 1,
        "audit_log": 1,
    }
    assert statuses(co) == {a: "active", b: "active"}
    assert co.api.session.execute(select(ConsolidationRequest.status)).scalar_one() == "declined"
    assert len(audits(co, "consolidation_declined")) == 1
    assert co.bank.payouts == []
    assert co.api.push.attempts == []


def test_CO_11_a_resend_of_a_declined_request_is_declined_again(co: Co) -> None:
    a, b = eligible(co)
    co.use_bank(MockConsolidationBank("decline"))
    first = submit(co, body((a, b)))
    co.use_bank(MockConsolidationBank("approve"))  # the bank's answer for this id stands

    second = submit(co, body((a, b)))

    assert second.status_code == 200
    assert second.json() == first.json() | {"status": "duplicate"}
    assert statuses(co) == {a: "active", b: "active"}


def test_CO_11_the_mock_decision_comes_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import providers

    monkeypatch.setenv("CONSOLIDATION_MOCK_DECISION", "decline")
    get_settings.cache_clear()
    providers.get_consolidation_bank.cache_clear()
    try:
        bank = providers.get_consolidation_bank()
        decision = bank.decide(Application(USER, "ref", (), Decimal("0.18"), 24))
        assert decision == Decision(approved=False, payoffs=(), reference=decision.reference)
    finally:
        monkeypatch.delenv("CONSOLIDATION_MOCK_DECISION")
        get_settings.cache_clear()
        providers.get_consolidation_bank.cache_clear()
    assert get_settings().consolidation_mock_decision == "approve"  # the default


# --- CO-12: approval is one transaction ------------------------------------------------


def test_CO_12_if_creating_the_loan_fails_nothing_is_consolidated_or_paid(
    co: Co, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = eligible(co)
    session = co.api.session
    session.commit()  # the setup is the state to return to (a savepoint in tests)
    before = row_counts(co)

    def broken_loan(*args: Any, **kwargs: Any) -> Installment:
        raise RuntimeError("loan insert failed")

    monkeypatch.setattr(service, "create_loan", broken_loan)
    with pytest.raises(RuntimeError, match="loan insert failed"):
        service.submit(
            session,
            user_id=USER,
            body=ConsolidationRequestIn.model_validate_json(_json(body((a, b)))),
            today=TODAY,
            settings=get_settings(),
            bank=co.bank,
        )
    session.rollback()

    assert statuses(co) == {a: "active", b: "active"}
    assert row_counts(co) == before
    assert co.bank.payouts == []
    monkeypatch.undo()
    # The client's retry, with the same id, is decided normally.
    assert submit(co, body((a, b))).status_code == 201


def _json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data)


# --- CO-13: payout keys and a payout that fails after the commit --------------------


def test_CO_13_payout_keys_come_from_user_request_and_installment() -> None:
    i, j = uuid.uuid4(), uuid.uuid4()

    assert service.payout_key("u", "r", i) == service.payout_key("u", "r", i)
    keys = {
        service.payout_key("u", "r", i),
        service.payout_key("u", "r", j),
        service.payout_key("u", "r2", i),
        service.payout_key("u2", "r", i),
    }
    assert len(keys) == 4


class FailsOnce(MockConsolidationBank):
    """The platform payout fails once, after the approval has committed."""

    def __init__(self) -> None:
        super().__init__("approve")
        self.failed = False

    def pay_out(
        self, *, vendor: str, contract_id: str, amount: Decimal, idempotency_key: str
    ) -> None:
        if not self.failed:
            self.failed = True
            raise ConnectionError("platform payout API down")
        super().pay_out(
            vendor=vendor, contract_id=contract_id, amount=amount, idempotency_key=idempotency_key
        )


def test_CO_13_a_payout_failing_after_commit_is_completed_by_the_retry_once(co: Co) -> None:
    a, b = eligible(co)
    bank = FailsOnce()
    co.use_bank(bank)

    co.api.session.commit()  # the setup survives the rollback below
    with pytest.raises(ConnectionError):
        submit(co, body((a, b)))
    # The failed request's session closes, which rolls back anything not committed
    # (get_session). The shared test session must do the same, or a payout made
    # before the commit would look committed (B92 blind spot).
    co.api.session.rollback()
    # The approval committed before the payouts: the Ledger already shows it.
    assert count(co.api.session, ConsolidationRequest) == 1
    assert len(bank.payouts) == 0

    retry = submit(co, body((a, b)))
    again = submit(co, body((a, b)))

    assert (retry.status_code, again.status_code) == (200, 200)
    assert sorted(p.amount for p in bank.payouts) == [Decimal("12000.00"), Decimal("18000.00")]
    stored = co.api.session.execute(select(ConsolidationPayout.idempotency_key)).scalars()
    assert set(stored) == {service.payout_key(USER, "req-1", i) for i in (a, b)}
    # The loan's alert still goes out once (review F1): delivery comes before the payouts.
    alert = co.api.session.execute(select(Notification)).scalar_one()
    assert alert.delivery_status == "pushed"
    assert [p.title for p in co.api.push.attempts] == [CONSOLIDATION_TITLE]


# --- CO-14: reconcile ------------------------------------------------------------------


def test_CO_14_reconcile_catches_a_consolidated_row_without_a_payout(co: Co) -> None:
    co.api.session.add(installment(user_id=USER, contract_id="c-y", status="consolidated"))
    co.api.session.flush()

    assert reconcile.check_user_invariants(co.api.session, USER) == ["L72"]


@pytest.mark.parametrize("break_it", ["loan_principal", "payout_reopened"])
def test_CO_14_reconcile_catches_an_approval_that_does_not_add_up(co: Co, break_it: str) -> None:
    a, b = eligible(co)
    loan_id = uuid.UUID(submit(co, body((a, b))).json()["loan"]["installment_id"])
    session = co.api.session
    assert reconcile.check_user_invariants(session, USER) == []

    if break_it == "loan_principal":
        session.get_one(Installment, loan_id).principal = Decimal("29999.99")
    else:
        session.get_one(Installment, a).status = "active"
    session.flush()

    assert reconcile.check_user_invariants(session, USER) == ["L72"]


def test_CO_14_reconcile_catches_payouts_that_do_not_add_up_to_the_loan(
    owner_session: Session,
) -> None:
    """The app role cannot UPDATE a payout (append-only), so the owner breaks one."""
    session = owner_session
    session.add(UserSettings(user_id=USER, auto_save_enabled=False, **profile()))
    a, b = (
        manual_installment(
            user_id=USER,
            client_request_id=f"req-{monthly}",
            principal=Decimal(monthly) * 3,
            monthly_amount=Decimal(monthly),
            months=3,
            first_due_date=date(2026, 11, 1),
        )
        for monthly in ("6000.00", "4000.00")
    )
    session.add_all([a, b])
    session.flush()
    result = service.submit(
        session,
        user_id=USER,
        body=ConsolidationRequestIn.model_validate_json(_json(body((a.id, b.id)))),
        today=TODAY,
        settings=get_settings(),
        bank=MockConsolidationBank(),
    )
    assert isinstance(result, service.Decided)
    assert reconcile.check_user_invariants(session, USER) == []

    result.payouts[0].amount -= Decimal("0.01")
    session.flush()

    assert reconcile.check_user_invariants(session, USER) == ["L72"]


# --- CO-06 and CO-07: the amounts in the request --------------------------------------


def test_CO_06_payoffs_that_sum_beyond_numeric_12_2_are_422(co: Co) -> None:
    a, b = eligible(co)

    response = submit(co, body((a, b), ("5000000000.00", "5000000000.00")))

    assert response.status_code == 422
    assert count(co.api.session, ConsolidationRequest) == 0


@pytest.mark.parametrize(
    ("amounts", "reason"),
    [
        # 300,000.00 over 24 months at 18% is 14,977.24 a month, above the 9,000.00
        # budget: the plan's own estimate (30,000.00) was within it.
        (("180000.00", "120000.00"), "PAYMENT_ABOVE_BUDGET"),
        # Within Numeric(12,2), but the total cost of the loan is not.
        (("5000000000.00", "4999999999.99"), "ESTIMATE_TOO_LARGE"),
    ],
)
def test_CO_07_l70_b_is_checked_again_on_the_amounts_requested(
    co: Co, amounts: tuple[str, str], reason: str
) -> None:
    a, b = eligible(co)

    response = submit(co, body((a, b), amounts))

    assert response.json() == not_eligible(reason)
    assert statuses(co) == {a: "active", b: "active"}
    assert count(co.api.session, ConsolidationRequest) == 0
    assert co.bank.payouts == []


def test_CO_07_requested_amounts_within_budget_are_approved_as_given(co: Co) -> None:
    """The mock bank takes the user's figures (open question 6): 90,000.00 is
    4,493.17 a month (4,493.1692 rounded up), within budget, though above the plan's
    own estimate."""
    a, b = eligible(co)

    loan = submit(co, body((a, b), ("54000.00", "36000.00"))).json()["loan"]

    assert (loan["principal"], loan["monthly_payment"]) == ("90000.00", "4493.17")


# --- CO-12 and CO-14: an approval that fails reconcile is rolled back ---------------


def test_CO_14_an_approval_that_breaks_l72_is_rolled_back_not_committed(
    co: Co, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = eligible(co)
    co.api.session.commit()  # keep the setup when the service rolls back
    before = row_counts(co)
    create_loan = service.create_loan

    def loan_off_by_a_satang(*args: Any, **kwargs: Any) -> Installment:
        loan = create_loan(*args, **kwargs)
        loan.principal += Decimal("0.01")
        return loan

    monkeypatch.setattr(service, "create_loan", loan_off_by_a_satang)

    with pytest.raises(reconcile.InvariantViolationError, match="L72"):
        submit(co, body((a, b)))

    assert statuses(co) == {a: "active", b: "active"}
    assert row_counts(co) == before
    assert co.bank.payouts == []


# --- Guards that the locks make unreachable --------------------------------------------


def test_CO_12_marking_an_installment_no_longer_owed_raises(co: Co) -> None:
    a, _ = eligible(co)
    paid = manual(co, "100.00", 1)
    co.api.session.get_one(Installment, paid).status = "cancelled"
    co.api.session.flush()

    with pytest.raises(RuntimeError, match="changed under the consolidation lock"):
        service._mark_consolidated(co.api.session, USER, [a, paid])


def test_CO_08_storing_the_same_request_twice_raises(co: Co) -> None:
    configure(co)
    request_body = ConsolidationRequestIn.model_validate_json(
        _json(body((uuid.uuid4(),), ("1.00",)))
    )

    def store() -> ConsolidationRequest:
        return service._store_request(
            co.api.session,
            request_id=uuid.uuid4(),
            user_id=USER,
            body=request_body,
            approved=False,
            principal=Decimal("1.00"),
            rate=Decimal("0"),
            term=1,
            payment=Decimal("1.00"),
            decision_reference="MOCK-test",
            loan_id=None,
        )

    store()
    with pytest.raises(RuntimeError, match="decided concurrently"):
        store()


# --- Review round 1 (PR C) --------------------------------------------------------------


def test_CO_02_the_loan_is_valued_like_a_manual_row_in_later_plans(co: Co) -> None:
    """The loan gets no payments (no platform reports them), so its earlier months are
    taken as paid, as for a manual row (open question 2), never its whole total cost
    for ever (review F2). It runs 2026-12 to 2028-11 at 1,497.73."""
    a, b = eligible(co)
    loan_id = uuid.UUID(submit(co, body((a, b))).json()["loan"]["installment_id"])
    loan = co.api.session.get_one(Installment, loan_id)
    debt = assistant_service.debt_of(loan)

    assert remaining_for_payoff(debt, Month.of(date(2026, 11, 10))) == Decimal("35945.52")
    assert remaining_for_payoff(debt, Month.of(date(2028, 10, 10))) == Decimal("2995.46")
    assert remaining_for_payoff(debt, Month.of(date(2028, 12, 10))) == Decimal("0.00")


def test_CO_07_an_ended_row_with_nothing_left_is_not_named(co: Co) -> None:
    """Open question 5: the payoffs name the counted installments with something left.
    A manual row that ended in October is still in the L43 set (no payments recorded)
    but has nothing left to pay off: it is not named and not paid (review F4)."""
    a, b = eligible(co)
    ended = manual_installment(
        user_id=USER,
        client_request_id="req-ended",
        principal=Decimal("300.00"),
        monthly_amount=Decimal("100.00"),
        months=3,
        first_due_date=date(2026, 8, 1),
    )
    co.api.session.add(ended)
    co.api.session.flush()

    named = submit(
        co, body((a, b, ended.id), ("18000.00", "12000.00", "0.01"), client_request_id="req-0")
    )
    response = submit(co, body((a, b)))

    assert named.json() == not_eligible("PAYOFFS_DO_NOT_MATCH_PLAN")
    assert response.status_code == 201
    assert statuses(co)[ended.id] == "active"
    assert len(co.bank.payouts) == 2
