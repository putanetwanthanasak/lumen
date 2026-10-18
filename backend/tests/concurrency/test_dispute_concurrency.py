"""L42 "Not me" under concurrency.

1. Eight taps at once: one dispute audit row, one platform signal, eight identical answers.
2. "Not me" racing the payment that pays the debt off: the result is `disputed`, never
   `paid_off`. Without the contract lock, the payment can read `active`, the dispute
   commits, and the payment's _settle then writes paid_off over it.
3. A deterministic probe for 2: dispute() must wait on the webhooks' contract lock.
4. S4: after a failed signal, eight repeat taps at once re-send it exactly once, even
   with a slow platform; and a deterministic probe that send_signal takes the lock.

Demo:  cd backend && uv run pytest -m concurrency -v
"""

import time
import uuid
from collections import Counter

import pytest
from psycopg.errors import LockNotAvailable
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from app.disputes.service import dispute, send_signal
from app.ledger.reconcile import check_user_invariants
from app.models import AuditLog, Installment
from tests.concurrency.conftest import Race
from tests.processing.conftest import created
from tests.webhooks.conftest import VENDOR
from tests.webhooks.payloads import payload

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

TAPS = 8


def _open_debt(race: Race, principal: str = "800.00") -> tuple[str, uuid.UUID]:
    contract = race.id("c_1")
    [response] = race.fire([created(race.id("evt_c"), contract, principal, user=race.user)])
    assert response.status_code == 200
    with race.session() as s:
        installment_id = s.scalars(
            select(Installment.id).where(Installment.contract_id == contract)
        ).one()
    return contract, installment_id


def _disputes(race: Race) -> int:
    with race.session() as s:
        return s.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.user_id == race.user, AuditLog.action == "installment_disputed")
        ).scalar_one()


def test_L42_eight_concurrent_not_me_taps_dispute_once(race: Race) -> None:
    contract, installment_id = _open_debt(race)

    responses = race.parallel([lambda: race.not_me(installment_id)] * TAPS)

    assert Counter(r.status_code for r in responses) == {200: TAPS}
    assert len({r.text for r in responses}) == 1  # the same answer for every tap
    assert responses[0].json()["status"] == "disputed"
    assert _disputes(race) == 1
    assert [(s.contract_id, s.user_id) for s in race.platform.signals] == [(contract, race.user)]


def test_L42_not_me_racing_the_final_payment_stays_disputed(race: Race) -> None:
    contract, installment_id = _open_debt(race)
    final_payment = payload(
        "installment_payment_collected",
        event_id=race.id("evt_p"),
        user_ref=race.user,
        contract_id=contract,
        amount="800.00",
    )

    # Warm two pooled connections first. From a cold pool, opening them staggers the
    # two requests enough that a missing lock went unnoticed in 30 of 30 runs.
    race.parallel([lambda: race.client.get("/debts/summary", headers={"X-Demo-User": "warm"})] * 2)

    responses = race.parallel(
        [lambda: race.post_webhook(final_payment), lambda: race.not_me(installment_id)]
    )

    assert [r.status_code for r in responses] == [200, 200]
    with race.session() as s:
        row = s.execute(select(Installment).where(Installment.id == installment_id)).scalar_one()
        assert (row.paid_amount, row.status) == (800, "disputed")
        assert row.disputed_at is not None
        assert check_user_invariants(s, race.user) == []


def test_L42_dispute_waits_for_the_contract_lock(race: Race) -> None:
    contract, installment_id = _open_debt(race)
    with race.session() as holder, holder.begin():
        key = func.hashtextextended(f"{VENDOR}:{contract}", 0)
        holder.execute(select(func.pg_advisory_xact_lock(key)))  # as a webhook in flight
        with race.session() as s, s.begin():
            s.execute(text("SET LOCAL lock_timeout = '200ms'"))
            with pytest.raises(OperationalError) as exc:
                dispute(s, user_id=race.user, installment_id=installment_id)
            assert isinstance(exc.value.orig, LockNotAvailable)


def test_S4_eight_concurrent_retries_after_a_failed_signal_send_once(
    race: Race, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, installment_id = _open_debt(race)

    def down(**_: object) -> None:
        raise ConnectionError("platform down")

    monkeypatch.setattr(race.platform, "signal_dispute", down)
    assert race.not_me(installment_id).json()["platform_signal"] == "failed"
    monkeypatch.undo()
    real_signal = race.platform.signal_dispute

    def slow(**fields: str) -> None:
        # A real platform call takes time. With an instant mock, the taps never
        # overlap inside send_signal and a missing lock went unnoticed (10 of 10).
        time.sleep(0.2)
        real_signal(**fields)

    monkeypatch.setattr(race.platform, "signal_dispute", slow)

    responses = race.parallel([lambda: race.not_me(installment_id)] * TAPS)

    assert Counter(r.status_code for r in responses) == {200: TAPS}
    assert {r.json()["platform_signal"] for r in responses} == {"sent"}
    assert len({r.text for r in responses}) == 1
    assert [(s.contract_id, s.user_id) for s in race.platform.signals] == [(contract, race.user)]
    assert _disputes(race) == 1


def test_S4_send_signal_waits_for_the_contract_lock(
    race: Race, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, installment_id = _open_debt(race)

    def down(**_: object) -> None:
        raise ConnectionError("platform down")

    monkeypatch.setattr(race.platform, "signal_dispute", down)
    assert race.not_me(installment_id).json()["platform_signal"] == "failed"
    monkeypatch.undo()
    with race.session() as s:
        report = dispute(s, user_id=race.user, installment_id=installment_id)
        s.rollback()
    assert report is not None

    with race.session() as holder, holder.begin():
        key = func.hashtextextended(f"{VENDOR}:{contract}", 0)
        holder.execute(select(func.pg_advisory_xact_lock(key)))  # another tap mid-signal
        with race.session() as s, s.begin():
            s.execute(text("SET LOCAL lock_timeout = '200ms'"))
            with pytest.raises(OperationalError) as exc:
                send_signal(s, report=report, user_id=race.user, platform=race.platform)
            assert isinstance(exc.value.orig, LockNotAvailable)
    assert race.platform.signals == []  # it never got as far as the platform
