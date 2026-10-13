"""SQLAlchemy models (04 section 4).

The database enforces every invariant it can (CHECK, UNIQUE, partial UNIQUE, FK,
and an append-only trigger on audit_log in the migration) as defense in depth.
Services must still enforce the rest; see 05 section 3.

Types:
- Money: Numeric(12, 2) -> Decimal. Never float.
- Rates: Numeric(7, 6) -> Decimal. Rates are not money, so they are not rounded
  to cents; 6 places hold monthly rates such as 0.020833 (25% APR / 12).
- Timestamps: TIMESTAMPTZ.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Money = Numeric(12, 2)
Rate = Numeric(7, 6)


class EventType(StrEnum):
    # All six events from 03 section 2 (04 section 4.1 says "4 types"; see progress log).
    INSTALLMENT_CREATED = "installment_created"
    CASH_WITHDRAWAL_CREATED = "cash_withdrawal_created"
    CASH_LOAN_CREATED = "cash_loan_created"
    INSTALLMENT_PAYMENT_COLLECTED = "installment_payment_collected"
    INSTALLMENT_OVERDUE = "installment_overdue"
    INSTALLMENT_CANCELLED = "installment_cancelled"


class EventStatus(StrEnum):
    PROCESSED = "processed"
    PENDING_PARENT = "pending_parent"
    REJECTED = "rejected"


class InstallmentKind(StrEnum):
    PURCHASE = "purchase"
    CASH_WITHDRAWAL = "cash_withdrawal"
    CASH_LOAN = "cash_loan"


class InstallmentStatus(StrEnum):
    ACTIVE = "active"
    PAID_OFF = "paid_off"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class SavingsType(StrEnum):
    AUTO_SAVE = "auto_save"
    WITHDRAWAL = "withdrawal"


class NotificationKind(StrEnum):
    NEW_DEBT = "new_debt"
    CASH_WITHDRAWAL = "cash_withdrawal"
    CASH_LOAN = "cash_loan"
    OVER_CAP = "over_cap"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    PUSHED = "pushed"
    INBOX_ONLY = "inbox_only"


class UserResponse(StrEnum):
    NONE = "none"
    NOT_ME = "not_me"


class Actor(StrEnum):
    SYSTEM = "system"
    USER = "user"


def one_of(column: str, values: type[StrEnum]) -> CheckConstraint:
    """CHECK (column IN (...)) built from a StrEnum; values are code constants, not input."""
    allowed = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_valid")


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        one_of("event_type", EventType),
        one_of("status", EventStatus),
    )

    # Platform event id = idempotency key (ID-01, ID-02).
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    vendor: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(Text, index=True)
    contract_id: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = created_at_column()


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (
        UniqueConstraint("vendor", "contract_id"),  # ID-05
        one_of("kind", InstallmentKind),
        one_of("status", InstallmentStatus),
        CheckConstraint("principal > 0", name="principal_positive"),
        CheckConstraint("months > 0", name="months_positive"),
        CheckConstraint("monthly_amount >= 0", name="monthly_amount_nonneg"),
        CheckConstraint("fee_total >= 0", name="fee_total_nonneg"),
        CheckConstraint("paid_amount >= 0", name="paid_amount_nonneg"),
        CheckConstraint("paid_amount <= principal + fee_total", name="paid_le_total"),  # INV-6
        CheckConstraint("min_payment >= 0", name="min_payment_nonneg"),
        CheckConstraint("late_fee_per_period >= 0", name="late_fee_nonneg"),
        CheckConstraint("monthly_rate >= 0", name="monthly_rate_nonneg"),
        CheckConstraint("overdue_days >= 0", name="overdue_days_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[str] = mapped_column(Text, index=True)
    vendor: Mapped[str] = mapped_column(Text)
    contract_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    item_name: Mapped[str] = mapped_column(Text)
    principal: Mapped[Decimal] = mapped_column(Money)
    months: Mapped[int]
    monthly_amount: Mapped[Decimal] = mapped_column(Money)
    fee_total: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    paid_amount: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    first_due_date: Mapped[date] = mapped_column(Date)
    # L41: full debt data from the platform contract (an assumption about its API).
    # No defaults: a silent 0 rate or fee would make debt look free to the planner.
    min_payment: Mapped[Decimal] = mapped_column(Money)
    late_fee_per_period: Mapped[Decimal] = mapped_column(Money)
    monthly_rate: Mapped[Decimal] = mapped_column(Rate)
    overdue_days: Mapped[int] = mapped_column(server_default=text("0"))
    created_at: Mapped[datetime] = created_at_column()


class SavingsTransaction(Base):
    __tablename__ = "savings_transactions"
    __table_args__ = (
        one_of("type", SavingsType),
        CheckConstraint("amount > 0", name="amount_positive"),
        # NULLs never collide in a UNIQUE index, so INV-3 needs auto_save to carry its event.
        CheckConstraint(
            "type <> 'auto_save' OR source_event_id IS NOT NULL",
            name="auto_save_has_source_event",
        ),
        # INV-3: one event creates at most one auto_save.
        Index(
            "uq_savings_transactions_auto_save_source_event_id",
            "source_event_id",
            unique=True,
            postgresql_where=text("type = 'auto_save'"),
        ),
        # ID-05: one installment gets at most one auto_save, even if the platform
        # resends the same contract under a new event_id.
        CheckConstraint(
            "type <> 'auto_save' OR installment_id IS NOT NULL",
            name="auto_save_has_installment",
        ),
        Index(
            "uq_savings_transactions_auto_save_installment_id",
            "installment_id",
            unique=True,
            postgresql_where=text("type = 'auto_save'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[str] = mapped_column(Text, index=True)
    type: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Money)  # always positive; direction from type
    source_event_id: Mapped[str | None] = mapped_column(Text, ForeignKey("webhook_events.event_id"))
    installment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("installments.id")
    )
    created_at: Mapped[datetime] = created_at_column()


class UserBalance(Base):
    __tablename__ = "user_balances"
    __table_args__ = (
        CheckConstraint("savings_balance >= 0", name="savings_balance_nonneg"),  # INV-2
        CheckConstraint("version >= 0", name="version_nonneg"),
    )

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    savings_balance: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    version: Mapped[int] = mapped_column(server_default=text("0"))  # optimistic locking


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("save_rate BETWEEN 0.03 AND 0.10", name="save_rate_range"),
        CheckConstraint("per_item_cap >= 10.00", name="per_item_cap_ge_min_saving"),
        CheckConstraint(
            "monthly_installment_cap IS NULL OR monthly_installment_cap >= 0",
            name="monthly_cap_nonneg",
        ),
    )

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    auto_save_enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    save_rate: Mapped[Decimal] = mapped_column(Rate, server_default=text("0.05"))
    per_item_cap: Mapped[Decimal] = mapped_column(Money, server_default=text("100.00"))
    monthly_installment_cap: Mapped[Decimal | None] = mapped_column(Money)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        one_of("kind", NotificationKind),
        one_of("delivery_status", DeliveryStatus),
        one_of("user_response", UserResponse),
        CheckConstraint("push_attempts >= 0", name="push_attempts_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[str] = mapped_column(Text, index=True)
    installment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("installments.id")
    )
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    push_attempts: Mapped[int] = mapped_column(server_default=text("0"))
    user_response: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    created_at: Mapped[datetime] = created_at_column()


class AuditLog(Base):
    """Append-only. The migration adds a trigger rejecting UPDATE, DELETE, TRUNCATE."""

    __tablename__ = "audit_log"
    __table_args__ = (one_of("actor", Actor),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Text, index=True)
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at_column()
