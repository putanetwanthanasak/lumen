"""PB-03 and PB-04 (05 section 4.2): random event histories through the real processor.

Each example draws up to 3 contracts across 2 users. Each contract gets a created
event (purchase or cash) and up to 4 payment, overdue or cancel events, sometimes for
the wrong user, and maybe a "Not me" tap (L42), sometimes by the wrong user. Delivery
is a random permutation, so events often arrive before their installment, and some
events and taps are repeated at random points. A tap always comes after its created
event: the user can only report a debt they can see.

PB-03: after every delivered event, all invariants hold:
- reconcile is clean for both users (INV-1, 2, 3, 5, 6, L51);
- savings and the bank move only on a created event (INV-7 and no saving from
  payment, overdue or cancel);
- the ledger matches the stored events: paid_amount is the sum of processed payments,
  late fees come from the latest processed overdue (L55), status follows from them,
  and nothing waits as pending_parent once its installment exists;
- every installment has exactly one new-debt alert, whatever happened to it (L58);
- the dispute history survives every sequence (L59 3): once set, disputed_at never
  changes or clears, there is exactly one dispute audit row, the alert stays not_me,
  and the status is disputed unless a cancel made it cancelled.
PB-04: the final state with resends equals the final state without them.

Each history runs inside a savepoint that is rolled back, on the shared test DB.
"""

from collections import Counter
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.disputes.service import dispute
from app.ledger.reconcile import check_user_invariants
from app.ledger.service import CREATED_EVENT_TYPES
from app.models import AuditLog, Installment, Notification, SavingsTransaction, WebhookEvent
from app.providers.mock_bank import MockBankAccountProvider
from tests.processing.conftest import balance, created, opt_in, run
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db

EXAMPLES = 150
USERS = ("pb_a", "pb_b")
ZERO = Decimal("0.00")

History = tuple[list[dict[str, Any]], list[dict[str, Any]]]


@st.composite
def histories(draw: st.DrawFn) -> History:
    """(delivery without resends, delivery with resends)."""
    events: list[dict[str, Any]] = []
    for c in range(draw(st.integers(1, 3))):
        owner = draw(st.sampled_from(USERS))
        contract = f"pb_c{c}"
        event_type = draw(st.sampled_from(["installment_created"] * 3 + ["cash_loan_created"]))
        principal = draw(st.sampled_from(["100.00", "800.00", "1500.00"]))
        events.append(created(f"pb_e{c}_0", contract, principal, event_type=event_type, user=owner))
        for i in range(1, draw(st.integers(0, 4)) + 1):
            user = owner if draw(st.integers(0, 9)) else next(u for u in USERS if u != owner)
            common: dict[str, Any] = {
                "event_id": f"pb_e{c}_{i}",
                "user_ref": user,
                "contract_id": contract,
                "occurred_at": f"2026-10-12T10:{i:02}:00Z",  # true order within a contract
            }
            match draw(st.sampled_from(["pay", "pay", "overdue", "cancel"])):
                case "pay":
                    amount = draw(st.sampled_from(["10.00", "50.00", "99.99", "800.00"]))
                    data = payload("installment_payment_collected", amount=amount, **common)
                case "overdue":
                    fees = draw(st.sampled_from(["0.00", "5.00", "25.00", "80.00"]))
                    days = draw(st.integers(1, 60))
                    data = payload(
                        "installment_overdue", late_fees_accrued=fees, overdue_days=days, **common
                    )
                case _:
                    data = payload("installment_cancelled", **common)
            events.append(data)
        if draw(st.booleans()):
            user = owner if draw(st.integers(0, 4)) else next(u for u in USERS if u != owner)
            events.append(
                {
                    "not_me": contract,
                    "user_ref": user,
                    "event_id": f"pb_d{c}",
                    "after": f"pb_e{c}_0",
                }
            )
    delivery = draw(st.permutations(events))
    for report in [e for e in delivery if "not_me" in e]:
        delivery.remove(report)
        after = next(i for i, e in enumerate(delivery) if e["event_id"] == report["after"])
        delivery.insert(draw(st.integers(after + 1, len(delivery))), report)
    with_resends = list(delivery)
    for _ in range(draw(st.integers(0, 4))):
        resend = draw(st.sampled_from(delivery))
        # After its first delivery: a copy placed earlier would reorder the history,
        # and order may legitimately matter (OR-05 rejects whichever payment overflows).
        first = with_resends.index(resend)
        with_resends.insert(draw(st.integers(first + 1, len(with_resends))), resend)
    return delivery, with_resends


def savings_state(session: Session, bank: MockBankAccountProvider) -> tuple[Any, ...]:
    return tuple((balance(session, u), bank.get_balance(u)) for u in USERS)


