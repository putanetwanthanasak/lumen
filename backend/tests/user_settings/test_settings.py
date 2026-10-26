"""ST-xx: /settings (L63 saving rule, L64 budget warning). 05 has no IDs for this,
so ST-01 to ST-15 are new (Session 12; ST-13 to ST-15 live in tests/db and tests/processing)."""

import json
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app.models import UserSettings
from app.user_settings import service
from app.user_settings.schemas import BUDGET_ABOVE_ONE_THIRD_OF_INCOME, budget_warnings
from tests.user_settings.conftest import USER, Api

pytestmark = pytest.mark.db

PERCENT = {"mode": "percent", "percent": 10}
FIXED = {"mode": "fixed", "amount": "50.00"}


def body(**overrides: Any) -> dict[str, Any]:
    return {
        "income": "30000.00",
        "payday": 25,
        "monthly_installment_budget": "9000.00",
        "saving_rule": PERCENT,
        "auto_save_enabled": True,
        "auto_save_consent": True,
        "leftover_saving_enabled": False,
    } | overrides


def _encode(data: dict[str, Any]) -> bytes:
    return json.dumps(data).encode()


def stored(api: Api, user: str = USER) -> UserSettings | None:
    api.session.expire_all()
    return api.session.execute(
        select(UserSettings).where(UserSettings.user_id == user)
    ).scalar_one_or_none()


def assert_422(api: Api, data: Any, method: str = "POST") -> list[dict[str, Any]]:
    response = api.call(method, "/settings", data)
    assert response.status_code == 422, response.text
    detail: list[dict[str, Any]] = response.json()["detail"]
    assert all(set(error) == {"type", "loc"} for error in detail)  # R5: no msg, no input
    return detail


# --- ST-01: create and read -----------------------------------------------------


def test_ST_01_create_then_read_round_trip(api: Api) -> None:
    created = api.call("POST", "/settings", body())
    assert created.status_code == 201
    expected = {
        "income": "30000.00",
        "payday": 25,
        "monthly_installment_budget": "9000.00",
        "saving_rule": {"mode": "percent", "percent": 10},
        "auto_save_enabled": True,
        "leftover_saving_enabled": False,
        "warnings": [],
    }
    assert {k: v for k, v in created.json().items() if k != "consent_at"} == expected
    assert created.json()["consent_at"] is not None

    read = api.call("GET", "/settings")
    assert read.status_code == 200
    assert read.json() == created.json()


def test_ST_01_money_is_stored_as_decimal(api: Api) -> None:
    api.call("POST", "/settings", body(saving_rule=FIXED, leftover_saving_enabled=True))
    row = stored(api)
    assert row is not None
    assert (row.income, row.monthly_installment_budget, row.saving_fixed_amount) == (
        Decimal("30000.00"),
        Decimal("9000.00"),
        Decimal("50.00"),
    )
    assert type(row.saving_fixed_amount) is Decimal
    assert (row.saving_mode, row.saving_percent, row.leftover_saving_enabled) == (
        "fixed",
        None,
        True,
    )


def test_ST_01_settings_are_per_user(api: Api) -> None:
    api.call("POST", "/settings", body())
    assert api.call("GET", "/settings", user="user_b").status_code == 404


# --- ST-02 to ST-05: the rule values --------------------------------------------


@pytest.mark.parametrize("percent", [1, 100])
def test_ST_02_percent_bounds_accepted(api: Api, percent: int) -> None:
    rule = {"mode": "percent", "percent": percent}
    response = api.call("POST", "/settings", body(saving_rule=rule))
    assert response.status_code == 201
    assert response.json()["saving_rule"] == rule


@pytest.mark.parametrize(
    "raw",
    [b"0", b"101", b"-1", b"10.5", b"10.0", b'"10"', b"true", b"null"],
)
def test_ST_03_bad_percent_rejected(api: Api, raw: bytes) -> None:
    data = body(saving_rule={"mode": "percent", "percent": "@"})
    encoded = _encode(data).replace(b'"@"', raw)
    detail = assert_422(api, encoded)
    assert any("percent" in error["loc"] for error in detail)
    assert stored(api) is None


def test_ST_04_smallest_fixed_amount_accepted(api: Api) -> None:
    rule = {"mode": "fixed", "amount": "0.01"}
    response = api.call("POST", "/settings", body(saving_rule=rule))
    assert response.status_code == 201
    assert response.json()["saving_rule"] == rule


