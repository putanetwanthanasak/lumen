"""Auto-save (04 section 6, step 5b and 5c; 05 section 4.6), for a webhook contract
or a manual entry (L62)."""

import hashlib
import json
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import SavingMode, SavingsTransaction, SavingsType, UserBalance, UserSettings
from app.providers.base import BankAccountProvider
from app.rules.config import NEVER_SAVE_KINDS, load_rules
from app.rules.engine import ZERO, FixedRule, PercentRule, SavingRule, compute_saving

# Each failed attempt means another transaction committed a credit for this user, so
# this bounds the number of concurrent writers, not time. Past it, the event fails
# with a 500 and the platform retries it later.
MAX_CREDIT_ATTEMPTS = 100


class BalanceContentionError(Exception):
    pass


def transfer_key(vendor: str, event_id: str) -> str:
    """S1: the bank idempotency key for the auto-save of one event, the same on every
    delivery of it. Not savings_tx_id: that row is rolled back with a failed commit,
    so the platform's retry would get a new id and the bank would debit twice."""
    canonical = json.dumps(["auto_save", vendor, event_id], separators=(",", ":"))
    return "auto-save-" + hashlib.sha256(canonical.encode()).hexdigest()


def manual_transfer_key(user_id: str, client_request_id: str) -> str:
    """As transfer_key, for a manual entry (L62): the same on every submit of one
    request. Not the installment id: a retry after a failed commit gets a new one."""
    canonical = json.dumps(["auto_save_manual", user_id, client_request_id], separators=(",", ":"))
    return "auto-save-" + hashlib.sha256(canonical.encode()).hexdigest()


def saving_rule(settings: UserSettings) -> SavingRule | None:
    """The user's one rule (L63), or None if they have not set one (a row from before
    L63). The DB CHECKs guarantee the chosen mode's value is present."""
    if settings.saving_mode == SavingMode.PERCENT and settings.saving_percent is not None:
        return PercentRule(settings.saving_percent)
    if settings.saving_mode == SavingMode.FIXED and settings.saving_fixed_amount is not None:
        return FixedRule(settings.saving_fixed_amount)
    return None


def auto_save(
    session: Session,
    *,
    user_id: str,
    kind: str,
    item_price: Decimal,
    installment_id: uuid.UUID,
    source: tuple[str, str] | None,
    bank: BankAccountProvider,
) -> Decimal:
    """Record the auto-save for a new installment and return its amount (0.00 if none).

    `source` is the (vendor, event_id) of the webhook event that created it, or None
    for a manual entry. The caller moves the money with bank.transfer_to_savings only
    after the transaction passes reconcile. The saving belongs to the installment's
    user (L51), and its amount follows that user's own rule (L63) on either path.
    """
    if kind in NEVER_SAVE_KINDS:  # INV-5: decided before anything else
        return ZERO
    settings = session.get(UserSettings, user_id)
    # SV-01, SV-02: a missing row means auto-save was never switched on.
    if settings is None or not settings.auto_save_enabled or settings.consent_at is None:
        return ZERO
    rule = saving_rule(settings)
    if rule is None:  # no rule set yet: nothing to save by
        return ZERO

    # R3: hold this user's balance row until commit, before reading the bank. A second
    # purchase for the same user waits here and then reads the bank after the first
    # one's transfer, so two savings cannot jointly pass the safety net. The version
    # check in _credit stays as a second layer.
    _lock_balance(session, user_id)
    amount = compute_saving(
        kind=kind,
        item_value=item_price,
        bank_balance=bank.get_balance(user_id),
        rule=rule,
        protected_min=load_rules().safety_net.protected_min_balance,
    )
    if amount == ZERO:
        return ZERO

    session.add(
        SavingsTransaction(
            user_id=user_id,
            type=SavingsType.AUTO_SAVE,
            amount=amount,
            source_vendor=source[0] if source else None,
            source_event_id=source[1] if source else None,
            installment_id=installment_id,
        )
    )
    session.flush()
    _credit(session, user_id, amount)
    return amount


def _lock_balance(session: Session, user_id: str) -> None:
    """Create the user's balance row if missing, then SELECT ... FOR UPDATE it.

    Of two concurrent inserts, the second waits on the unique index for the first to
    commit and then does nothing, so both reach the lock on the same row.
    """
    session.execute(pg_insert(UserBalance).values(user_id=user_id).on_conflict_do_nothing())
    session.execute(
        select(UserBalance.user_id).where(UserBalance.user_id == user_id).with_for_update()
    ).one()


def _credit(session: Session, user_id: str, amount: Decimal) -> None:
    """savings_balance += amount with optimistic locking on version.

    The new balance is computed from the value read, so only the version check stops
    a lost update when two transactions read the same balance. Under READ COMMITTED,
    a losing UPDATE waits for the winner's commit, matches 0 rows, and the next
    SELECT sees the winner's balance.
    """
    session.execute(pg_insert(UserBalance).values(user_id=user_id).on_conflict_do_nothing())
    for _ in range(MAX_CREDIT_ATTEMPTS):
        balance, version = session.execute(
            select(UserBalance.savings_balance, UserBalance.version).where(
                UserBalance.user_id == user_id
            )
        ).one()
        updated = session.execute(
            update(UserBalance)
            .where(UserBalance.user_id == user_id, UserBalance.version == version)
            .values(savings_balance=balance + amount, version=version + 1)
            .execution_options(synchronize_session=False)
        )
        if updated.rowcount == 1:  # type: ignore[attr-defined]
            return
    # S12: no user ref in the message; it reaches the server log.
    raise BalanceContentionError(f"balance still contended after {MAX_CREDIT_ATTEMPTS} attempts")
