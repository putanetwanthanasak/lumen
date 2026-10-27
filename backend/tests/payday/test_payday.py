"""PD-01, PD-02, PD-04 to PD-06 and LO-01 to LO-06: the payday run (L67)
through POST /demo/payday. PD-03 runs concurrently in tests/concurrency. 05 has no
PD or LO section; the IDs are new (Session 13).

The profile from opt_in is income 30,000.00 and budget 9,000.00. Installments are
written as Ledger rows due in November 2026 unless a test says otherwise.
"""

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import OperationalError

from app.affordability.months import Month
from app.config import Settings
from app.db import Base
from app.ledger.reconcile import InvariantViolationError, check_user_invariants
from app.main import create_app
from app.models import (
    AuditLog,
    Notification,
    PaydayRun,
    SavingsTransaction,
    UserBalance,
    UserSettings,
)
from app.payday import service as payday_service
from app.savings import service as savings
from tests.db.factories import installment, savings_tx
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

OPENING = Decimal("10000.00")
NOV = "2026-11"


def due(api: Api, monthly: str, *, months: int = 1, first: date = date(2026, 11, 1)) -> uuid.UUID:
    row = installment(
        user_id=USER,
        contract_id=str(uuid.uuid4()),
        principal=Decimal(monthly) * months,
        monthly_amount=Decimal(monthly),
        months=months,
        first_due_date=first,
    )
    api.session.add(row)
    api.session.flush()
    return row.id


def configure(api: Api, *, leftover: bool = True, **opt: Any) -> None:
    opt_in(api.session, **opt)
    api.session.execute(
        update(UserSettings)
        .where(UserSettings.user_id == USER)
        .values(leftover_saving_enabled=leftover)
    )


def buffer_of(api: Api, amount: str) -> None:
    """A consistent buffer (INV-1): an auto-save of `amount` on its own installment."""
    inst = due(api, "1.00", first=date(2020, 1, 1))  # long finished, never due again
    api.session.add(
        savings_tx(
            user_id=USER,
            amount=Decimal(amount),
            installment_id=inst,
            source_vendor=None,
            source_event_id=None,
        )
    )
    api.session.add(UserBalance(user_id=USER, savings_balance=Decimal(amount)))
    api.session.flush()


def payday(api: Api, month: Any = NOV, user: str | None = USER) -> Any:
    return api.call("POST", "/demo/payday", {"month": month}, user=user)


def alerts(api: Api) -> list[Notification]:
    api.session.expire_all()
    rows = api.session.execute(select(Notification).order_by(Notification.created_at))
    return list(rows.scalars())


def leftover_saves(api: Api) -> list[tuple[Decimal, date | None]]:
    rows = api.session.execute(
        select(SavingsTransaction.amount, SavingsTransaction.payday_month).where(
            SavingsTransaction.type == "leftover_save"
        )
    )
    return [(amount, month) for amount, month in rows]


def buffer_now(api: Api) -> Decimal:
    api.session.expire_all()
    return api.session.execute(
        select(UserBalance.savings_balance).where(UserBalance.user_id == USER)
    ).scalar_one()


# --- PD-01: over budget ----------------------------------------------------------------


def test_PD_01_over_budget_alerts_with_shortfall_and_buffer(demo: Api) -> None:
    configure(demo)
    buffer_of(demo, "820.50")
    due(demo, "6000.00")
    due(demo, "4500.00", months=3)  # 10,500.00 in November

    response = payday(demo)

    assert response.status_code == 201
    assert response.json() == {
        "month": NOV,
        "status": "created",
        "outcome": "over_budget",
        "month_total": "10500.00",
        "budget": "9000.00",
        "amount": "1500.00",
        "buffer_balance": "820.50",
    }
    [alert] = alerts(demo)
    assert (alert.user_id, alert.kind, alert.installment_id) == (USER, "payday_shortfall", None)
    assert alert.title == "เดือนนี้ค่างวดเกินงบ"
    assert alert.body == (
        "เดือน พ.ย. 2569 ค่างวดรวม 10,500 บาท เกินงบ 1,500 บาท คุณมีกันชน 820.50 บาท ย้ายมาช่วยจ่ายได้"
    )
    assert alert.delivery_status == "pushed"
    assert [a.title for a in demo.push.attempts] == ["เดือนนี้ค่างวดเกินงบ"]
    assert leftover_saves(demo) == []  # (a) never saves
    assert demo.bank.get_balance(USER) == OPENING


