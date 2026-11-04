"""MA-01 to MA-07: GET /bank/main-account, the main account balance and the movements
the system made between it and the buffer, newest first (Session 21). Read only.

The rows are written directly with a set created_at, as in NT-08: every row in one
test transaction would otherwise share now(). MA-06 goes through the real routes.
"""

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.models import SavingsTransaction
from tests.db.factories import installment, savings_tx
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

T0 = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)  # 09:00 in Bangkok
OTHER = "user_b"
KEYS = {"balance", "movements", "movements_truncated"}
MOVEMENT_KEYS = {"id", "at", "kind", "direction", "amount", "for_month"}
_unique = itertools.count()


def _add(api: Api, row: SavingsTransaction, minutes: int) -> uuid.UUID:
    row.created_at = T0 + timedelta(minutes=minutes)
    api.session.add(row)
    api.session.flush()
    return row.id


def auto_save(api: Api, minutes: int, amount: str = "40.00", user: str = USER) -> uuid.UUID:
    owned = installment(user_id=user, contract_id=f"c-{next(_unique)}")
    api.session.add(owned)
    api.session.flush()
    row = savings_tx(
        user_id=user,
        amount=Decimal(amount),
        installment_id=owned.id,
        source_vendor=None,
        source_event_id=None,
    )
    return _add(api, row, minutes)


def leftover(api: Api, minutes: int, month: date, amount: str = "300.00") -> uuid.UUID:
    row = savings_tx(
        type="leftover_save",
        amount=Decimal(amount),
        payday_month=month,
        source_vendor=None,
        source_event_id=None,
        user_id=USER,
    )
    return _add(api, row, minutes)


def withdrawal(
    api: Api,
    minutes: int,
    amount: str = "1500.00",
    *,
    for_month: date | None = None,
    user: str = USER,
) -> uuid.UUID:
    row = savings_tx(
        type="withdrawal",
        amount=Decimal(amount),
        client_request_id=f"move-{next(_unique)}",
        for_month=for_month,
        source_vendor=None,
        source_event_id=None,
        user_id=user,
    )
    return _add(api, row, minutes)


def read(api: Api, user: str | None = USER) -> Any:
    return api.call("GET", "/bank/main-account", user=user)


# --- MA-01: the response shape ---------------------------------------------------------


def test_MA_01_balance_from_the_bank_and_the_contract_keys(api: Api) -> None:
    api.bank.set_balance(USER, Decimal("9500.00"))
    saved = auto_save(api, 0)

    response = read(api)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "balance": "9500.00",
        "movements": [
            {
                "id": str(saved),
                "at": "2026-11-01T09:00:00+07:00",
                "kind": "auto_save",
                "direction": "out",
                "amount": "40.00",
                "for_month": None,
            }
        ],
        "movements_truncated": False,
    }
    assert set(body) == KEYS
    assert set(body["movements"][0]) == MOVEMENT_KEYS


def test_MA_01_a_user_never_seen_by_the_bank_opens_at_its_opening_balance(api: Api) -> None:
    assert read(api).json()["balance"] == "10000.00"


def test_MA_01_no_account_number_anywhere_in_the_body(api: Api) -> None:
    withdrawal(api, 0)
    text = read(api).text.lower()
    for word in ("account_number", "account_no", "number", "iban"):
        assert word not in text


def test_MA_01_the_bangkok_date_is_kept_across_utc_midnight(api: Api) -> None:
    # 17:30 UTC on Oct 31 is already Nov 1 in Bangkok: the screen reads the date part.
    row = savings_tx(
        type="withdrawal",
        amount=Decimal("10.00"),
        client_request_id="late",
        source_vendor=None,
        source_event_id=None,
        user_id=USER,
    )
    row.created_at = datetime(2026, 10, 31, 17, 30, tzinfo=UTC)
    api.session.add(row)
    api.session.flush()
    assert read(api).json()["movements"][0]["at"] == "2026-11-01T00:30:00+07:00"


# --- MA-02: newest first ---------------------------------------------------------------


def test_MA_02_newest_first(api: Api) -> None:
    first = auto_save(api, 0)
    second = withdrawal(api, 10)
    third = leftover(api, 20, date(2026, 11, 1))

    listed = [m["id"] for m in read(api).json()["movements"]]

    assert listed == [str(third), str(second), str(first)]


def test_MA_02_movements_at_the_same_instant_keep_one_order(api: Api) -> None:
    ids = [withdrawal(api, 0, "10.00"), auto_save(api, 0), withdrawal(api, 0, "20.00")]
    listed = [m["id"] for m in read(api).json()["movements"]]
    assert listed == sorted((str(i) for i in ids), reverse=True)


# --- MA-03: at most 20 -----------------------------------------------------------------


def test_MA_03_lists_the_20_newest_and_says_there_are_more(api: Api) -> None:
    ids = [withdrawal(api, minutes, "10.00") for minutes in range(25)]

    body = read(api).json()

    assert [m["id"] for m in body["movements"]] == [str(i) for i in reversed(ids[5:])]
    assert body["movements_truncated"] is True


