"""S1 (the part built now): the bank applies an auto-save transfer at most once.

The transfer runs before COMMIT (step 5c). If the commit then fails, the ledger rows
roll back but the money has moved, and the platform retries the event. The retry
carries the same (vendor, event_id), so the same idempotency key, and the bank does
nothing the second time. The full fix, a transactional outbox, is roadmap R4.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from app.models import Notification, SavingsTransaction, UserSettings
from app.providers.mock_bank import DEFAULT_OPENING_BALANCE, MockBankAccountProvider
from app.savings import service as savings
from app.webhooks import processor
from tests.processing.conftest import USER, opt_in
from tests.webhooks.conftest import Webhook
from tests.webhooks.payloads import payload

pytestmark = pytest.mark.db


def test_S1_transfer_key_is_stable_per_event_and_distinct_across_events() -> None:
    key = savings.transfer_key("shopdemo", "evt_1")
    assert key == savings.transfer_key("shopdemo", "evt_1")
    assert key != savings.transfer_key("shopdemo", "evt_2")
    assert key != savings.transfer_key("othervendor", "evt_1")
    # No separator games: ("a:b", "c") and ("a", "b:c") are different events.
    assert savings.transfer_key("a:b", "c") != savings.transfer_key("a", "b:c")


def test_S1_commit_fails_after_transfer_retry_debits_the_bank_once(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    bank = MockBankAccountProvider()
    monkeypatch.setattr(processor, "get_bank_provider", lambda: bank)
    opt_in(webhook.session)
    webhook.session.commit()  # kept by the rollback below: only the lost request rolls back
    data = payload(contract={**payload()["contract"], "principal": "1200.00"})
    session = webhook.session
    real_commit = session.commit

    def commit_fails_once() -> None:
        monkeypatch.setattr(session, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails_once)

    lost = webhook.post(data)
    session.rollback()  # what get_session's close does after the failed request
    assert lost.status_code == 500
    assert bank.get_balance("user_a") == DEFAULT_OPENING_BALANCE - Decimal("120.00")

    retry = webhook.post(data)

    assert retry.status_code == 200, retry.text
    assert bank.get_balance("user_a") == DEFAULT_OPENING_BALANCE - Decimal("120.00")
    saved = session.execute(select(SavingsTransaction.amount)).scalars().all()
    assert saved == [Decimal("120.00")]  # the retry did save; the bank just moved it once


def _lose_the_first_delivery(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch, data: dict[str, object]
) -> None:
    """Deliver the event once with its commit lost, as a dropped connection would."""
    session = webhook.session
    real_commit = session.commit

    def commit_fails_once() -> None:
        monkeypatch.setattr(session, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails_once)
    lost = webhook.post(data)
    session.rollback()  # what get_session's close does after the failed request
    assert lost.status_code == 500


def test_S1_retry_near_the_safety_net_records_what_the_bank_moved(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review F2 (Session 23), the webhook path: 300.00 out of 900.00 leaves 600.00.
    # Deciding again on the platform's retry would save 0.00 (600.00 - 300.00 is under
    # the 500.00 net) while the first 300.00 had already left the main account.
    bank = MockBankAccountProvider()
    bank.set_balance(USER, Decimal("900.00"))
    monkeypatch.setattr(processor, "get_bank_provider", lambda: bank)
    opt_in(webhook.session, fixed="300.00")
    webhook.session.commit()
    data = payload(contract={**payload()["contract"], "principal": "1200.00"})
    _lose_the_first_delivery(webhook, monkeypatch, data)
    assert bank.get_balance(USER) == Decimal("600.00")

    retry = webhook.post(data)

    assert retry.status_code == 200, retry.text
    assert bank.get_balance(USER) == Decimal("600.00")  # debited once
    saved = webhook.session.execute(select(SavingsTransaction.amount)).scalars().all()
    assert saved == [Decimal("300.00")]


def test_S1_retry_after_the_rule_changed_records_the_first_amount_instead_of_failing(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 10% of 1,200.00 moved, then the user changed the rule to 20%. Deciding again
    # would ask the bank for 240.00 under the same key: refused, so every platform
    # retry would fail and the installment and its alert would never be recorded.
    bank = MockBankAccountProvider()
    monkeypatch.setattr(processor, "get_bank_provider", lambda: bank)
    opt_in(webhook.session)
    webhook.session.commit()
    data = payload(contract={**payload()["contract"], "principal": "1200.00"})
    _lose_the_first_delivery(webhook, monkeypatch, data)
    session = webhook.session
    session.execute(
        update(UserSettings).where(UserSettings.user_id == USER).values(saving_percent=20)
    )
    session.commit()

    retry = webhook.post(data)

    assert retry.status_code == 200, retry.text
    assert bank.get_balance(USER) == DEFAULT_OPENING_BALANCE - Decimal("120.00")
    saved = session.execute(select(SavingsTransaction.amount)).scalars().all()
    assert saved == [Decimal("120.00")]


def test_S1_retry_as_a_cash_withdrawal_saves_nothing_and_stores_its_alert(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR 3 review F1, the webhook path: the platform resends the same event_id as a
    # cash withdrawal after the lost commit. INV-5 is decided before the guard, so the
    # event is recorded and its strong alert stored (L50, L58), with no saving.
    bank = MockBankAccountProvider()
    monkeypatch.setattr(processor, "get_bank_provider", lambda: bank)
    opt_in(webhook.session)
    webhook.session.commit()
    first = payload(contract={**payload()["contract"], "principal": "1200.00"})
    _lose_the_first_delivery(webhook, monkeypatch, first)
    cash = payload("cash_withdrawal_created")
    assert cash["event_id"] == first["event_id"]

    retry = webhook.post(cash)

    assert retry.status_code == 200, retry.text
    session = webhook.session
    assert session.execute(select(SavingsTransaction.amount)).scalars().all() == []
    assert len(session.execute(select(Notification.id)).scalars().all()) == 1