def test_PD_01_over_budget_alert_ignores_the_leftover_switch(demo: Api) -> None:
    configure(demo, leftover=False)
    due(demo, "9000.01")
    assert payday(demo).json()["outcome"] == "over_budget"
    assert [a.kind for a in alerts(demo)] == ["payday_shortfall"]


# --- PD-02, PD-04: once per month ------------------------------------------------------


@pytest.mark.parametrize("monthly", ["9500.00", "7000.00"], ids=["over_budget", "leftover"])
def test_PD_02_second_run_of_the_month_changes_nothing(demo: Api, monthly: str) -> None:
    configure(demo)
    due(demo, monthly)
    first = payday(demo)
    before = {
        t.name: demo.session.execute(select(func.count()).select_from(t)).scalar_one()
        for t in Base.metadata.sorted_tables
    }
    bank_before = demo.bank.get_balance(USER)

    second = payday(demo)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json() | {"status": "duplicate"}
    after = {
        t.name: demo.session.execute(select(func.count()).select_from(t)).scalar_one()
        for t in Base.metadata.sorted_tables
    }
    assert after == before
    assert demo.bank.get_balance(USER) == bank_before
    assert len(demo.push.attempts) == 1


def test_PD_02_a_repeat_returns_the_stored_outcome_even_if_things_changed(demo: Api) -> None:
    # Once per month is literal (open question 7): the stored run is the answer.
    configure(demo, leftover=False)
    due(demo, "7000.00")
    first = payday(demo)
    demo.session.execute(update(UserSettings).values(leftover_saving_enabled=True))

    again = payday(demo)

    assert first.json()["outcome"] == again.json()["outcome"] == "leftover_off"
    assert leftover_saves(demo) == []


def test_PD_04_each_month_runs_on_its_own(demo: Api) -> None:
    configure(demo)
    due(demo, "9500.00")  # November only
    nov, dec = payday(demo, "2026-11"), payday(demo, "2026-12")
    assert (nov.status_code, dec.status_code) == (201, 201)
    assert (nov.json()["outcome"], dec.json()["outcome"]) == ("over_budget", "leftover_saved")
    assert dec.json()["amount"] == "9000.00"  # nothing due in December: all of the budget
    assert leftover_saves(demo) == [(Decimal("9000.00"), date(2026, 12, 1))]
    runs = demo.session.execute(select(PaydayRun.month).order_by(PaydayRun.month)).scalars()
    assert list(runs) == [date(2026, 11, 1), date(2026, 12, 1)]


def test_PD_04_month_total_counts_only_installments_due_that_month(demo: Api) -> None:
    configure(demo, leftover=False)
    due(demo, "300.00", months=2, first=date(2026, 10, 1))  # Oct and Nov
    due(demo, "400.00", months=1, first=date(2026, 12, 1))  # Dec only
    assert payday(demo, "2026-11").json()["month_total"] == "300.00"
    assert payday(demo, "2026-12").json()["month_total"] == "400.00"
    assert payday(demo, "2027-01").json()["month_total"] == "0.00"


# --- PD-05: the demo endpoint is off by default ----------------------------------------


def test_PD_05_demo_endpoint_is_404_when_the_flag_is_off(api: Api) -> None:
    opt_in(api.session)
    assert payday(api).status_code == 404  # the module app: flag off in tests and CI


def served(settings: Settings) -> bool:
    """Whether an app built with these settings has POST /demo/payday. Without a user
    header a mounted route answers 401 before touching anything; an absent one, 404."""
    with TestClient(create_app(settings)) as client:
        status = client.post("/demo/payday", json={"month": NOV}).status_code
    assert status in (401, 404)
    return status == 401