@pytest.mark.parametrize(
    "raw",
    [b'"0"', b'"0.00"', b'"-1.00"', b'"1.234"', b"5", b"5.00", b'"5e2"', b'" 5.00"', b"null"],
)
def test_ST_05_bad_fixed_amount_rejected(api: Api, raw: bytes) -> None:
    # L49: money is a JSON string with at most 2 places; never rounded or coerced.
    data = body(saving_rule={"mode": "fixed", "amount": "@"})
    detail = assert_422(api, _encode(data).replace(b'"@"', raw))
    assert any("amount" in error["loc"] for error in detail)
    assert stored(api) is None


# --- ST-06 and ST-07: one mode only ---------------------------------------------


@pytest.mark.parametrize(
    "rule",
    [
        {"mode": "percent", "percent": 10, "amount": "50.00"},
        {"mode": "fixed", "amount": "50.00", "percent": 10},
        {"mode": "percent", "percent": 10, "amount": None},
        {"mode": "both", "percent": 10, "amount": "50.00"},
        {"percent": 10, "amount": "50.00"},
        {"mode": "fixed", "percent": 10},  # the value of the wrong mode
    ],
)
def test_ST_06_both_modes_rejected(api: Api, rule: dict[str, Any]) -> None:
    assert_422(api, body(saving_rule=rule))
    assert stored(api) is None


def test_ST_06_both_modes_rejected_on_update(api: Api) -> None:
    api.call("POST", "/settings", body())
    assert_422(api, body(saving_rule={"mode": "fixed", "amount": "5.00", "percent": 10}), "PUT")
    row = stored(api)
    assert row is not None
    assert (row.saving_mode, row.saving_percent, row.saving_fixed_amount) == ("percent", 10, None)


def test_ST_07_switching_mode_clears_the_other_value(api: Api) -> None:
    api.call("POST", "/settings", body(saving_rule=PERCENT))

    to_fixed = api.call("PUT", "/settings", body(saving_rule=FIXED))
    assert to_fixed.status_code == 200
    assert to_fixed.json()["saving_rule"] == FIXED
    row = stored(api)
    assert row is not None
    assert (row.saving_mode, row.saving_percent, row.saving_fixed_amount) == (
        "fixed",
        None,
        Decimal("50.00"),
    )

    back = api.call("PUT", "/settings", body(saving_rule={"mode": "percent", "percent": 3}))
    assert back.json()["saving_rule"] == {"mode": "percent", "percent": 3}
    row = stored(api)
    assert row is not None
    assert (row.saving_mode, row.saving_percent, row.saving_fixed_amount) == ("percent", 3, None)


# --- ST-08 and ST-09: the one-third warning (L64) ---------------------------------


@pytest.mark.parametrize(
    ("budget", "warnings"),
    [
        ("10000.01", [BUDGET_ABOVE_ONE_THIRD_OF_INCOME]),  # budget * 3 > income
        ("10000.00", []),  # exactly one third: no warning
        ("9999.99", []),
        ("0.00", []),
    ],
)
def test_ST_08_budget_above_one_third_warns(api: Api, budget: str, warnings: list[str]) -> None:
    response = api.call("POST", "/settings", body(monthly_installment_budget=budget))
    assert response.status_code == 201
    assert response.json()["warnings"] == warnings
    assert api.call("GET", "/settings").json()["warnings"] == warnings


@pytest.mark.parametrize(
    ("income", "budget", "warns"),
    [
        ("100.00", "33.34", True),  # 100.02 > 100.00
        ("100.00", "33.33", False),  # 99.99: below; a division would also say below
        ("0.03", "0.01", False),  # exactly a third of a tiny income
        ("0.02", "0.01", True),
        ("9999999999.99", "3333333333.33", False),  # 9999999999.99 == income
        ("9999999999.98", "3333333333.33", True),
    ],
)
def test_ST_08_warning_compares_without_division(income: str, budget: str, warns: bool) -> None:
    result = budget_warnings(income=Decimal(income), budget=Decimal(budget))
    assert result == ([BUDGET_ABOVE_ONE_THIRD_OF_INCOME] if warns else [])


def test_ST_09_warning_still_saves(api: Api) -> None:
    response = api.call("POST", "/settings", body(monthly_installment_budget="20000.00"))
    assert response.status_code == 201  # advisory only (rule 6)
    row = stored(api)
    assert row is not None
    assert row.monthly_installment_budget == Decimal("20000.00")

    update = api.call("PUT", "/settings", body(monthly_installment_budget="15000.00"))
    assert update.status_code == 200
    assert update.json()["warnings"] == [BUDGET_ABOVE_ONE_THIRD_OF_INCOME]


