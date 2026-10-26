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
    ForeignKeyConstraint,
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


class DisputeSignalStatus(StrEnum):
    """L60 (2): whether the platform got the "Not me" report. The message says "sent"
    only for SENT; PENDING (recorded, not yet tried) and FAILED are re-attempted."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class UserResponse(StrEnum):
    NONE = "none"
    NOT_ME = "not_me"


DISPUTE_ACTION = "installment_disputed"


# L62: installments the user records themselves carry this vendor. No webhook vendor
# can have it: vendors come from configured secrets, and "manual" has none.
MANUAL_VENDOR = "manual"


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

    # Idempotency key is (vendor, event_id) (L47; ID-01, ID-02): event ids are only
    # unique within one platform, so two vendors may reuse the same id.
    vendor: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
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
        CheckConstraint("late_fees_accrued >= 0", name="late_fees_accrued_nonneg"),
        # INV-6 (L48): late fees are owed too, so a payment may cover them.
        CheckConstraint(
            "paid_amount <= principal + fee_total + late_fees_accrued", name="paid_le_total"
        ),
        CheckConstraint("min_payment >= 0", name="min_payment_nonneg"),
        CheckConstraint("late_fee_per_period >= 0", name="late_fee_nonneg"),
        CheckConstraint("monthly_rate >= 0", name="monthly_rate_nonneg"),
        CheckConstraint("overdue_days >= 0", name="overdue_days_nonneg"),
        # L42: a disputed installment records when. disputed_at may also be set on a
        # cancelled one (L59 3: cancelled after the report, or reported after cancel).
        CheckConstraint(
            "status <> 'disputed' OR disputed_at IS NOT NULL", name="disputed_has_disputed_at"
        ),
        # L60 (2): every report has a signal status, and only a report has one.
        one_of("dispute_signal_status", DisputeSignalStatus),
        CheckConstraint(
            "(disputed_at IS NULL) = (dispute_signal_status IS NULL)",
            name="dispute_signal_status_with_report",
        ),
        # L62: a manual row, and only a manual row, carries the client's request id.
        CheckConstraint(
            f"(vendor = '{MANUAL_VENDOR}') = (client_request_id IS NOT NULL)",
            name="manual_has_client_request_id",
        ),
        # L41 debt data comes from the platform. A manual row may leave it unknown
        # (NULL), never a made-up 0; a platform row must have all of it.
        CheckConstraint(
            f"vendor = '{MANUAL_VENDOR}' OR (min_payment IS NOT NULL "
            "AND late_fee_per_period IS NOT NULL AND monthly_rate IS NOT NULL)",
            name="platform_debt_data_complete",
        ),
        # The idempotency key for manual entry (L62): a double submit, however
        # concurrent, creates one installment.
        Index(
            "uq_installments_user_client_request_id",
            "user_id",
            "client_request_id",
            unique=True,
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
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
    # L48: kept apart from fee_total because the payoff planner needs them separately.
    late_fees_accrued: Mapped[Decimal] = mapped_column(Money, server_default=text("0"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    first_due_date: Mapped[date] = mapped_column(Date)
    # L41: full debt data from the platform contract (an assumption about its API).
    # No defaults: a silent 0 rate or fee would make debt look free to the planner.
    # NULL (unknown) only on a manual row, by platform_debt_data_complete.
    min_payment: Mapped[Decimal | None] = mapped_column(Money)
    late_fee_per_period: Mapped[Decimal | None] = mapped_column(Money)
    monthly_rate: Mapped[Decimal | None] = mapped_column(Rate)
    overdue_days: Mapped[int] = mapped_column(server_default=text("0"))
    # Set once by "Not me" and never cleared, so the dispute history survives (L59 3).
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispute_signal_status: Mapped[str | None] = mapped_column(Text)
    client_request_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


class SavingsTransaction(Base):
    __tablename__ = "savings_transactions"
    __table_args__ = (
        one_of("type", SavingsType),
        CheckConstraint("amount > 0", name="amount_positive"),
        # The source event is the pair (vendor, event_id) (L47).
        ForeignKeyConstraint(
            ["source_vendor", "source_event_id"],
            ["webhook_events.vendor", "webhook_events.event_id"],
        ),
        # A composite FK is MATCH SIMPLE: a half-NULL pair would skip it entirely.
        CheckConstraint(
            "(source_vendor IS NULL) = (source_event_id IS NULL)",
            name="source_event_pair_complete",
        ),
        # INV-3: one event creates at most one auto_save. A manual entry (L62) has no
        # event, so its auto_save has no source pair; the per-installment index below
        # is what keeps it to one.
        Index(
            "uq_savings_transactions_auto_save_source_event",
            "source_vendor",
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
    source_vendor: Mapped[str | None] = mapped_column(Text)
    source_event_id: Mapped[str | None] = mapped_column(Text)
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


class SavingMode(StrEnum):
    """L63: the user picks exactly one saving rule; the two never combine."""

    PERCENT = "percent"
    FIXED = "fixed"


class UserSettings(Base):
    """The user's own settings (L63, L64). A row from before L63 has no profile (all
    four profile columns NULL) and saves nothing until the user sets a rule."""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("monthly_installment_budget >= 0", name="monthly_budget_nonneg"),
        CheckConstraint("income > 0", name="income_positive"),
        CheckConstraint("payday BETWEEN 1 AND 31", name="payday_day_of_month"),
        one_of("saving_mode", SavingMode),
        CheckConstraint("saving_percent BETWEEN 1 AND 100", name="saving_percent_range"),
        CheckConstraint("saving_fixed_amount > 0", name="saving_fixed_amount_positive"),
        # Exactly the chosen mode's value is set, so both rules can never be active.
        CheckConstraint(
            "(saving_percent IS NOT NULL) = (saving_mode IS NOT DISTINCT FROM 'percent')",
            name="saving_percent_with_mode",
        ),
        CheckConstraint(
            "(saving_fixed_amount IS NOT NULL) = (saving_mode IS NOT DISTINCT FROM 'fixed')",
            name="saving_fixed_amount_with_mode",
        ),
        CheckConstraint(
            "num_nulls(income, payday, monthly_installment_budget, saving_mode) IN (0, 4)",
            name="profile_all_or_none",
        ),
    )

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    auto_save_enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    # Stamped the first time the user turns auto-save on with consent; never cleared.
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    monthly_installment_budget: Mapped[Decimal | None] = mapped_column(Money)
    income: Mapped[Decimal | None] = mapped_column(Money)
    payday: Mapped[int | None]
    saving_mode: Mapped[str | None] = mapped_column(Text)
    saving_percent: Mapped[int | None]
    saving_fixed_amount: Mapped[Decimal | None] = mapped_column(Money)
    # Stored only; the leftover-budget transfer comes in a later session.
    leftover_saving_enabled: Mapped[bool] = mapped_column(server_default=text("false"))


# The new-debt alert kinds (5e): one per installment, whatever the installment kind.
NEW_DEBT_KINDS = (
    NotificationKind.NEW_DEBT,
    NotificationKind.CASH_WITHDRAWAL,
    NotificationKind.CASH_LOAN,
)
NEW_DEBT_KIND_SQL = f"kind IN ({', '.join(f"'{k.value}'" for k in NEW_DEBT_KINDS)})"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        one_of("kind", NotificationKind),
        one_of("delivery_status", DeliveryStatus),
        one_of("user_response", UserResponse),
        CheckConstraint("push_attempts >= 0", name="push_attempts_nonneg"),
        # NULLs never collide in a UNIQUE index, so the index below needs this.
        CheckConstraint(
            f"NOT ({NEW_DEBT_KIND_SQL}) OR installment_id IS NOT NULL",
            name="new_debt_has_installment",
        ),
        # Exactly one new-debt alert per installment, however often or however
        # concurrently its created event arrives (NT-04).
        Index(
            "uq_notifications_new_debt_installment_id",
            "installment_id",
            unique=True,
            postgresql_where=text(NEW_DEBT_KIND_SQL),
        ),
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
    __table_args__ = (
        one_of("actor", Actor),
        # One "Not me" audit row per installment, however often or concurrently the
        # user taps it (L42).
        Index(
            "uq_audit_log_installment_disputed",
            "ref_id",
            unique=True,
            postgresql_where=text(f"action = '{DISPUTE_ACTION}'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Text, index=True)
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at_column()