def test_PD_05_flag_defaults_to_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_ENDPOINTS_ENABLED", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.demo_endpoints_enabled is False
    assert served(settings) is False


@pytest.mark.parametrize(("value", "enabled"), [("true", True), ("false", False)])
def test_PD_05_flag_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, value: str, enabled: bool
) -> None:
    monkeypatch.setenv("DEMO_ENDPOINTS_ENABLED", value)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.demo_endpoints_enabled is enabled
    assert served(settings) is enabled


# --- PD-06: settings, validation, auth ---------------------------------------------------


def test_PD_06_without_a_profile_is_409_and_records_no_run(demo: Api) -> None:
    response = payday(demo)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SETTINGS_REQUIRED"
    count = demo.session.execute(select(func.count()).select_from(PaydayRun)).scalar_one()
    assert count == 0


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "202611", 202611, None, "2026-11-01"])
def test_PD_06_bad_month_is_422(demo: Api, month: Any) -> None:
    configure(demo)
    assert payday(demo, month).status_code == 422


def test_PD_06_unknown_key_is_422(demo: Api) -> None:
    configure(demo)
    response = demo.call("POST", "/demo/payday", {"month": NOV, "extra": 1})
    assert response.status_code == 422


@pytest.mark.parametrize("user", [None, ""])
def test_PD_06_without_a_user_is_401(demo: Api, user: str | None) -> None:
    assert payday(demo, user=user).status_code == 401


# --- LO-01 to LO-04: leftover saving ----------------------------------------------------


def test_LO_01_leftover_is_saved_to_the_buffer(demo: Api) -> None:
    configure(demo)
    buffer_of(demo, "100.00")
    due(demo, "7200.00")

    response = payday(demo)

    assert response.status_code == 201
    body = response.json()
    assert (body["outcome"], body["amount"], body["buffer_balance"]) == (
        "leftover_saved",
        "1800.00",
        "1900.00",
    )
    assert leftover_saves(demo) == [(Decimal("1800.00"), date(2026, 11, 1))]
    assert buffer_now(demo) == Decimal("1900.00")  # INV-1: the ledger and the cache agree
    assert demo.bank.get_balance(USER) == OPENING - Decimal("1800.00")
    [alert] = alerts(demo)
    assert (alert.kind, alert.title) == ("leftover_saved", "ออมส่วนที่เหลือจากงบแล้ว")
    assert alert.body == "เดือน พ.ย. 2569 ค่างวดรวม 7,200 บาท ต่ำกว่างบ 1,800 บาท ย้ายเข้ากันชนแล้ว"
    [entry] = demo.session.execute(
        select(AuditLog).where(AuditLog.action == "leftover_saved")
    ).scalars()
    assert (entry.actor, entry.user_id, entry.ref_type) == ("system", USER, "savings_transaction")
    assert entry.detail == {"month": NOV, "amount": "1800.00", "recovered": False}


@pytest.mark.parametrize(
    "opt",
    [{"leftover": False}, {"enabled": False}, {"consent": False}],
    ids=["leftover_off", "auto_save_off", "no_consent"],
)
def test_LO_02_not_opted_in_saves_nothing(demo: Api, opt: dict[str, Any]) -> None:
    configure(demo, **opt)
    due(demo, "7200.00")
    response = payday(demo)
    assert response.status_code == 201
    assert (response.json()["outcome"], response.json()["amount"]) == ("leftover_off", "0.00")
    assert leftover_saves(demo) == []
    assert alerts(demo) == []
    assert demo.bank.get_balance(USER) == OPENING


def test_LO_03_safety_net_exactly_500_left_saves(demo: Api) -> None:
    configure(demo)
    due(demo, "8000.00")  # 1,000.00 left
    demo.bank.set_balance(USER, Decimal("1500.00"))
    assert payday(demo).json()["outcome"] == "leftover_saved"
    assert demo.bank.get_balance(USER) == Decimal("500.00")


