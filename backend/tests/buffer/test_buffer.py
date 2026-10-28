"""BF-01 to BF-05, BF-08, BF-09, BF-11: the buffer (L66) over HTTP. BF-06 and BF-07 run
concurrently in tests/concurrency. 05 has no BF section; BF-02, BF-03 and BF-07 are
05 SV-04, SV-05 and SV-06 for this endpoint.

Savings get in the way they do in the app: a manual entry auto-saves by a fixed
rule, here 500.00 out of the mock bank's 10,000.00 opening balance.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.buffer import service as buffer_service
from app.ledger.reconcile import InvariantViolationError, check_user_invariants
from app.models import AuditLog, SavingsTransaction, UserBalance
from app.savings import service as savings
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

OPENING = Decimal("10000.00")
ABOVE_BALANCE = {
    "detail": {"code": "AMOUNT_ABOVE_BALANCE", "message": "the buffer holds less than this amount"}
}


def save(api: Api, amount: str = "500.00", *, months: int = 10, monthly: str = "300.00") -> None:
    """Opt in with a fixed rule and record one entry, which saves `amount`."""
    opt_in(api.session, fixed=amount)
    response = api.call(
        "POST",
        "/installments",
        {
            "client_request_id": "entry-1",
            "kind": "purchase",
            "item_price": "3000.00",
            "months": months,
            "monthly_amount": monthly,
            "first_due_month": "2026-11",
        },
    )
    assert response.status_code == 201
    assert response.json()["saved_amount"] == amount


def move(api: Api, amount: Any, request_id: str = "move-1", user: str | None = USER) -> Any:
    return api.call(
        "POST",
        "/buffer/move-to-main",
        {"client_request_id": request_id, "amount": amount},
        user=user,
    )


def withdrawals(api: Api) -> list[Decimal]:
    return list(
        api.session.execute(
            select(SavingsTransaction.amount).where(SavingsTransaction.type == "withdrawal")
        ).scalars()
    )


def stored_balance(api: Api) -> Decimal:
    api.session.expire_all()
    return api.session.execute(
        select(UserBalance.savings_balance).where(UserBalance.user_id == USER)
    ).scalar_one()


# --- BF-01: reading the buffer ---------------------------------------------------------


def test_BF_01_buffer_shows_balance_and_whole_months_covered(api: Api) -> None:
    save(api, "500.00", monthly="300.00")  # 500 / 300 covers one whole month
    response = api.call("GET", "/buffer")
    assert response.status_code == 200
    assert response.json() == {
        "balance": "500.00",
        "monthly_total": "300.00",
        "months_covered": 1,
    }


@pytest.mark.parametrize(
    ("monthly", "months", "covered"),
    [("100.00", 30, 5), ("100.01", 30, 4), ("500.00", 6, 1), ("500.01", 6, 0)],
)
def test_BF_01_months_covered_is_the_floor(
    api: Api, monthly: str, months: int, covered: int
) -> None:
    save(api, "500.00", months=months, monthly=monthly)
    assert api.call("GET", "/buffer").json()["months_covered"] == covered


def test_BF_01_nothing_owed_gives_null_months(api: Api) -> None:
    opt_in(api.session)
    api.session.add(UserBalance(user_id=USER, savings_balance=Decimal("0.00")))
    assert api.call("GET", "/buffer").json() == {
        "balance": "0.00",
        "monthly_total": "0.00",
        "months_covered": None,
    }


def test_BF_01_user_who_never_saved_has_zero_buffer(api: Api) -> None:
    assert api.call("GET", "/buffer").json()["balance"] == "0.00"


@pytest.mark.parametrize("user", [None, ""])
def test_BF_01_buffer_without_a_user_is_401(api: Api, user: str | None) -> None:
    assert api.call("GET", "/buffer", user=user).status_code == 401
    assert move(api, "1.00", user=user).status_code == 401


# --- BF-02, BF-03: amount against the balance -----------------------------------------


def test_BF_02_moving_part_of_the_buffer(api: Api) -> None:
    save(api)
    response = move(api, "120.50")

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["amount"], body["balance"]) == ("created", "120.50", "379.50")
    assert withdrawals(api) == [Decimal("120.50")]
    assert stored_balance(api) == Decimal("379.50")
    assert api.bank.get_balance(USER) == OPENING - Decimal("500.00") + Decimal("120.50")
    assert check_user_invariants(api.session, USER) == []  # INV-1, INV-2
    [audit] = api.session.execute(
        select(AuditLog).where(AuditLog.action == "buffer_moved_to_main")
    ).scalars()
    assert (audit.user_id, audit.actor, audit.ref_id) == (USER, "user", body["transaction_id"])


def test_BF_02_moving_exactly_the_balance_empties_it(api: Api) -> None:
    # 05 SV-04: always allowed, never blocked; the buffer ends at 0.00.
    save(api)
    response = move(api, "500.00")
    assert response.status_code == 201
    assert response.json()["balance"] == "0.00"
    assert stored_balance(api) == Decimal("0.00")
    assert api.bank.get_balance(USER) == OPENING
    assert check_user_invariants(api.session, USER) == []


def test_BF_02_not_blocked_by_the_main_account_safety_net(api: Api) -> None:
    # The 500.00 safety net protects the main account from saving; moving money
    # back into it is never held back, however low it is.
    save(api)
    api.bank.set_balance(USER, Decimal("0.00"))
    assert move(api, "500.00").status_code == 201
    assert api.bank.get_balance(USER) == Decimal("500.00")


@pytest.mark.parametrize("amount", ["500.01", "9999999999.99"])
def test_BF_03_more_than_the_balance_is_422_and_moves_nothing(api: Api, amount: str) -> None:
    # 05 SV-05: refused, not blocked: there is not that much to move.
    save(api)
    response = move(api, amount)

    assert response.status_code == 422
    assert response.json() == ABOVE_BALANCE
    assert withdrawals(api) == []
    assert stored_balance(api) == Decimal("500.00")
    assert api.bank.get_balance(USER) == OPENING - Decimal("500.00")


def test_BF_03_user_who_never_saved_cannot_move_and_nothing_is_written(api: Api) -> None:
    response = move(api, "0.01")
    assert response.status_code == 422
    assert response.json() == ABOVE_BALANCE
    count = api.session.execute(select(func.count()).select_from(UserBalance)).scalar_one()
    assert count == 0


def test_BF_03_a_rejected_request_id_can_be_used_again(api: Api) -> None:
    save(api)
    assert move(api, "600.00").status_code == 422
    assert move(api, "200.00").status_code == 201  # nothing was stored for move-1


# --- BF-04: validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [b'"0"', b'"0.00"', b'"-1.00"', b'"1.234"', b"5", b"5.0", b"null", b'"abc"'],
)
def test_BF_04_bad_amounts_rejected(api: Api, raw: bytes) -> None:
    save(api)
    body = b'{"client_request_id": "move-1", "amount": ' + raw + b"}"
    assert api.call("POST", "/buffer/move-to-main", body).status_code == 422
    assert withdrawals(api) == []


@pytest.mark.parametrize(
    "body",
    [
        {"amount": "1.00"},
        {"client_request_id": "move-1"},
        {"client_request_id": "", "amount": "1.00"},
        {"client_request_id": "a\nb", "amount": "1.00"},
        {"client_request_id": "move-1", "amount": "1.00", "extra": 1},
    ],
)
def test_BF_04_bad_bodies_rejected(api: Api, body: dict[str, Any]) -> None:
    save(api)
    assert api.call("POST", "/buffer/move-to-main", body).status_code == 422


# --- BF-05, BF-08: the same request again ---------------------------------------------


def test_BF_05_sequential_double_submit_moves_once(api: Api) -> None:
    save(api)
    first = move(api, "100.00")
    second = move(api, "100.00")

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json() | {"status": "duplicate"}
    assert withdrawals(api) == [Decimal("100.00")]
    assert stored_balance(api) == Decimal("400.00")
    assert api.bank.get_balance(USER) == OPENING - Decimal("400.00")  # credited once


def test_BF_05_repeat_of_a_move_that_emptied_the_buffer_still_gets_200(api: Api) -> None:
    # The request is matched before the balance: the repeat is not "above balance".
    save(api)
    first = move(api, "500.00")
    again = move(api, "500.00")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["transaction_id"] == first.json()["transaction_id"]
    assert withdrawals(api) == [Decimal("500.00")]


def test_BF_05_request_ids_are_per_user(api: Api) -> None:
    save(api)
    assert move(api, "100.00").status_code == 201
    assert move(api, "100.00", user="user_b").status_code == 422  # user_b's own buffer
    assert withdrawals(api) == [Decimal("100.00")]


def test_BF_08_same_request_id_with_another_amount_conflicts(api: Api) -> None:
    save(api)
    first = move(api, "100.00")
    response = move(api, "150.00")

    assert response.status_code == 409
    assert withdrawals(api) == [Decimal("100.00")]
    [reused] = api.session.execute(
        select(AuditLog).where(AuditLog.action == "client_request_id_reused")
    ).scalars()
    assert (reused.user_id, reused.ref_id) == (USER, first.json()["transaction_id"])


# --- BF-11: a move may name the month it prepares (Session 17) ---------------------------


def move_for(api: Api, amount: str, for_month: Any, request_id: str = "move-1") -> Any:
    body = {"client_request_id": request_id, "amount": amount, "for_month": for_month}
    return api.call("POST", "/buffer/move-to-main", body)


def stored_months(api: Api) -> list[date | None]:
    return list(
        api.session.execute(
            select(SavingsTransaction.for_month)
            .where(SavingsTransaction.type == "withdrawal")
            .order_by(SavingsTransaction.created_at, SavingsTransaction.id)
        ).scalars()
    )


def test_BF_11_for_month_is_stored_and_echoed(api: Api) -> None:
    save(api)
    response = move_for(api, "100.00", "2026-12")
    assert response.status_code == 201
    assert response.json()["for_month"] == "2026-12"
    assert stored_months(api) == [date(2026, 12, 1)]
    [audit] = api.session.execute(
        select(AuditLog).where(AuditLog.action == "buffer_moved_to_main")
    ).scalars()
    assert audit.detail["for_month"] == "2026-12"


@pytest.mark.parametrize("body_month", [None, "absent"])
def test_BF_11_without_for_month_it_is_a_free_move(api: Api, body_month: str | None) -> None:
    save(api)
    response = move(api, "100.00") if body_month == "absent" else move_for(api, "100.00", None)
    assert response.status_code == 201
    assert response.json()["for_month"] is None
    assert stored_months(api) == [None]


def test_BF_11_any_month_is_accepted_it_never_blocks_the_move(api: Api) -> None:
    # L66: the month is a label. A past month, or one within budget, moves the money.
    save(api)
    assert move_for(api, "100.00", "2020-01", "move-a").status_code == 201
    assert move_for(api, "100.00", "2099-12", "move-b").status_code == 201
    assert stored_balance(api) == Decimal("300.00")


def test_BF_11_the_same_request_with_the_same_month_moves_once(api: Api) -> None:
    save(api)
    first = move_for(api, "100.00", "2026-12")
    again = move_for(api, "100.00", "2026-12")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json() | {"status": "duplicate"}
    assert stored_months(api) == [date(2026, 12, 1)]
    assert api.bank.get_balance(USER) == OPENING - Decimal("400.00")  # credited once


@pytest.mark.parametrize(
    ("first_month", "second_month"),
    [("2026-12", "2027-01"), ("2026-12", None), (None, "2026-12")],
    ids=["another_month", "month_dropped", "month_added"],
)
def test_BF_11_the_same_request_id_with_another_month_conflicts(
    api: Api, first_month: str | None, second_month: str | None
) -> None:
    save(api)
    first = move_for(api, "100.00", first_month)
    response = move_for(api, "100.00", second_month)

    assert (first.status_code, response.status_code) == (201, 409)
    assert withdrawals(api) == [Decimal("100.00")]
    assert stored_balance(api) == Decimal("400.00")
    [reused] = api.session.execute(
        select(AuditLog).where(AuditLog.action == "client_request_id_reused")
    ).scalars()
    assert (reused.user_id, reused.ref_id) == (USER, first.json()["transaction_id"])


@pytest.mark.parametrize(
    "raw",
    [
        b'"2026-13"',
        b'"2026-00"',
        b'"2026-1"',
        b'"2026-11-01"',
        b'"11-2026"',
        b'""',
        b"202611",
        b'"0000-01"',
        b'"2026-11\\n"',  # a JSON-escaped newline: control characters are refused
    ],
)
def test_BF_11_a_bad_month_is_422_and_moves_nothing(api: Api, raw: bytes) -> None:
    save(api)
    body = b'{"client_request_id": "move-1", "amount": "100.00", "for_month": ' + raw + b"}"
    response = api.call("POST", "/buffer/move-to-main", body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "for_month"
    assert withdrawals(api) == []
    assert stored_balance(api) == Decimal("500.00")


# --- BF-09: the bank moves the money at most once (S1) ----------------------------------


def test_BF_09_move_key_is_stable_per_request_and_distinct() -> None:
    key = savings.move_key(USER, "move-1")
    assert key == savings.move_key(USER, "move-1")
    assert key != savings.move_key(USER, "move-2")
    assert key != savings.move_key("user_b", "move-1")
    assert savings.move_key("a:b", "c") != savings.move_key("a", "b:c")
    assert key != savings.manual_transfer_key(USER, "move-1")  # never an auto-save's key


def test_BF_09_commit_fails_retry_credits_main_once(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The bank is called only after the commit (review round 2 F1), so a lost
    # commit moves nothing and the retry is the first move.
    save(api)
    api.session.commit()  # kept by the rollback below: only the lost request rolls back
    session = api.session
    real_commit = session.commit

    def commit_fails_once() -> None:
        monkeypatch.setattr(session, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails_once)

    lost = move(api, "200.00")
    session.rollback()  # what get_session's close does after the failed request
    assert lost.status_code == 500
    assert withdrawals(api) == []
    assert api.bank.get_balance(USER) == OPENING - Decimal("500.00")  # nothing moved

    retry = move(api, "200.00")

    assert retry.status_code == 201, retry.text
    assert api.bank.get_balance(USER) == OPENING - Decimal("300.00")  # credited once
    assert withdrawals(api) == [Decimal("200.00")]
    assert stored_balance(api) == Decimal("300.00")


def test_BF_09_lost_commit_then_another_move_never_credits_main_twice(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review round 2 F1: move "a" loses its commit, "b" then moves the whole buffer,
    and "a" is retried. The main account may only gain what the ledger withdrew."""
    save(api)  # buffer 500.00; main OPENING - 500.00
    api.session.commit()
    session = api.session
    real_commit = session.commit

    def commit_fails_once() -> None:
        monkeypatch.setattr(session, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails_once)
    assert move(api, "500.00", "a").status_code == 500
    session.rollback()

    assert move(api, "500.00", "b").status_code == 201
    retry = move(api, "500.00", "a")

    assert retry.status_code == 422  # the buffer is empty now
    credited = api.bank.get_balance(USER) - (OPENING - Decimal("500.00"))
    assert credited == sum(withdrawals(api), Decimal("0.00")) == Decimal("500.00")
    assert stored_balance(api) == Decimal("0.00")


