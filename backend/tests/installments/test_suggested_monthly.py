"""SM-01 to SM-03: the 0% monthly amount the "เช็กก่อนผ่อน" form suggests,
item_price / months rounded UP to 0.01 (Session 15A)."""

from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.installments.suggest import suggested_monthly
from app.money import MONEY_MAX
from tests.user_settings.conftest import USER, Api

CENT = Decimal("0.01")


# --- SM-01: rounds up, never down -------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "months", "expected"),
    [
        ("1000.00", 3, "333.34"),  # 333.333... up, so 3 payments cover the price
        ("1000.00", 4, "250.00"),  # an exact split stays exact
        ("1000.01", 2, "500.01"),  # 500.005 up, not half-even to 500.00
        ("12000.00", 9, "1333.34"),  # 1333.333... up, where nearest would give 1333.33
        ("100.00", 6, "16.67"),  # 16.666... up
        ("10.00", 3, "3.34"),  # 3.333... up, where nearest would give 3.33
        ("0.01", 600, "0.01"),  # never 0.00: a payment is at least a satang
        ("0.01", 1, "0.01"),
        ("9999999999.99", 1, "9999999999.99"),
    ],
)
def test_SM_01_rounds_up_to_the_satang(price: str, months: int, expected: str) -> None:
    result = suggested_monthly(Decimal(price), months)
    assert (result, str(result)) == (Decimal(expected), expected)


# --- SM-02: against an integer oracle ----------------------------------------------------


@settings(max_examples=1500, deadline=None)
@given(
    satang=st.integers(min_value=1, max_value=999_999_999_999),
    months=st.integers(min_value=1, max_value=600),
)
def test_SM_02_payments_cover_the_price_by_less_than_one_satang_each(
    satang: int, months: int
) -> None:
    price = Decimal(satang) / 100
    result = suggested_monthly(price, months)
    # The oracle is integer division in satang: the ceiling of satang / months.
    assert result * 100 == -(-satang // months)
    assert result.as_tuple().exponent == -2
    assert months * result >= price
    assert months * (result - CENT) < price


# --- SM-03: the endpoint -----------------------------------------------------------------


def suggest(api: Api, query: str, user: str | None = USER) -> Any:
    return api.call("GET", f"/installments/suggested-monthly{query}", user=user)


@pytest.mark.db
def test_SM_03_endpoint_answers_with_a_money_string(api: Api) -> None:
    response = suggest(api, "?item_price=1000.00&months=3")
    assert (response.status_code, response.json()) == (200, {"monthly_amount": "333.34"})
    # A whole number of baht is a plain decimal string too (L49).
    assert suggest(api, "?item_price=1200&months=12").json() == {"monthly_amount": "100.00"}


@pytest.mark.db
@pytest.mark.parametrize(
    "query",
    [
        "",
        "?item_price=1000.00",
        "?months=3",
        "?item_price=0&months=3",
        "?item_price=0.00&months=3",
        "?item_price=1000.001&months=3",  # never rounded (L49)
        "?item_price=1e3&months=3",
        "?item_price=-1000.00&months=3",
        "?item_price=%201000.00&months=3",  # a leading space
        "?item_price=1,000.00&months=3",
        "?item_price=12345678901.00&months=3",  # beyond Numeric(12,2)
        "?item_price=1000.00&months=0",
        "?item_price=1000.00&months=601",
        "?item_price=1000.00&months=1.5",
        "?item_price=1000.00&months=3.0",
        "?item_price=1000.00&months=%2B3",
        "?item_price=1000.00&months=3&months=4",
        "?item_price=1000.00&months=3&kind=purchase",
    ],
)
def test_SM_03_bad_query_is_422(api: Api, query: str) -> None:
    response = suggest(api, query)
    assert response.status_code == 422
    assert all(set(e) == {"type", "loc"} for e in response.json()["detail"])


@pytest.mark.db
def test_SM_03_a_suggestion_that_could_not_be_recorded_is_422(api: Api) -> None:
    # 9,999,999,999.99 over 600 months rounds up to 16,666,666.67, and 600 of those
    # pass MONEY_MAX, which POST /installments would refuse.
    assert 600 * suggested_monthly(MONEY_MAX, 600) > MONEY_MAX
    assert suggest(api, "?item_price=9999999999.99&months=600").status_code == 422


@pytest.mark.db
def test_SM_03_no_user_is_401(api: Api) -> None:
    assert suggest(api, "?item_price=1000.00&months=3", user=None).status_code == 401
