"""Auto-save (04 section 6, step 5b and 5c; 05 section 4.6), for a webhook contract
or a manual entry (L62), and the balance primitives the buffer (L66) shares."""

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


def move_key(user_id: str, client_request_id: str) -> str:
    """As transfer_key, for a move from the buffer to the main account (L66): the
    same on every submit of one request, so a retry after a lost commit credits the
    main account once."""
    canonical = json.dumps(
        ["buffer_move_to_main", user_id, client_request_id], separators=(",", ":")
    )
    return "move-to-main-" + hashlib.sha256(canonical.encode()).hexdigest()


def leftover_key(user_id: str, month: str) -> str:
    """As transfer_key, for one payday month's leftover saving (L67): the same on
    every attempt for (user, month), so a retry after a lost commit debits once."""
    canonical = json.dumps(["leftover_save", user_id, month], separators=(",", ":"))
    return "leftover-save-" + hashlib.sha256(canonical.encode()).hexdigest()


def saving_rule(settings: UserSettings) -> SavingRule | None:
    """The user's one rule (L63), or None if they have not set one (a row from before
    L63). The DB CHECKs guarantee the chosen mode's value is present."""
    if settings.saving_mode == SavingMode.PERCENT and settings.saving_percent is not None:
        return PercentRule(settings.saving_percent)
    if settings.saving_mode == SavingMode.FIXED and settings.saving_fixed_amount is not None:
        return FixedRule(settings.saving_fixed_amount)
    return None


def active_rule(session: Session, user_id: str, kind: str) -> SavingRule | None:
    """The rule a new installment of this kind saves by, or None if it saves nothing."""
    if kind in NEVER_SAVE_KINDS:  # INV-5: decided before anything else
        return None
    settings = session.get(UserSettings, user_id)
    # SV-01, SV-02: a missing row means auto-save was never switched on.
    if settings is None or not settings.auto_save_enabled or settings.consent_at is None:
        return None
    return saving_rule(settings)  # None: no rule set yet, nothing to save by


def _saving(kind: str, item_price: Decimal, bank_balance: Decimal, rule: SavingRule) -> Decimal:
    """The L63 amount with the safety net, for both auto_save and would_save."""
    return compute_saving(
        kind=kind,
        item_value=item_price,
        bank_balance=bank_balance,
        rule=rule,
        protected_min=load_rules().safety_net.protected_min_balance,
    )


def _already_moved(
    user_id: str, kind: str, transfer_key: str, bank: BankAccountProvider
) -> Decimal | None:
    """What the bank already moved under this saving's key, None if nothing.

    A retry after a lost commit: the transfer runs before COMMIT, so the money moved
    while the rows rolled back (Session 23 review F2). A kind that never saves never
    has one: INV-5 is decided first, even if a retry comes back with another kind.
    No lock is needed: two requests with one key are serialized earlier, by the
    idempotency insert (webhook_events or installments)."""
    if kind in NEVER_SAVE_KINDS:
        return None
    return bank.applied_to_savings(user_id, transfer_key)


def would_save(
    session: Session,
    *,
    user_id: str,
    kind: str,
    item_price: Decimal,
    transfer_key: str,
    bank: BankAccountProvider,
) -> Decimal:
    """What auto_save would save for this installment now (the preview's
    saving_if_recorded): what already moved under its key, as auto_save records it,
    else the rule's amount. Read-only: no lock and no write, so a purchase that
    commits in between can change the answer; recording decides again under the lock."""
    moved = _already_moved(user_id, kind, transfer_key, bank)
    if moved is not None:
        return moved
    rule = active_rule(session, user_id, kind)
    if rule is None:
        return ZERO
    return _saving(kind, item_price, bank.get_balance(user_id), rule)


def auto_save(
    session: Session,
    *,
    user_id: str,
    kind: str,
    item_price: Decimal,
    installment_id: uuid.UUID,
    source: tuple[str, str] | None,
    transfer_key: str,
    bank: BankAccountProvider,
) -> Decimal:
    """Record the auto-save for a new installment and return its amount (0.00 if none).

    `source` is the (vendor, event_id) of the webhook event that created it, or None
    for a manual entry. `transfer_key` is the bank key the caller moves the money
    under, with bank.transfer_to_savings, only after the transaction passes reconcile.
    The saving belongs to the installment's user (L51), and its amount follows that
    user's own rule (L63) on either path.

    A retry after a lost commit: the bank already moved this saving under the same key
    (the transfer runs before COMMIT, and the rows rolled back). Record what moved, as
    payday does with its leftover. Deciding again would read a balance that already
    reflects it, so the safety net could skip it, and a changed rule could ask the bank
    for another amount under the same key; either way the money would leave the main
    account without a row. It is recorded even if auto-save was turned off in between:
    the money has already moved (Session 23 review F2).
    """
    moved = _already_moved(user_id, kind, transfer_key, bank)
    # R3, in both branches: hold this user's balance row until commit, before reading
    # the bank balance. A second purchase for the same user waits there and then reads
    # the bank after the first one's transfer, so two savings cannot jointly pass the
    # safety net. The version check in adjust_balance stays as a second layer.
    if moved is None:
        rule = active_rule(session, user_id, kind)
        if rule is None:
            return ZERO
        lock_balance(session, user_id)
        amount = _saving(kind, item_price, bank.get_balance(user_id), rule)
    else:
        lock_balance(session, user_id)
        amount = moved
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
    adjust_balance(session, user_id, amount)
    return amount


def lock_balance(session: Session, user_id: str) -> None:
    """Create the user's balance row if missing, then SELECT ... FOR UPDATE it.

    Of two concurrent inserts, the second waits on the unique index for the first to
    commit and then does nothing, so both reach the lock on the same row.
    """
    session.execute(pg_insert(UserBalance).values(user_id=user_id).on_conflict_do_nothing())
    session.execute(
        select(UserBalance.user_id).where(UserBalance.user_id == user_id).with_for_update()
    ).one()


def adjust_balance(session: Session, user_id: str, delta: Decimal) -> None:
    """savings_balance += delta (negative for a withdrawal) with optimistic locking
    on version. The CHECK savings_balance >= 0 (INV-2) stops an overdraw.

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
            .values(savings_balance=balance + delta, version=version + 1)
            .execution_options(synchronize_session=False)
        )
        if updated.rowcount == 1:  # type: ignore[attr-defined]
            return
    # S12: no user ref in the message; it reaches the server log.
    raise BalanceContentionError(f"balance still contended after {MAX_CREDIT_ATTEMPTS} attempts")
