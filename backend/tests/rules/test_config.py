"""rules.json validation (04 section 7). Bad config must fail at load, not at use."""

import json
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.rules.config import RULES_PATH, decimal_places, load_rules, parse_rules


def shipped() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(RULES_PATH.read_text())
    return data


def with_auto_save(**overrides: Any) -> str:
    data = shipped()
    data["auto_save"] |= overrides
    return json.dumps(data)


def test_shipped_rules_load_as_decimal() -> None:
    rules = load_rules()
    a = rules.auto_save
    assert (a.default_rate, a.min_rate, a.max_rate) == (
        Decimal("0.05"),
        Decimal("0.03"),
        Decimal("0.10"),
    )
    assert a.min_saving == Decimal("10.00")
    assert a.default_per_item_cap == Decimal("100.00")
    assert rules.safety_net.protected_min_balance == Decimal("500.00")
    for value in (a.default_rate, a.min_saving, rules.safety_net.protected_min_balance):
        assert type(value) is Decimal
    assert a.applies_to_kinds == ("purchase",)
    assert set(rules.alerts.strong_alert_kinds) == {"cash_withdrawal", "cash_loan"}


def test_load_rules_is_cached() -> None:
    assert load_rules() is load_rules()


def test_rules_are_frozen() -> None:
    with pytest.raises(ValidationError):
        load_rules().auto_save.min_saving = Decimal("0.01")  # type: ignore[misc]


def test_RE_05d_config_cap_below_min_saving_rejected() -> None:
    with pytest.raises(ValidationError, match="default_per_item_cap must be >= min_saving"):
        parse_rules(with_auto_save(default_per_item_cap="5.00"))


@pytest.mark.parametrize("rate", ["0.02", "0.11"])
def test_RE_10_config_default_rate_outside_bounds_rejected(rate: str) -> None:
    with pytest.raises(ValidationError, match="default_rate must be within"):
        parse_rules(with_auto_save(default_rate=rate))


@pytest.mark.parametrize(("lo", "hi"), [("0.10", "0.03"), ("0.05", "0.05")])
def test_inverted_or_empty_rate_bounds_rejected(lo: str, hi: str) -> None:
    with pytest.raises(ValidationError, match="rate bounds inverted"):
        parse_rules(with_auto_save(min_rate=lo, max_rate=hi, default_rate=lo))


def test_non_positive_min_rate_rejected() -> None:
    with pytest.raises(ValidationError, match="min_rate must be > 0"):
        parse_rules(with_auto_save(min_rate="0.00"))


def test_non_positive_min_saving_rejected() -> None:
    with pytest.raises(ValidationError, match="min_saving must be > 0"):
        parse_rules(with_auto_save(min_saving="0.00"))


@pytest.mark.parametrize("field", ["default_rate", "min_saving"])
def test_json_number_instead_of_string_rejected(field: str) -> None:
    # Unquote the value in the JSON text to make it a JSON number (no Python float).
    value = shipped()["auto_save"][field]
    raw = RULES_PATH.read_text().replace(f'"{field}": "{value}"', f'"{field}": {value}')
    assert raw != RULES_PATH.read_text()
    with pytest.raises(ValidationError, match="must be a JSON string"):
        parse_rules(raw)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("min_saving", "ten", "not a decimal"),
        ("min_saving", "NaN", "must be finite"),
        ("min_saving", "Infinity", "must be finite"),
        ("min_saving", "10.001", "at most 2 decimal places"),
        ("default_rate", "0.0500001", "at most 6 decimal places"),
    ],
)
def test_bad_decimal_strings_rejected(field: str, value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_rules(with_auto_save(**{field: value}))


@pytest.mark.parametrize("kinds", [["purchase", "cash_withdrawal"], ["cash_loan"]])
def test_cash_kinds_never_auto_save(kinds: list[str]) -> None:
    with pytest.raises(ValidationError, match="INV-5"):
        parse_rules(with_auto_save(applies_to_kinds=kinds))


@pytest.mark.parametrize("kinds", [[], ["credit_card"]])
def test_applies_to_kinds_must_be_known_and_non_empty(kinds: list[str]) -> None:
    with pytest.raises(ValidationError):
        parse_rules(with_auto_save(applies_to_kinds=kinds))


def test_rounding_must_be_half_up() -> None:
    with pytest.raises(ValidationError):
        parse_rules(with_auto_save(rounding="ROUND_DOWN"))


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_rules(with_auto_save(max_saving="100.00"))


def test_negative_protected_min_rejected() -> None:
    data = shipped()
    data["safety_net"]["protected_min_balance"] = "-1.00"
    with pytest.raises(ValidationError, match="protected_min_balance must be >= 0"):
        parse_rules(json.dumps(data))


@pytest.mark.parametrize("attempts", [0, "3", True])
def test_push_max_attempts_must_be_positive_int(attempts: object) -> None:
    data = shipped()
    data["alerts"]["push_max_attempts"] = attempts
    with pytest.raises(ValidationError):
        parse_rules(json.dumps(data))


def test_decimal_places_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        decimal_places(Decimal("NaN"))
