"""PV-01 to PV-04: saving_if_recorded on POST /installments/preview equals the
saved_amount POST /installments reports for the same body (L63 rule, the 500.00
safety net, the kind), and the preview writes nothing."""

from decimal import Decimal
from typing import Any

import pytest

from tests.affordability.test_preview import entry, preview, record, row_counts
from tests.processing.conftest import opt_in
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db


def preview_then_record(api: Api, data: dict[str, Any]) -> tuple[str, str]:
    previewed = preview(api, data)
    assert previewed.status_code == 200
    recorded = record(api, data)
    assert recorded.status_code == 201
    return previewed.json()["saving_if_recorded"], recorded.json()["saved_amount"]


# --- PV-01: the same rule as recording ----------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "price", "expected"),
    [
        ({"percent": 10}, "6000.00", "600.00"),
        ({"percent": 7}, "1234.56", "86.41"),  # 86.4192 rounded DOWN (L63 a)
        ({"percent": 1}, "0.99", "0.00"),  # 0.0099 rounds down to 0.00: skipped
        ({"percent": 100}, "2500.00", "2500.00"),
        ({"fixed": "250.00"}, "6000.00", "250.00"),  # per installment, whatever the price
        ({"fixed": "0.01"}, "6000.00", "0.01"),
    ],
)
def test_PV_01_preview_saving_equals_the_recorded_saving(
    api: Api, rule: dict[str, Any], price: str, expected: str
) -> None:
    opt_in(api.session, **rule)
    data = entry(item_price=price, monthly_amount="100.00", months=1)
    assert preview_then_record(api, data) == (expected, expected)


# --- PV-02: the 500.00 safety net ----------------------------------------------------------


@pytest.mark.parametrize(
    ("bank", "expected"),
    [
        ("1100.00", "600.00"),  # leaves exactly 500.00: allowed (L63)
        ("1099.99", "0.00"),  # would leave 499.99: the whole saving is skipped
        ("600.00", "0.00"),
        ("100000.00", "600.00"),
    ],
)
def test_PV_02_safety_net_applies_to_the_preview_as_to_recording(
    api: Api, bank: str, expected: str
) -> None:
    opt_in(api.session)
    api.bank.set_balance(USER, Decimal(bank))
    assert preview_then_record(api, entry()) == (expected, expected)


def test_PV_02_preview_reads_the_balance_now(api: Api) -> None:
    opt_in(api.session)
    api.bank.set_balance(USER, Decimal("1100.00"))
    assert preview(api, entry()).json()["saving_if_recorded"] == "600.00"
    api.bank.set_balance(USER, Decimal("1099.99"))
    assert preview(api, entry()).json()["saving_if_recorded"] == "0.00"


# --- PV-03: what never saves ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "kind"),
    [
        ({}, "cash_withdrawal"),
        ({}, "cash_loan"),
        ({"enabled": False}, "purchase"),
        ({"consent": False}, "purchase"),
    ],
    ids=["cash_withdrawal", "cash_loan", "auto_save_off", "no_consent"],
)
def test_PV_03_cash_kinds_and_auto_save_off_save_nothing(
    api: Api, settings: dict[str, Any], kind: str
) -> None:
    opt_in(api.session, **settings)
    assert preview_then_record(api, entry(kind=kind)) == ("0.00", "0.00")


def test_PV_03_saving_is_shown_even_when_the_verdict_is_red(api: Api) -> None:
    # Advice only (rule 6): the saving does not depend on the verdict.
    opt_in(api.session)
    body = preview(api, entry(monthly_amount="10000.01", item_price="30000.03")).json()
    assert (body["verdict"], body["saving_if_recorded"]) == ("RED", "3000.00")


# --- PV-04: a request already recorded, and nothing written ---------------------------------


def test_PV_04_a_recorded_request_previews_its_first_saving(api: Api) -> None:
    opt_in(api.session)
    assert record(api, entry()).json()["saved_amount"] == "600.00"
    # The bank now could not pass the safety net, but recording again moves nothing:
    # POST reports the first saving, and so does the preview.
    api.bank.set_balance(USER, Decimal("0.00"))
    assert preview(api, entry()).json()["saving_if_recorded"] == "600.00"
    assert record(api, entry()).json()["saved_amount"] == "600.00"


def test_PV_04_a_reused_request_id_with_other_fields_previews_nothing(api: Api) -> None:
    opt_in(api.session)
    record(api, entry())
    other = entry(item_price="9000.00")
    assert preview(api, other).json()["saving_if_recorded"] == "0.00"
    assert record(api, other).status_code == 409  # POST saves nothing either


def test_PV_04_another_users_request_id_does_not_count(api: Api) -> None:
    opt_in(api.session)
    opt_in(api.session, "user_b")
    record(api, entry(), user="user_b")
    assert preview(api, entry()).json()["saving_if_recorded"] == "600.00"


def test_PV_04_preview_with_a_saving_writes_nothing(api: Api) -> None:
    opt_in(api.session)
    before = row_counts(api)
    assert preview(api, entry()).json()["saving_if_recorded"] == "600.00"
    api.session.expire_all()
    assert row_counts(api) == before
    assert api.bank.get_balance(USER) == Decimal("10000.00")
