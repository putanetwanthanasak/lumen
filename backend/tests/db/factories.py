"""Valid-by-default rows. Tests override one field to violate one rule."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Installment,
    Notification,
    SavingsTransaction,
    UserBalance,
    UserSettings,
    WebhookEvent,
)

USER = "user-1"
VENDOR = "shopdemo"


def webhook_event(**overrides: Any) -> WebhookEvent:
    fields: dict[str, Any] = {
        "vendor": VENDOR,
        "event_id": "evt-1",
        "event_type": "installment_created",
        "user_id": USER,
        "contract_id": "c-1",
        "payload": {"item_value": "800.00"},
        "status": "processed",
    }
    return WebhookEvent(**(fields | overrides))


def installment(**overrides: Any) -> Installment:
    fields: dict[str, Any] = {
        "user_id": USER,
        "vendor": VENDOR,
        "contract_id": "c-1",
        "kind": "purchase",
        "item_name": "Headphones",
        "principal": Decimal("2000.00"),
        "months": 4,
        "monthly_amount": Decimal("500.00"),
        "fee_total": Decimal("0.00"),
        "paid_amount": Decimal("0.00"),
        "late_fees_accrued": Decimal("0.00"),
        "first_due_date": date(2026, 11, 1),
        "min_payment": Decimal("500.00"),
        "late_fee_per_period": Decimal("50.00"),
        "monthly_rate": Decimal("0.000000"),
    }
    return Installment(**(fields | overrides))


def savings_tx(**overrides: Any) -> SavingsTransaction:
    fields: dict[str, Any] = {
        "user_id": USER,
        "type": "auto_save",
        "amount": Decimal("40.00"),
        "source_vendor": VENDOR,
        "source_event_id": "evt-1",
    }
    return SavingsTransaction(**(fields | overrides))


def user_balance(**overrides: Any) -> UserBalance:
    fields: dict[str, Any] = {"user_id": USER, "savings_balance": Decimal("0.00")}
    return UserBalance(**(fields | overrides))


def profile(*, percent: int | None = 10, fixed: str | None = None) -> dict[str, Any]:
    """UserSettings columns for a configured user (L63): a percent rule by default,
    or a fixed one when `fixed` is given."""
    return {
        "income": Decimal("30000.00"),
        "payday": 25,
        "monthly_installment_budget": Decimal("9000.00"),
        "saving_mode": "fixed" if fixed is not None else "percent",
        "saving_percent": None if fixed is not None else percent,
        "saving_fixed_amount": None if fixed is None else Decimal(fixed),
    }


def user_settings(**overrides: Any) -> UserSettings:
    fields: dict[str, Any] = {"user_id": USER}
    return UserSettings(**(fields | overrides))


def notification(**overrides: Any) -> Notification:
    fields: dict[str, Any] = {
        "user_id": USER,
        "kind": "new_debt",
        "title": "New installment",
        "body": "Total monthly installments: 500.00",
    }
    return Notification(**(fields | overrides))


def audit_log(**overrides: Any) -> AuditLog:
    fields: dict[str, Any] = {
        "user_id": USER,
        "actor": "system",
        "action": "installment_created",
        "ref_type": "installment",
        "ref_id": "c-1",
        "detail": {"event_id": "evt-1"},
    }
    return AuditLog(**(fields | overrides))


def add_event(session: Session, event_id: str = "evt-1", vendor: str = VENDOR) -> None:
    session.add(webhook_event(event_id=event_id, vendor=vendor))
    session.flush()


def add_installment(session: Session, contract_id: str = "c-1", vendor: str = VENDOR) -> uuid.UUID:
    row = installment(contract_id=contract_id, vendor=vendor)
    session.add(row)
    session.flush()
    return row.id


def add_auto_save_parents(
    session: Session, event_id: str = "evt-1", contract_id: str = "c-1", vendor: str = VENDOR
) -> uuid.UUID:
    """An event and its installment, the two rows every auto_save must reference."""
    session.add(webhook_event(event_id=event_id, contract_id=contract_id, vendor=vendor))
    return add_installment(session, contract_id, vendor)
