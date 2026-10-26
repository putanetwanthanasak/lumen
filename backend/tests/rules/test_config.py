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


def with_safety_net(value: str) -> str:
    data = shipped()
    data["safety_net"]["protected_min_balance"] = value
    return json.dumps(data)


def test_shipped_rules_load_as_decimal() -> None:
    rules = load_rules()
    # The safety net stays fixed under L63. A change here is a spec change.
    assert rules.safety_net.protected_min_balance == Decimal("500.00")
    assert type(rules.safety_net.protected_min_balance) is Decimal
    assert set(rules.alerts.strong_alert_kinds) == {"cash_withdrawal", "cash_loan"}


def test_load_rules_is_cached() -> None:
    assert load_rules() is load_rules()


def test_rules_are_frozen() -> None:
    with pytest.raises(ValidationError):
        load_rules().safety_net.protected_min_balance = Decimal("0.00")  # type: ignore[misc]


@pytest.mark.parametrize(
    "auto_save",
    [
        {"rate": "0.10", "min_saving": "10.00", "max_saving": "500.00"},  # L46 + L52
        {"default_rate": "0.05", "default_per_item_cap": "100.00"},  # the 5% shape
    ],
)
def test_L63_global_saving_rule_rejected(auto_save: dict[str, str]) -> None:
    # L63: the saving rule is the user's own. A global rule in rules.json must not
    # load silently and look as if it still applied.
    data = shipped() | {"auto_save": auto_save}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_rules(json.dumps(data))


def test_L49_json_number_instead_of_string_rejected() -> None:
    # Unquote the value in the JSON text to make it a JSON number (no Python float).
    raw = RULES_PATH.read_text().replace(
        '"protected_min_balance": "500.00"', '"protected_min_balance": 500.00'
    )
    assert raw != RULES_PATH.read_text()
    with pytest.raises(ValidationError, match="must be a JSON string"):
        parse_rules(raw)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        # Shared parser (app.money): one message for every malformed string.
        ("five hundred", "plain decimal string"),
        ("NaN", "plain decimal string"),
        ("Infinity", "plain decimal string"),
        ("500.001", "at most 2 decimal places"),
    ],
)
def test_L49_bad_decimal_strings_rejected(value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_rules(with_safety_net(value))


def test_unknown_key_rejected() -> None:
    data = shipped()
    data["safety_net"]["per_user_min"] = "100.00"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_rules(json.dumps(data))


def test_negative_protected_min_rejected() -> None:
    # No sign is allowed by the money pattern, so negatives fail at parse time.
    with pytest.raises(ValidationError, match="plain decimal string"):
        parse_rules(with_safety_net("-1.00"))


@pytest.mark.parametrize("attempts", [0, "3", True])
def test_push_max_attempts_must_be_positive_int(attempts: object) -> None:
    data = shipped()
    data["alerts"]["push_max_attempts"] = attempts
    with pytest.raises(ValidationError):
        parse_rules(json.dumps(data))


def test_decimal_places_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        decimal_places(Decimal("NaN"))
