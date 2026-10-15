"""POST /webhooks/bnpl: WH-01..WH-06 (05 section 4.3) and ID-01 (05 section 4.4).

Every rejection also asserts that nothing reached the database.
"""

import json
from typing import Any

import pytest
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, WebhookEvent
from app.webhooks.router import MAX_BODY_BYTES
from app.webhooks.signature import get_vendor_secrets, sign
from tests.webhooks.conftest import NOW, OTHER_VENDOR, SECRETS, VENDOR, WRONG_SECRET, Webhook
from tests.webhooks.payloads import EVENT_TYPES, encode, payload, raw_with, with_contract

pytestmark = pytest.mark.db

PROCESSED = {"status": "processed"}
DUPLICATE = {"status": "duplicate"}
UNAUTHORIZED = {"detail": "unauthorized"}


def assert_rejected(webhook: Webhook, response: Any, status: int) -> None:
    assert response.status_code == status, response.text
    assert webhook.nothing_written()


# --- WH-01 ---------------------------------------------------------------------------


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_WH_01_valid_signature_processed(webhook: Webhook, event_type: str) -> None:
    data = payload(event_type)
    response = webhook.post(data)

    assert response.status_code == 200
    assert response.json() == PROCESSED
    row = webhook.session.execute(select(WebhookEvent)).scalar_one()
    assert (row.vendor, row.event_id, row.event_type) == (VENDOR, data["event_id"], event_type)
    assert (row.user_id, row.contract_id, row.status) == ("user_a", "ctr_88213", "processed")
    assert row.payload == data  # raw payload kept for audit and replay; money still strings
    entry = webhook.session.execute(select(AuditLog)).scalar_one()
    assert (entry.actor, entry.action) == ("system", "webhook_received")
    assert entry.ref_id == f"{VENDOR}:{data['event_id']}"
    assert entry.detail["event_type"] == event_type


# --- WH-02 ---------------------------------------------------------------------------


def _tampered_body(webhook: Webhook) -> Any:
    body = encode(payload())
    signature = sign(SECRETS[VENDOR], str(NOW), body)
    changed = body.replace(b"20000.00", b"20001.00")
    return webhook.post(changed, signature=signature)


def _tampered_timestamp(webhook: Webhook) -> Any:
    body = encode(payload())
    signature = sign(SECRETS[VENDOR], str(NOW), body)
    return webhook.post(body, timestamp=NOW - 1, signature=signature)


def _uppercase_hex(webhook: Webhook) -> Any:
    body = encode(payload())
    return webhook.post(body, signature=sign(SECRETS[VENDOR], str(NOW), body).upper())


BAD_SIGNATURES = {
    "wrong secret": lambda w: w.post(payload(), secret=WRONG_SECRET),
    "other vendor's secret": lambda w: w.post(payload(), secret=SECRETS[OTHER_VENDOR]),
    "body changed after signing": _tampered_body,
    "timestamp changed after signing": _tampered_timestamp,
    "uppercase hex": _uppercase_hex,
    "not hex": lambda w: w.post(payload(), signature="z" * 64),
    "too short": lambda w: w.post(payload(), signature="ab" * 16),
    "empty": lambda w: w.post(payload(), signature=""),
}


@pytest.mark.parametrize("case", BAD_SIGNATURES, ids=list(BAD_SIGNATURES))
def test_WH_02_bad_signature_rejected(webhook: Webhook, case: str) -> None:
    response = BAD_SIGNATURES[case](webhook)
    assert_rejected(webhook, response, 401)
    assert response.json() == UNAUTHORIZED


@pytest.mark.parametrize("header", ["X-Vendor-Id", "X-Timestamp", "X-Signature"])
def test_WH_02_missing_header_rejected(webhook: Webhook, header: str) -> None:
    assert_rejected(webhook, webhook.post(payload(), drop=header), 401)


def test_WH_02_signature_checked_before_schema(webhook: Webhook) -> None:
    # An unauthenticated sender must not learn anything from schema errors.
    response = webhook.post(b"not json", secret=WRONG_SECRET)
    assert_rejected(webhook, response, 401)


# --- WH-03 ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "timestamp", [NOW - 301, NOW + 301, NOW - 86_400, 0], ids=["old", "future", "day", "zero"]
)
def test_WH_03_timestamp_outside_window_rejected(webhook: Webhook, timestamp: int) -> None:
    assert_rejected(webhook, webhook.post(payload(), timestamp=timestamp), 401)


@pytest.mark.parametrize("timestamp", [NOW - 300, NOW + 300])
def test_WH_03_window_edges_accepted(webhook: Webhook, timestamp: int) -> None:
    # 04 5.2 rejects only *more than* 300 seconds away.
    assert webhook.post(payload(), timestamp=timestamp).status_code == 200


@pytest.mark.parametrize("timestamp", ["1.79e9", "-1", " 1791000000", "1791000000.0", ""])
def test_WH_03_malformed_timestamp_rejected(webhook: Webhook, timestamp: str) -> None:
    assert_rejected(webhook, webhook.post(payload(), timestamp=timestamp), 401)