def ledger_matches_events(session: Session) -> None:
    rows = session.execute(select(WebhookEvent)).scalars().all()
    by_contract: dict[str, list[WebhookEvent]] = {}
    for row in rows:
        by_contract.setdefault(row.contract_id, []).append(row)
    installments = {i.contract_id: i for i in session.execute(select(Installment)).scalars()}
    alerted = Counter(session.execute(select(Notification.installment_id)).scalars())
    assert alerted == Counter(i.id for i in installments.values())  # L58, NT-04
    responses = dict(
        session.execute(select(Notification.installment_id, Notification.user_response)).all()
    )
    disputes = Counter(
        session.execute(
            select(AuditLog.ref_id).where(AuditLog.action == "installment_disputed")
        ).scalars()
    )

    for contract, stored in by_contract.items():
        children = [r for r in stored if r.event_type not in CREATED_EVENT_TYPES]
        inst = installments.get(contract)
        if inst is None:
            assert all(r.status == "pending_parent" for r in children)
            continue
        processed = [r for r in children if r.status == "processed"]
        assert all(r.status in ("processed", "rejected") for r in children)
        payments = [r for r in processed if r.event_type == "installment_payment_collected"]
        assert inst.paid_amount == sum((Decimal(r.payload["amount"]) for r in payments), ZERO)
        overdues = [r for r in processed if r.event_type == "installment_overdue"]
        if overdues:
            latest = max(overdues, key=lambda r: r.payload["occurred_at"]).payload
            assert inst.late_fees_accrued == Decimal(latest["late_fees_accrued"])  # L55
            assert inst.overdue_days == latest["overdue_days"]
        else:
            assert (inst.late_fees_accrued, inst.overdue_days) == (ZERO, 0)
        owed = inst.principal + inst.fee_total + inst.late_fees_accrued
        assert inst.paid_amount <= owed  # INV-6
        disputed = disputes[str(inst.id)]
        assert disputed <= 1  # one audit row, whatever the taps
        assert (inst.disputed_at is not None) == (disputed == 1)
        if disputed:
            assert responses[inst.id] == "not_me"
        if any(r.event_type == "installment_cancelled" for r in processed):
            assert inst.status == "cancelled"
        elif disputed:
            assert inst.status == "disputed"  # _settle never changes it
        else:
            assert inst.status == ("paid_off" if inst.paid_amount == owed else "active")


def snapshot(session: Session, bank: MockBankAccountProvider) -> tuple[Any, ...]:
    session.expire_all()
    installments = sorted(
        (
            i.contract_id,
            i.paid_amount,
            i.late_fees_accrued,
            i.overdue_days,
            i.status,
            i.disputed_at is not None,
        )
        for i in session.execute(select(Installment)).scalars()
    )
    events = sorted(session.execute(select(WebhookEvent.event_id, WebhookEvent.status)).all())
    saves = sorted(session.execute(select(SavingsTransaction.amount)).scalars())
    alerts = sorted(session.execute(select(Notification.kind, Notification.body)).all())
    return installments, events, saves, alerts, savings_state(session, bank)


def tap(session: Session, data: dict[str, Any]) -> None:
    """A "Not me" tap, through the same service the endpoint calls."""
    installment_id = session.execute(
        select(Installment.id).where(Installment.contract_id == data["not_me"])
    ).scalar_one()
    result = dispute(session, user_id=data["user_ref"], installment_id=installment_id)
    event("not_me: " + ("wrong user" if result is None else f"first={result.first_report}"))


def deliver(session: Session, delivery: list[dict[str, Any]], *, check: bool) -> tuple[Any, ...]:
    savepoint = session.begin_nested()
    try:
        bank = MockBankAccountProvider()
        for user in USERS:
            opt_in(session, user)
        seen: set[str] = set()
        disputed_at: dict[str, Any] = {}
        for data in delivery:
            before = savings_state(session, bank)
            if "not_me" in data:
                tap(session, data)
            else:
                outcome = run(session, data, bank)
                event(f"outcome: {outcome}")
                seen.add(data["event_id"])
            if not check:
                continue
            session.expire_all()
            for user in USERS:
                assert check_user_invariants(session, user) == []
            if data.get("event_type") not in CREATED_EVENT_TYPES:
                assert savings_state(session, bank) == before  # INV-7, and "Not me"
            for inst in session.execute(select(Installment)).scalars():
                if inst.contract_id in disputed_at:  # L59 3: never changed or cleared
                    assert inst.disputed_at == disputed_at[inst.contract_id]
                elif inst.disputed_at is not None:
                    disputed_at[inst.contract_id] = inst.disputed_at
            ledger_matches_events(session)
            assert len(session.execute(select(WebhookEvent.event_id)).all()) == len(seen)
        return snapshot(session, bank)
    finally:
        savepoint.rollback()


@settings(
    max_examples=EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(history=histories())
def test_PB_03_PB_04_invariants_after_every_event_and_resends_change_nothing(
    db_session: Session, history: History
) -> None:
    delivery, with_resends = history
    event(f"resends: {len(with_resends) - len(delivery)}")
    event(f"events: {len(delivery)}")

    with_resends_state = deliver(db_session, with_resends, check=True)
    once_state = deliver(db_session, delivery, check=False)

    assert with_resends_state == once_state  # PB-04
    assert Counter(status for _, status in once_state[1])["pending_parent"] == 0