def test_LO_03_safety_net_one_satang_short_saves_nothing(demo: Api) -> None:
    configure(demo)
    due(demo, "8000.00")
    demo.bank.set_balance(USER, Decimal("1499.99"))
    response = payday(demo)
    assert (response.json()["outcome"], response.json()["amount"]) == ("safety_net", "0.00")
    assert leftover_saves(demo) == []  # never a partial 999.99
    assert alerts(demo) == []
    assert demo.bank.get_balance(USER) == Decimal("1499.99")


def test_LO_04_total_equal_to_budget_saves_nothing(demo: Api) -> None:
    configure(demo)
    due(demo, "9000.00")
    response = payday(demo)
    assert (response.json()["outcome"], response.json()["amount"]) == ("no_leftover", "0.00")
    assert leftover_saves(demo) == []
    assert alerts(demo) == []


# --- LO-06: the bank moves the leftover at most once (S1) --------------------------------


def test_LO_06_leftover_key_is_stable_per_month_and_distinct() -> None:
    key = savings.leftover_key(USER, NOV)
    assert key == savings.leftover_key(USER, NOV)
    assert key != savings.leftover_key(USER, "2026-12")
    assert key != savings.leftover_key("user_b", NOV)
    assert key != savings.manual_transfer_key(USER, NOV)
    assert key != savings.move_key(USER, NOV)


