"""verify() without HTTP: each check in isolation, plus where the secret comes from."""

import hashlib
import hmac
import secrets
from typing import Any

import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.webhooks.signature import SignatureError, get_now, get_vendor_secrets, sign, verify

SECRET = secrets.token_hex(32)
NOW = 1_791_000_000
BODY = b'{"event_id": "e1"}'


def call(**overrides: Any) -> str:
    ts = str(overrides.pop("now_offset", 0) + NOW)
    args: dict[str, Any] = {
        "secrets": {"shopdemo": SecretStr(SECRET)},
        "vendor": "shopdemo",
        "timestamp": ts,
        "signature": sign(SECRET, ts, BODY),
        "body": BODY,
        "now": NOW,
    }
    return verify(**(args | overrides))


def test_valid_signature_returns_vendor() -> None:
    assert call() == "shopdemo"


def test_signature_covers_timestamp_dot_raw_body() -> None:
    # 04 5.2: hex(HMAC_SHA256(secret, timestamp + "." + raw_body)), computed here
    # independently with the stdlib, not through sign().
    expected = hmac.new(SECRET.encode(), f"{NOW}.".encode() + BODY, hashlib.sha256).hexdigest()
    assert sign(SECRET, str(NOW), BODY) == expected


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"vendor": None}, "missing header"),
        ({"timestamp": None}, "missing header"),
        ({"signature": None}, "missing header"),
        ({"vendor": "unknown"}, "unknown vendor"),
        ({"secrets": {"shopdemo": None}}, "unknown vendor"),
        ({"secrets": {"shopdemo": SecretStr("")}}, "unknown vendor"),
        ({"timestamp": "abc"}, "malformed timestamp"),
        ({"timestamp": "١٧٩"}, "malformed timestamp"),  # Arabic-Indic digits
        ({"now": NOW + 301}, "outside window"),
        ({"now": NOW - 301}, "outside window"),
        ({"signature": "A" * 64}, "malformed signature"),
        ({"signature": "0" * 64}, "bad signature"),
        ({"body": BODY + b" "}, "bad signature"),
    ],
)
def test_each_check_rejects(overrides: dict[str, Any], reason: str) -> None:
    with pytest.raises(SignatureError, match=reason):
        call(**overrides)


@pytest.mark.parametrize("offset", [-300, 300])
def test_window_is_inclusive_at_300_seconds(offset: int) -> None:
    assert call(now=NOW + offset) == "shopdemo"


def test_vendor_secrets_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    value = secrets.token_hex(32)
    monkeypatch.setenv("WEBHOOK_SECRET_SHOPDEMO", value)
    get_settings.cache_clear()
    try:
        secret = get_vendor_secrets()["shopdemo"]
        assert secret is not None
        assert secret.get_secret_value() == value
        assert value not in repr(secret)  # SecretStr never prints its value
    finally:
        get_settings.cache_clear()


def test_get_now_is_unix_seconds() -> None:
    assert isinstance(get_now(), int)
    assert get_now() > NOW - 10**8
