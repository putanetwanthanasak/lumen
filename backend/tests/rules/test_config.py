"""rules.json validation (04 section 7). Bad config must fail at load, not at use."""

import json
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.money import decimal_places
from app.rules.config import RULES_PATH, load_rules, parse_rules


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
    # L46 + L52: the fixed rule. A change here is a spec change, not a tuning knob.
    assert (a.rate, a.min_saving, a.max_saving) == (
        Decimal("0.10"),
        Decimal("10.00"),
        Decimal("500.00"),
    )
    assert rules.safety_net.protected_min_balance == Decimal("500.00")
    for value in (a.rate, a.min_saving, a.max_saving, rules.safety_net.protected_min_balance):
        assert type(value) is Decimal
    assert a.applies_to_kinds == ("purchase",)
    assert set(rules.alerts.strong_alert_kinds) == {"cash_withdrawal", "cash_loan"}


def test_load_rules_is_cached() -> None:
    assert load_rules() is load_rules()


def test_rules_are_frozen() -> None:
    with pytest.raises(ValidationError):
        load_rules().auto_save.min_saving = Decimal("0.01")  # type: ignore[misc]


def test_max_saving_below_min_saving_rejected() -> None:
    with pytest.raises(ValidationError, match="max_saving must be >= min_saving"):
        parse_rules(with_auto_save(max_saving="9.99"))


def test_max_saving_equal_to_min_saving_allowed() -> None:
    assert parse_rules(with_auto_save(max_saving="10.00")).auto_save.max_saving == Decimal("10.00")


@pytest.mark.parametrize("rate", ["0.00", "1.01"])
def test_rate_outside_zero_to_one_rejected(rate: str) -> None:
    with pytest.raises(ValidationError, match=r"rate must be within \(0, 1\]"):
        parse_rules(with_auto_save(rate=rate))


def test_non_positive_min_saving_rejected() -> None:
    with pytest.raises(ValidationError, match="min_saving must be > 0"):
        parse_rules(with_auto_save(min_saving="0.00"))


@pytest.mark.parametrize("key", ["default_rate", "min_rate", "max_rate", "default_per_item_cap"])
def test_legacy_adjustable_rule_keys_rejected(key: str) -> None:
    # The old user-adjustable shape (5%, 3-10%, per-item cap) must not load silently.
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_rules(with_auto_save(**{key: "0.05"}))


@pytest.mark.parametrize("field", ["rate", "min_saving", "max_saving"])
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
        # Shared parser (app.money): one message for every malformed string.
        ("min_saving", "ten", "plain decimal string"),
        ("min_saving", "NaN", "plain decimal string"),
        ("min_saving", "Infinity", "plain decimal string"),
        ("rate", "-0.10", "plain decimal string"),
        ("min_saving", "10.001", "at most 2 decimal places"),
        ("max_saving", "500.001", "at most 2 decimal places"),
        ("rate", "0.1000001", "at most 6 decimal places"),
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
        parse_rules(with_auto_save(per_user_rate="0.05"))


def test_negative_protected_min_rejected() -> None:
    data = shipped()
    data["safety_net"]["protected_min_balance"] = "-1.00"
    # No sign is allowed by the money pattern, so negatives fail at parse time.
    with pytest.raises(ValidationError, match="plain decimal string"):
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
