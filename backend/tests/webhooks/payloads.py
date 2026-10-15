"""Valid webhook payloads for all six event types (04 section 5.3 plus L41, L48).

Money and rates are strings, as the contract requires. Tests copy one and change
a single field to break a single rule.
"""

import copy
import json
from typing import Any

CONTRACT: dict[str, Any] = {
    "contract_id": "ctr_88213",
    "kind": "purchase",
    "item_name": "Headphones",
    "principal": "20000.00",
    "months": 6,
    "monthly_amount": "3333.33",
    "fee_total": "0.00",
    "first_due_date": "2026-11-05",
    "min_payment": "3333.33",
    "late_fee_per_period": "100.00",
    "monthly_rate": "0.020833",
    "overdue_days": 0,
}

COMMON: dict[str, Any] = {
    "event_id": "evt_01J9ZQ7K3M",
    "occurred_at": "2026-10-12T09:30:00Z",
    "user_ref": "user_a",
}

PAYLOADS: dict[str, dict[str, Any]] = {
    "installment_created": {"event_type": "installment_created", "contract": CONTRACT},
    "cash_withdrawal_created": {
        "event_type": "cash_withdrawal_created",
        "contract": CONTRACT | {"kind": "cash_withdrawal"},
    },
    "cash_loan_created": {
        "event_type": "cash_loan_created",
        "contract": CONTRACT | {"kind": "cash_loan"},
    },
    "installment_payment_collected": {
        "event_type": "installment_payment_collected",
        "contract_id": "ctr_88213",
        "amount": "3333.33",
        "installment_no": 1,
    },
    "installment_overdue": {
        "event_type": "installment_overdue",
        "contract_id": "ctr_88213",
        "overdue_days": 3,
        "late_fees_accrued": "100.00",
    },
    "installment_cancelled": {
        "event_type": "installment_cancelled",
        "contract_id": "ctr_88213",
        "reason": "Order cancelled by buyer",
    },
}
EVENT_TYPES = list(PAYLOADS)


def payload(event_type: str = "installment_created", **overrides: Any) -> dict[str, Any]:
    """A deep copy of a valid payload, with top-level overrides applied."""
    return copy.deepcopy(COMMON | PAYLOADS[event_type]) | overrides


def with_contract(**overrides: Any) -> dict[str, Any]:
    """A valid installment_created payload with contract fields overridden."""
    data = payload()
    data["contract"] |= overrides
    return data


def raw_with(field: str, json_literal: str, base: dict[str, Any] | None = None) -> bytes:
    """JSON text with one quoted string value replaced by a raw JSON literal.

    Builds JSON numbers such as 20000.00 as text, so no Python float exists in tests.
    """
    data = base if base is not None else payload()
    text = json.dumps(data)
    value = _find(data, field)
    old = f'"{field}": {json.dumps(value)}'
    assert text.count(old) == 1, old
    return text.replace(old, f'"{field}": {json_literal}').encode()


def _find(data: dict[str, Any], field: str) -> Any:
    if field in data:
        return data[field]
    return data["contract"][field]


def encode(data: dict[str, Any]) -> bytes:
    return json.dumps(data).encode()