def test_LO_06_commit_fails_after_transfer_retry_debits_once(
    demo: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(demo)
    due(demo, "7200.00")
    demo.session.commit()  # kept by the rollback below: only the lost run rolls back
    session = demo.session
    real_commit = session.commit

    def commit_fails_once() -> None:
        monkeypatch.setattr(session, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails_once)

    lost = payday(demo)
    session.rollback()  # what get_session's close does after the failed request
    assert lost.status_code == 500
    assert leftover_saves(demo) == []
    assert demo.bank.get_balance(USER) == OPENING - Decimal("1800.00")  # the money moved

    retry = payday(demo)

    assert retry.status_code == 201, retry.text
    assert demo.bank.get_balance(USER) == OPENING - Decimal("1800.00")  # debited once
    assert leftover_saves(demo) == [(Decimal("1800.00"), date(2026, 11, 1))]


# --- LO-05: reconcile knows the leftover saving ------------------------------------------


def test_LO_05_leftover_save_counts_as_a_credit_for_INV_1(demo: Api) -> None:
    configure(demo)
    buffer_of(demo, "100.00")
    due(demo, "7200.00")
    assert payday(demo).json()["outcome"] == "leftover_saved"
    assert check_user_invariants(demo.session, USER) == []
    assert buffer_now(demo) == Decimal("1900.00")


def test_LO_05_two_leftover_saves_in_one_month_are_detected(owner_session: Any) -> None:
    # The partial UNIQUE index blocks this; drop it, so reconcile must catch it alone.
    owner_session.execute(text("DROP INDEX uq_savings_transactions_leftover_save_month"))
    for _ in range(2):
        owner_session.add(
            savings_tx(
                user_id=USER,
                type="leftover_save",
                amount=Decimal("50.00"),
                source_vendor=None,
                source_event_id=None,
                payday_month=date(2026, 11, 1),
            )
        )
    owner_session.add(UserBalance(user_id=USER, savings_balance=Decimal("100.00")))
    owner_session.flush()
    assert check_user_invariants(owner_session, USER) == ["L67"]


def test_RS_02_violation_rolls_back_the_whole_run(
    demo: Api, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A simulated bug: the leftover is credited one baht too much. Nothing of the run
    may persist and no money may move, so the month can still run."""
    configure(demo)
    due(demo, "7200.00")
    demo.session.commit()  # kept by the rollback: only the run rolls back
    real_adjust = savings.adjust_balance
    monkeypatch.setattr(
        savings,
        "adjust_balance",
        lambda session, user_id, delta: real_adjust(session, user_id, delta + Decimal(1)),
    )
    with caplog.at_level(logging.ERROR), pytest.raises(InvariantViolationError) as exc:
        payday(demo)

    assert exc.value.violations == ["INV-1"]
    for model in (PaydayRun, Notification):
        assert demo.session.execute(select(func.count()).select_from(model)).scalar_one() == 0
    assert leftover_saves(demo) == []
    assert demo.bank.get_balance(USER) == OPENING
    [record] = caplog.records
    assert "payday run rolled back" in record.getMessage()
    assert USER not in record.getMessage()  # S12


def test_PD_02_primary_key_is_the_second_layer(demo: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the lookup before the insert ever missed the month's run (say the balance
    lock stopped serialising runs), ON CONFLICT still finds it and nothing repeats."""
    configure(demo)
    due(demo, "9500.00")
    first = payday(demo)
    real_stored = payday_service._stored
    calls: list[int] = []

    def blind_once(user_id: str, month: Month) -> Any:
        calls.append(1)
        return real_stored(user_id if len(calls) > 1 else "nobody", month)

    monkeypatch.setattr(payday_service, "_stored", blind_once)
    again = payday(demo)

    assert len(calls) == 2  # the blind lookup, then the one after ON CONFLICT
    assert again.status_code == 200
    assert again.json() == first.json() | {"status": "duplicate"}
    assert len(alerts(demo)) == 1


def lose_first_commit(demo: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """The next commit fails after the bank call, as a lost connection would."""
    session = demo.session
    real_commit = session.commit

    def commit_fails_once() -> None:
        monkeypatch.setattr(session, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails_once)


def test_LO_06_retry_near_the_safety_net_records_the_money_that_moved(
    demo: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review F1: after the lost commit the main account holds 600.00, so deciding
    again would skip for the safety net, leaving 1,800.00 moved and not recorded."""
    configure(demo)
    due(demo, "7200.00")
    demo.bank.set_balance(USER, Decimal("2400.00"))
    demo.session.commit()
    lose_first_commit(demo, monkeypatch)
    assert payday(demo).status_code == 500
    demo.session.rollback()
    assert demo.bank.get_balance(USER) == Decimal("600.00")

    retry = payday(demo)

    assert retry.status_code == 201, retry.text
    assert (retry.json()["outcome"], retry.json()["amount"]) == ("leftover_saved", "1800.00")
    assert leftover_saves(demo) == [(Decimal("1800.00"), date(2026, 11, 1))]
    assert buffer_now(demo) == Decimal("1800.00")
    assert demo.bank.get_balance(USER) == Decimal("600.00")
    [entry] = demo.session.execute(
        select(AuditLog).where(AuditLog.action == "leftover_saved")
    ).scalars()
    assert entry.detail == {"month": NOV, "amount": "1800.00", "recovered": True}


def test_LO_06_retry_after_the_month_total_changed_records_the_money_that_moved(
    demo: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review F1 variant: a new November installment lands between the lost commit
    and the retry. Deciding again would ask the bank for another amount on the same
    key; the money that moved is what gets recorded."""
    configure(demo)
    due(demo, "7200.00")
    demo.session.commit()
    lose_first_commit(demo, monkeypatch)
    assert payday(demo).status_code == 500
    demo.session.rollback()
    due(demo, "500.00")

    retry = payday(demo)

    assert retry.status_code == 201, retry.text
    assert (retry.json()["outcome"], retry.json()["amount"]) == ("leftover_saved", "1800.00")
    assert leftover_saves(demo) == [(Decimal("1800.00"), date(2026, 11, 1))]
    assert demo.bank.get_balance(USER) == OPENING - Decimal("1800.00")
    # Review round 2 F2: the run records the decision the first attempt made (7,200
    # under the budget by 1,800), so the stored total, the response and the alert
    # agree with each other and with the money, not 7,700 "under by 1,800".
    assert retry.json()["month_total"] == "7200.00"
    [alert] = alerts(demo)
    assert alert.body == "เดือน พ.ย. 2569 ค่างวดรวม 7,200 บาท ต่ำกว่างบ 1,800 บาท ย้ายเข้ากันชนแล้ว"