# --- ST-10: create, read and update semantics ------------------------------------


def test_ST_10_second_create_conflicts(api: Api) -> None:
    api.call("POST", "/settings", body())
    again = api.call("POST", "/settings", body(saving_rule=FIXED))
    assert again.status_code == 409
    row = stored(api)
    assert row is not None
    assert row.saving_mode == "percent"  # unchanged


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_ST_10_no_settings_yet_is_404(api: Api, method: str) -> None:
    response = api.call(method, "/settings", body() if method == "PUT" else None)
    assert response.status_code == 404
    assert stored(api) is None


@pytest.mark.parametrize("method", ["GET", "POST", "PUT"])
@pytest.mark.parametrize("user", [None, "", "a\nb"])
def test_ST_10_missing_or_bad_user_is_401(api: Api, method: str, user: str | None) -> None:
    response = api.call(method, "/settings", body(), user=user)
    assert response.status_code == 401


def test_ST_10_row_from_before_L63_counts_as_no_settings(api: Api) -> None:
    api.session.add(UserSettings(user_id=USER, auto_save_enabled=True))
    api.session.flush()
    assert api.call("GET", "/settings").status_code == 404
    assert api.call("PUT", "/settings", body()).status_code == 404
    assert api.call("POST", "/settings", body()).status_code == 201
    assert api.call("GET", "/settings").json()["saving_rule"] == PERCENT


# --- ST-11: other validation ------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"payday": 0},
        {"payday": 32},
        {"payday": "25"},
        {"income": "0.00"},
        {"income": "0"},
        {"income": "-100.00"},
        {"monthly_installment_budget": "-1.00"},
        {"monthly_installment_budget": "100.001"},
        {"auto_save_enabled": "true"},
        {"leftover_saving_enabled": 1},
        {"save_rate": "0.10"},  # unknown key
    ],
)
def test_ST_11_bad_fields_rejected(api: Api, overrides: dict[str, Any]) -> None:
    assert_422(api, body(**overrides))
    assert stored(api) is None


@pytest.mark.parametrize("field", ["income", "payday", "saving_rule", "auto_save_enabled"])
def test_ST_11_required_fields(api: Api, field: str) -> None:
    data = body()
    del data[field]
    assert_422(api, data)


@pytest.mark.parametrize("raw", [b"", b"[]", b"not json", b'{"income": 30000.00}'])
def test_ST_11_malformed_body_rejected(api: Api, raw: bytes) -> None:
    assert_422(api, raw)


def test_ST_11_money_as_json_number_rejected(api: Api) -> None:
    encoded = _encode(body()).replace(b'"30000.00"', b"30000.00")
    detail = assert_422(api, encoded)
    assert detail == [{"type": "value_error", "loc": ["income"]}]


def test_ST_11_oversized_body_rejected(api: Api) -> None:
    response = api.call("POST", "/settings", b" " * (64 * 1024 + 1))
    assert response.status_code == 413


# --- ST-12: consent -----------------------------------------------------------------


@pytest.mark.parametrize("consent", [None, False])
def test_ST_12_auto_save_needs_consent(api: Api, consent: bool | None) -> None:
    data = body(auto_save_consent=consent)
    if consent is None:
        del data["auto_save_consent"]
    assert_422(api, data)
    assert stored(api) is None


def test_ST_12_auto_save_off_needs_no_consent(api: Api) -> None:
    data = body(auto_save_enabled=False)
    del data["auto_save_consent"]
    response = api.call("POST", "/settings", data)
    assert response.status_code == 201
    assert response.json()["consent_at"] is None


def test_ST_12_consent_is_kept_after_turning_auto_save_off(api: Api) -> None:
    first = api.call("POST", "/settings", body()).json()["consent_at"]
    off = api.call("PUT", "/settings", body(auto_save_enabled=False, auto_save_consent=False))
    assert off.json()["consent_at"] == first
    on_again = api.call("PUT", "/settings", body())
    assert on_again.json()["consent_at"] == first  # stamped once, never moved


def test_ST_10_to_out_refuses_a_row_without_profile() -> None:
    # Callers pass configured rows only; a row from before L63 must not render half-empty.
    with pytest.raises(ValueError, match="no profile"):
        service.to_out(UserSettings(user_id=USER, auto_save_enabled=True))
