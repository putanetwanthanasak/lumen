"""Auto-save (04 section 6, step 5b and 5c; 05 section 4.6)."""

import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ledger.service import ContractCreated
from app.models import SavingsTransaction, SavingsType, UserBalance, UserSettings
from app.providers.base import BankAccountProvider
from app.rules.config import NEVER_SAVE_KINDS, load_rules
from app.rules.engine import ZERO, compute_saving

# Each failed attempt means another transaction committed a credit for this user, so
# this bounds the number of concurrent writers, not time. Past it, the event fails
# with a 500 and the platform retries it later.
MAX_CREDIT_ATTEMPTS = 100


class BalanceContentionError(Exception):
    pass


def auto_save(
    session: Session,
    *,
    vendor: str,
    event: ContractCreated,
    installment_id: uuid.UUID,
    bank: BankAccountProvider,
) -> Decimal:
    """Record the auto-save for a new contract and return its amount (0.00 if none).

    The caller moves the money with bank.transfer_to_savings only after the
    transaction passes reconcile. The saving belongs to the event's user (L51).
    """
    contract = event.contract
    if contract.kind in NEVER_SAVE_KINDS:  # INV-5: decided before anything else
        return ZERO
    user_id = event.user_ref
    settings = session.get(UserSettings, user_id)
    # SV-01, SV-02: a missing row means auto-save was never switched on.
    if settings is None or not settings.auto_save_enabled or settings.consent_at is None:
        return ZERO

    # R3: hold this user's balance row until commit, before reading the bank. A second
    # purchase for the same user waits here and then reads the bank after the first
    # one's transfer, so two savings cannot jointly pass the safety net. The version
    # check in _credit stays as a second layer.
    _lock_balance(session, user_id)
    rules = load_rules()
    amount = compute_saving(
        kind=contract.kind,
        item_value=contract.principal,
        bank_balance=bank.get_balance(user_id),
        rules=rules.auto_save,
        protected_min=rules.safety_net.protected_min_balance,
    )
    if amount == ZERO:
        return ZERO

    session.add(
        SavingsTransaction(
            user_id=user_id,
            type=SavingsType.AUTO_SAVE,
            amount=amount,
            source_vendor=vendor,
            source_event_id=event.event_id,
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
