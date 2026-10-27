"""CO-01 to CO-05: the consolidation loan kind and the consolidated status (L72).

The loan never saves, counts in every month total, and "Not me" is refused on it.
A consolidated installment is not owed, keeps its history, and keeps its status
whatever the platform sends later. Only an approved consolidation creates the kind;
that request is not built yet, so here the rows are written directly.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ledger import reconcile
from app.models import AuditLog, Installment, SavingsTransaction, UserBalance, UserSettings
from app.providers.mock_bank import MockBankAccountProvider
from app.rules.engine import FixedRule, PercentRule, compute_saving
from app.savings import service as savings
from tests.db.factories import consolidation_loan, installment, profile, savings_tx
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api
from tests.webhooks.conftest import Webhook
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db

REFUSED = {
    "detail": {
        "code": "NOT_ME_UNAVAILABLE_FOR_CONSOLIDATION_LOAN",
        "message": (
            "this is the consolidation loan you asked the bank for; "
            "there is no platform to report it to"
        ),
    }
}


def add_loan(session: Session, **overrides: Any) -> Installment:
    loan = consolidation_loan(user_id=USER, **overrides)
    session.add(loan)
    session.flush()
    return loan


# --- CO-01: the loan never saves ----------------------------------------------------


@pytest.mark.parametrize("rule", [PercentRule(100), FixedRule(Decimal("500.00"))])
def test_CO_01_engine_never_saves_on_a_consolidation_loan(rule: PercentRule | FixedRule) -> None:
    saving = compute_saving(
        kind="consolidation_loan",
        item_value=Decimal("17100.00"),
        bank_balance=Decimal("100000.00"),
        rule=rule,
        protected_min=Decimal("500.00"),
    )

    assert saving == Decimal("0.00")


def test_CO_01_auto_save_on_a_loan_records_nothing_and_moves_nothing(db_session: Session) -> None:
    # 1% of 17,100.00 is 171.00, well inside the 10,000.00 balance: only the kind
    # rule can stop this saving, not the 500.00 safety net (B78 blind spot).
    opt_in(db_session, percent=1)
    loan = add_loan(db_session)
    bank = MockBankAccountProvider()

    saved = savings.auto_save(
        db_session,
        user_id=USER,
        kind=loan.kind,
        item_price=loan.principal,
        installment_id=loan.id,
        source=None,
        bank=bank,
    )

    assert saved == Decimal("0.00")
    assert (
        db_session.execute(select(func.count()).select_from(SavingsTransaction)).scalar_one() == 0
    )
    assert bank.get_balance(USER) == Decimal("10000.00")


def test_CO_01_reconcile_flags_an_auto_save_on_a_loan_as_INV_5(db_session: Session) -> None:
    loan = add_loan(db_session)
    db_session.add(
        savings_tx(
            user_id=USER,
            amount=Decimal("10.00"),
            source_vendor=None,
            source_event_id=None,
            installment_id=loan.id,
        )
    )
    db_session.add(UserBalance(user_id=USER, savings_balance=Decimal("10.00")))
    db_session.flush()

    assert reconcile.check_user_invariants(db_session, USER) == ["INV-5"]


# --- CO-02: the loan counts; a consolidated installment does not -------------------


def test_CO_02_loan_counts_in_the_debt_summary_and_consolidated_rows_do_not(api: Api) -> None:
    add_loan(api.session)
    api.session.add(
        installment(user_id=USER, contract_id="c-old", status="consolidated")  # 500.00 x 4
    )
    api.session.flush()

    body = api.call("GET", "/debts/summary").json()

    assert body["monthly_total"] == "853.71"
    assert {(line["kind"], line["status"], line["owed"]) for line in body["installments"]} == {
        ("consolidation_loan", "active", True),
        ("purchase", "consolidated", False),
    }


def test_CO_02_loan_counts_in_the_preview_month_totals(api: Api) -> None:
    api.session.add(_settings())
    add_loan(api.session)
    api.session.add(installment(user_id=USER, contract_id="c-old", status="consolidated"))
    api.session.flush()
    entry = {
        "client_request_id": "req-1",
        "kind": "purchase",
        "item_price": "1000.00",
        "months": 2,
        "monthly_amount": "500.00",
        "first_due_month": "2026-11",
    }

    months = api.call("POST", "/installments/preview", entry).json()["months"]

    # November is before the loan's first due month; the consolidated row is gone.
    assert [(m["month"], m["total"]) for m in months] == [
        ("2026-11", "500.00"),
        ("2026-12", "1353.71"),
    ]


def _settings() -> UserSettings:
    return UserSettings(user_id=USER, auto_save_enabled=False, **profile())


# --- CO-03: "Not me" on the loan is refused -----------------------------------------


def test_CO_03_not_me_on_a_loan_is_409_and_changes_nothing(api: Api) -> None:
    loan = add_loan(api.session)

    responses = [api.call("POST", f"/debts/{loan.id}/not-me") for _ in range(3)]

    assert [r.status_code for r in responses] == [409, 409, 409]
    assert responses[0].json() == REFUSED
    api.session.expire_all()
    row = api.session.get(Installment, loan.id)
    assert row is not None
    assert (row.status, row.disputed_at, row.dispute_signal_status) == ("active", None, None)
    assert api.platform.signals == []
    audits = api.session.execute(
        select(AuditLog).where(AuditLog.action == "not_me_rejected_consolidation_loan")
    ).scalars()
    assert [(a.ref_id, a.actor) for a in audits] == [(str(loan.id), "user")] * 3


def test_CO_03_not_me_on_a_consolidated_debt_records_the_report_status_stays(
    webhook: Webhook,
) -> None:
    """Like a cancelled debt (L59 3): as `disputed` it would be owed again, and
    counted twice, in itself and in the loan."""
    assert webhook.post(payload()).status_code == 200
    webhook.session.execute(update(Installment).values(status="consolidated"))
    installment_id = webhook.session.execute(select(Installment.id)).scalar_one()

    body = webhook.not_me(installment_id).json()

    webhook.session.expire_all()
    row = webhook.session.get(Installment, installment_id)
    assert row is not None
    assert (body["status"], row.status, row.disputed_at is not None) == (
        "consolidated",
        "consolidated",
        True,
    )
    assert len(webhook.platform.signals) == 1
    assert webhook.get("/debts/summary").json()["monthly_total"] == "0.00"


# --- CO-04: platform events on a consolidated installment --------------------------


def _event(event_type: str, event_id: str, **fields: Any) -> dict[str, Any]:
    return payload(event_type, event_id=event_id, occurred_at="2026-10-12T11:00:00Z", **fields)


@pytest.mark.parametrize(
    ("event", "field", "value"),
    [
        (_event("installment_cancelled", "evt_c"), "status", "consolidated"),
        (
            _event("installment_payment_collected", "evt_p", amount="20000.00"),
            "paid_amount",
            Decimal("20000.00"),
        ),
        (_event("installment_overdue", "evt_o"), "late_fees_accrued", Decimal("100.00")),
    ],
)
def test_CO_04_platform_events_on_a_consolidated_debt_are_recorded_status_stays(
    webhook: Webhook, event: dict[str, Any], field: str, value: object
) -> None:
    assert webhook.post(payload()).status_code == 200
    webhook.session.execute(update(Installment).values(status="consolidated"))

    assert webhook.post(event).json() == {"status": "processed"}

    webhook.session.expire_all()
    row = webhook.session.execute(select(Installment)).scalar_one()
    assert row.status == "consolidated"
    assert getattr(row, field) == value


# --- CO-05: only a consolidation creates the kind; the DB pins it ------------------


def test_CO_05_manual_entry_cannot_record_a_consolidation_loan(api: Api) -> None:
    api.session.add(_settings())
    api.session.flush()
    entry = {
        "client_request_id": "req-1",
        "kind": "consolidation_loan",
        "item_price": "1000.00",
        "months": 2,
        "monthly_amount": "500.00",
        "first_due_month": "2026-11",
    }

    for path in ("/installments", "/installments/preview"):
        response = api.call("POST", path, entry)
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["kind"]
    assert api.session.execute(select(func.count()).select_from(Installment)).scalar_one() == 0


@pytest.mark.parametrize(
    "event_type", ["installment_created", "cash_withdrawal_created", "cash_loan_created"]
)
def test_CO_05_no_webhook_event_can_carry_the_loan_kind(webhook: Webhook, event_type: str) -> None:
    data = payload(event_type)
    data["contract"] |= {"kind": "consolidation_loan"}

    assert webhook.post(data).status_code == 422
    assert webhook.session.execute(select(func.count()).select_from(Installment)).scalar_one() == 0


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        # A full platform row, so only the vendor rule can reject it (review F2).
        (
            {"vendor": "shopdemo", "late_fee_per_period": Decimal("0.00")},
            "consolidation_loan_vendor",
        ),
        ({"vendor": "manual"}, "consolidation_loan_vendor"),
        ({"min_payment": None}, "consolidation_loan_terms"),
        ({"monthly_rate": None}, "consolidation_loan_terms"),
    ],
)
def test_CO_05_db_rejects_a_loan_without_its_vendor_or_terms(
    db_session: Session, overrides: dict[str, Any], constraint: str
) -> None:
    db_session.add(consolidation_loan(**overrides))
    with pytest.raises(IntegrityError, match=constraint):
        db_session.flush()


def test_CO_05_db_rejects_the_consolidation_vendor_on_another_kind(db_session: Session) -> None:
    db_session.add(consolidation_loan(kind="purchase"))
    with pytest.raises(IntegrityError, match="consolidation_loan_vendor"):
        db_session.flush()


def test_CO_05_db_accepts_a_loan_and_a_consolidated_installment(db_session: Session) -> None:
    db_session.add(consolidation_loan())
    db_session.add(installment(contract_id="c-2", status="consolidated"))
    db_session.add(
        installment(
            contract_id="c-3",
            status="consolidated",
            disputed_at=datetime(2026, 11, 1, tzinfo=UTC),
            dispute_signal_status="sent",
        )
    )
    db_session.flush()