# --- WH-04 ---------------------------------------------------------------------------


def _without(field: str) -> dict[str, Any]:
    data = payload()
    del data["contract"][field]
    return data


INVALID_PAYLOADS: dict[str, dict[str, Any] | bytes] = {
    "missing principal": _without("principal"),
    "missing L41 monthly_rate": _without("monthly_rate"),
    "negative principal": with_contract(principal="-1.00"),
    "zero principal": with_contract(principal="0.00"),
    "months = 0": with_contract(months=0),
    "months as string": with_contract(months="6"),
    "kind does not match event type": with_contract(kind="cash_loan"),
    "unknown field": payload(vendor="shopdemo"),
    "not JSON": b"{not json",
    "empty body": b"",
}


@pytest.mark.parametrize("case", INVALID_PAYLOADS, ids=list(INVALID_PAYLOADS))
def test_WH_04_invalid_payload_rejected(webhook: Webhook, case: str) -> None:
    response = webhook.post(INVALID_PAYLOADS[case])
    assert_rejected(webhook, response, 422)
    errors = response.json()["detail"]
    assert errors
    assert all("input" not in e for e in errors)  # the payload is not echoed back


# --- WH-05 (L49: one policy, reject) ------------------------------------------------


@pytest.mark.parametrize("literal", ["20000.00", "20000"])
def test_WH_05_money_as_json_number_rejected(webhook: Webhook, literal: str) -> None:
    response = webhook.post(raw_with("principal", literal))
    assert_rejected(webhook, response, 422)
    assert "must be a JSON string" in response.text


@pytest.mark.parametrize("value", ["123.455", "1e3", "1_000.00", " 1.00", "+1.00"])
def test_WH_05_bad_money_string_rejected(webhook: Webhook, value: str) -> None:
    assert_rejected(webhook, webhook.post(with_contract(principal=value)), 422)


# --- WH-06 ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", ["unknownvendor", "SHOPDEMO", ""])
def test_WH_06_unknown_vendor_rejected(webhook: Webhook, vendor: str) -> None:
    assert_rejected(webhook, webhook.post(payload(), vendor=vendor, secret=WRONG_SECRET), 401)


def test_WH_06_vendor_without_secret_rejected(webhook: Webhook) -> None:
    # A known vendor whose secret is unset must not accept an empty-key signature.
    app.dependency_overrides[get_vendor_secrets] = lambda: {VENDOR: None}
    assert_rejected(webhook, webhook.post(payload(), secret=""), 401)


# --- Body size limit -----------------------------------------------------------------


def _padded(size: int) -> bytes:
    # Trailing whitespace is valid JSON, so the body stays a valid event.
    body = encode(payload())
    return body + b" " * (size - len(body))


def test_body_at_size_limit_accepted(webhook: Webhook) -> None:
    body = _padded(MAX_BODY_BYTES)
    assert len(body) == MAX_BODY_BYTES
    assert webhook.post(body).json() == PROCESSED


def test_body_over_size_limit_rejected_before_signature(webhook: Webhook) -> None:
    body = _padded(MAX_BODY_BYTES + 1)
    response = webhook.post(body, secret=WRONG_SECRET)  # 413 wins over 401
    assert_rejected(webhook, response, 413)


# --- ID-01, L47, and event_id reuse ---------------------------------------------------


def test_ID_01_same_event_twice_processed_then_duplicate(webhook: Webhook) -> None:
    data = payload()
    assert webhook.post(data).json() == PROCESSED
    second = webhook.post(data)
    assert second.status_code == 200
    assert second.json() == DUPLICATE
    assert webhook.count(WebhookEvent) == 1
    assert webhook.count(AuditLog) == 1  # a duplicate writes nothing


def test_ID_01_duplicate_with_reordered_keys_and_spacing(webhook: Webhook) -> None:
    # The same event re-serialized differently is still the same payload.
    data = payload()
    assert webhook.post(data).json() == PROCESSED
    resent = json.dumps(dict(reversed(data.items())), indent=2).encode()
    assert webhook.post(resent).json() == DUPLICATE


def test_L47_two_vendors_reuse_event_id(webhook: Webhook) -> None:
    data = payload()
    assert webhook.post(data, vendor=VENDOR).json() == PROCESSED
    assert webhook.post(data, vendor=OTHER_VENDOR).json() == PROCESSED
    vendors = webhook.session.execute(select(WebhookEvent.vendor)).scalars().all()
    assert sorted(vendors) == [OTHER_VENDOR, VENDOR]


def test_event_id_reused_with_different_payload_conflicts(webhook: Webhook) -> None:
    original = payload()
    assert webhook.post(original).json() == PROCESSED

    response = webhook.post(with_contract(principal="99999.00"))
    assert response.status_code == 409
    assert response.json() == {"detail": "event_id reused with different payload"}

    row = webhook.session.execute(select(WebhookEvent)).scalar_one()
    assert row.payload == original  # the original row is kept
    actions = webhook.session.execute(select(AuditLog.action).order_by(AuditLog.id)).scalars()
    assert list(actions) == ["webhook_received", "webhook_event_id_reused"]