def test_BF_09_bank_fails_after_commit_retry_credits_main_once(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The withdrawal is committed before the bank call, so a failed call leaves a
    recorded move that has not reached the main account yet. The client's retry
    (same id) gets the duplicate answer and repeats the call under the same key."""
    save(api)
    api.session.commit()
    real_transfer = api.bank.transfer_from_savings

    def bank_down_once(user_id: str, amount: Decimal, *, idempotency_key: str) -> None:
        monkeypatch.setattr(api.bank, "transfer_from_savings", real_transfer)
        raise ConnectionError("bank unavailable")

    monkeypatch.setattr(api.bank, "transfer_from_savings", bank_down_once)
    with pytest.raises(ConnectionError):
        move(api, "200.00")
    assert withdrawals(api) == [Decimal("200.00")]  # committed
    assert api.bank.get_balance(USER) == OPENING - Decimal("500.00")  # not credited yet

    retry = move(api, "200.00")

    assert retry.status_code == 200
    assert retry.json()["status"] == "duplicate"
    assert api.bank.get_balance(USER) == OPENING - Decimal("300.00")
    assert move(api, "200.00").status_code == 200  # and again: still credited once
    assert api.bank.get_balance(USER) == OPENING - Decimal("300.00")


def test_BF_05_unique_index_is_the_second_layer(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the lookup before the insert ever missed an earlier move (say the balance
    lock stopped serialising moves), ON CONFLICT still finds it: one move, and the
    repeat gets the first answer."""
    save(api)
    first = move(api, "100.00")
    real_earlier = buffer_service._earlier
    calls: list[int] = []

    def blind_once(user_id: str, client_request_id: str) -> Any:
        calls.append(1)
        return real_earlier(user_id, "no-such-request" if len(calls) == 1 else client_request_id)

    monkeypatch.setattr(buffer_service, "_earlier", blind_once)
    again = move(api, "100.00")

    assert len(calls) == 2  # the blind lookup, then the one after ON CONFLICT
    assert again.status_code == 200
    assert again.json()["transaction_id"] == first.json()["transaction_id"]
    assert withdrawals(api) == [Decimal("100.00")]


def test_RS_02_violation_rolls_back_the_whole_move(
    api: Api, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A simulated bug: the balance is debited one baht too little. Nothing of the
    move may persist and no money may move."""
    save(api)
    api.session.commit()  # kept by the rollback: only the move rolls back
    real_adjust = savings.adjust_balance
    monkeypatch.setattr(
        savings,
        "adjust_balance",
        lambda session, user_id, delta: real_adjust(session, user_id, delta + Decimal(1)),
    )
    with caplog.at_level(logging.ERROR), pytest.raises(InvariantViolationError) as exc:
        move(api, "100.00")

    assert exc.value.violations == ["INV-1"]
    assert withdrawals(api) == []
    assert stored_balance(api) == Decimal("500.00")
    assert api.bank.get_balance(USER) == OPENING - Decimal("500.00")
    actions = api.session.execute(select(AuditLog.action)).scalars().all()
    assert "buffer_moved_to_main" not in actions
    [record] = caplog.records
    assert "move to main rolled back" in record.getMessage()
    assert USER not in record.getMessage()  # S12