def test_MA_03_exactly_20_is_not_truncated(api: Api) -> None:
    for minutes in range(20):
        withdrawal(api, minutes, "10.00")
    body = read(api).json()
    assert len(body["movements"]) == 20
    assert body["movements_truncated"] is False


def test_MA_03_21_is_truncated_by_one(api: Api) -> None:
    for minutes in range(21):
        withdrawal(api, minutes, "10.00")
    body = read(api).json()
    assert len(body["movements"]) == 20
    assert body["movements_truncated"] is True


# --- MA-04: only the caller's own account (critical) -----------------------------------


def test_MA_04_each_user_sees_only_their_own_movements_and_balance(api: Api) -> None:
    api.bank.set_balance(USER, Decimal("9500.00"))
    api.bank.set_balance(OTHER, Decimal("123.45"))
    mine = auto_save(api, 0)
    theirs = [withdrawal(api, minutes, user=OTHER) for minutes in (5, 10)]
    auto_save(api, 15, user=OTHER)

    me = read(api).json()
    them = read(api, OTHER).json()

    assert me["balance"] == "9500.00"
    assert [m["id"] for m in me["movements"]] == [str(mine)]
    assert them["balance"] == "123.45"
    assert len(them["movements"]) == 3
    assert {m["id"] for m in them["movements"]} >= {str(i) for i in theirs}
    assert str(mine) not in {m["id"] for m in them["movements"]}


def test_MA_04_another_users_movements_never_count_toward_the_cap(api: Api) -> None:
    withdrawal(api, 0, "10.00")
    for minutes in range(1, 30):
        withdrawal(api, minutes, "10.00", user=OTHER)
    body = read(api).json()
    assert len(body["movements"]) == 1
    assert body["movements_truncated"] is False


# --- MA-05: kind and direction per type (critical) -------------------------------------


def test_MA_05_direction_and_month_per_kind(api: Api) -> None:
    auto_save(api, 0, "40.00")
    leftover(api, 10, date(2026, 10, 1), "300.00")
    withdrawal(api, 20, "1500.00", for_month=date(2026, 11, 1))
    withdrawal(api, 30, "200.00")  # a free move

    listed = [
        (m["kind"], m["direction"], m["amount"], m["for_month"])
        for m in read(api).json()["movements"]
    ]

    assert listed == [
        ("withdrawal", "in", "200.00", None),
        ("withdrawal", "in", "1500.00", "2026-11"),
        ("leftover_save", "out", "300.00", "2026-10"),
        ("auto_save", "out", "40.00", None),
    ]


def test_MA_05_amounts_are_always_positive_strings(api: Api) -> None:
    auto_save(api, 0, "0.01")
    withdrawal(api, 10, "99999.99")
    for m in read(api).json()["movements"]:
        assert isinstance(m["amount"], str)
        assert not m["amount"].startswith("-")
        assert Decimal(m["amount"]) > 0


# --- MA-06: through the real routes ----------------------------------------------------


def test_MA_06_a_saving_and_a_move_to_main_appear_with_the_bank_balance(api: Api) -> None:
    opt_in(api.session, fixed="500.00")
    recorded = api.call(
        "POST",
        "/installments",
        {
            "client_request_id": "entry-1",
            "kind": "purchase",
            "item_price": "3000.00",
            "months": 10,
            "monthly_amount": "300.00",
            "first_due_month": "2026-11",
        },
    )
    assert recorded.status_code == 201
    after_save = read(api).json()
    assert after_save["balance"] == "9500.00"
    assert [(m["kind"], m["direction"], m["amount"]) for m in after_save["movements"]] == [
        ("auto_save", "out", "500.00")
    ]

    moved = api.call(
        "POST",
        "/buffer/move-to-main",
        {"client_request_id": "move-1", "amount": "200.00", "for_month": "2026-12"},
    )
    assert moved.status_code == 201
    # Both rows share the test transaction's now(), so look them up by kind.
    body = read(api).json()
    rows = {m["kind"]: m for m in body["movements"]}

    assert body["balance"] == "9700.00"
    assert rows["withdrawal"]["direction"] == "in"
    assert rows["withdrawal"]["amount"] == "200.00"
    assert rows["withdrawal"]["for_month"] == "2026-12"
    assert rows["withdrawal"]["id"] == moved.json()["transaction_id"]
    assert len(body["movements"]) == 2


def test_MA_06_reading_twice_moves_nothing(api: Api) -> None:
    withdrawal(api, 0)
    first = read(api).json()
    assert read(api).json() == first
    assert api.bank.get_balance(USER) == Decimal("10000.00")


# --- MA-07: no user, an empty account --------------------------------------------------


@pytest.mark.parametrize("user", [None, "", "a\x01b", "x" * 129])
def test_MA_07_no_or_malformed_user_is_401(api: Api, user: str | None) -> None:
    response = read(api, user)
    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_MA_07_an_account_with_no_movements(api: Api) -> None:
    assert read(api).json() == {
        "balance": "10000.00",
        "movements": [],
        "movements_truncated": False,
    }
