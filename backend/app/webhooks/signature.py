"""Webhook authentication (04 section 5.2): HMAC-SHA256 plus a replay window.

The signature covers `timestamp + "." + raw body bytes`, exactly as received and
before any JSON parsing, so the bytes that are verified are the bytes that are parsed.
"""

import hashlib
import hmac
import re
import time
from collections.abc import Mapping

from pydantic import SecretStr

from app.config import get_settings

WINDOW_SECONDS = 300  # 04 5.2: reject when more than 300 s from now, in either direction
TIMESTAMP_PATTERN = re.compile(r"[0-9]{1,12}")  # Unix seconds; ASCII only, no sign
SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{64}")  # lowercase hex of SHA-256


class SignatureError(Exception):
    """Any authentication failure. The reason is for logs and tests, never the client."""


def get_vendor_secrets() -> Mapping[str, SecretStr | None]:
    """Per-vendor webhook secrets, from env only (WEBHOOK_SECRET_<VENDOR>)."""
    return {"shopdemo": get_settings().webhook_secret_shopdemo}


def get_now() -> int:
    return int(time.time())


def sign(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("ascii") + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(
    *,
    secrets: Mapping[str, SecretStr | None],
    vendor: str | None,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now: int,
) -> str:
    """Return the authenticated vendor, or raise SignatureError."""
    if vendor is None or timestamp is None or signature is None:
        raise SignatureError("missing header")
    secret = secrets.get(vendor)
    if secret is None or not secret.get_secret_value():
        raise SignatureError("unknown vendor")
    if TIMESTAMP_PATTERN.fullmatch(timestamp) is None:
        raise SignatureError("malformed timestamp")
    if abs(now - int(timestamp)) > WINDOW_SECONDS:
        raise SignatureError("timestamp outside window")
    if SIGNATURE_PATTERN.fullmatch(signature) is None:
        raise SignatureError("malformed signature")
    expected = sign(secret.get_secret_value(), timestamp, body)
    # Constant time: == would stop at the first differing byte and leak how much matched.
    if not hmac.compare_digest(expected, signature):
        raise SignatureError("bad signature")
    return vendor
