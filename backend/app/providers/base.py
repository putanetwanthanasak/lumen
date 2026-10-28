"""Data-source interfaces (04 section 8). Core logic depends on these, never on a mock."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class BankAccountProvider(Protocol):
    def get_balance(self, user_id: str) -> Decimal: ...
    def transfer_to_savings(self, user_id: str, amount: Decimal, *, idempotency_key: str) -> None:
        """Move amount into savings. The bank applies a given key at most once (S1): a
        retry with the same key after a lost commit is a no-op, not a second debit."""
        ...

    def transfer_from_savings(self, user_id: str, amount: Decimal, *, idempotency_key: str) -> None:
        """Move amount from savings back to the main account (L66), with the same
        at-most-once guarantee per key as transfer_to_savings."""
        ...

    def applied_to_savings(self, user_id: str, idempotency_key: str) -> Decimal | None:
        """The amount a transfer_to_savings under this key already moved for this user,
        or None if the key was never applied. A retry whose decision depends on the
        bank balance asks this first, so it records the money that moved instead of
        deciding again on a balance that already reflects it."""
        ...


class PushProvider(Protocol):
    def send(self, user_id: str, title: str, body: str) -> bool:
        """True if the push reached the device. May also raise; callers treat both
        a False and an exception as a failed attempt."""
        ...


class PlatformProvider(Protocol):
    def signal_dispute(self, *, vendor: str, contract_id: str, user_id: str) -> None:
        """Tell the platform the user reported this contract as not theirs (L42). It
        is a report only: nothing here stops or reverses the platform transaction."""
        ...


@dataclass(frozen=True)
class Payoff:
    installment_id: uuid.UUID
    vendor: str
    contract_id: str
    amount: Decimal  # what the user entered (L71): it starts the request, never approves it


@dataclass(frozen=True)
class Application:
    user_id: str
    reference: str  # the request's idempotency key: the same application, the same answer
    payoffs: tuple[Payoff, ...]
    annual_rate: Decimal
    term_months: int


@dataclass(frozen=True)
class Decision:
    approved: bool
    # The bank's own figure per installment, from its own data (L71). Only when approved.
    payoffs: tuple[Payoff, ...]
    reference: str  # the bank's reference for this decision


class ConsolidationBankProvider(Protocol):
    """The bank that decides on a consolidation and pays the platforms (L71, L72)."""

    def decide(self, application: Application) -> Decision:
        """The bank decides with its own data. User-entered amounts only start the
        request. The same reference always gets the same decision."""
        ...

    def pay_out(
        self, *, vendor: str, contract_id: str, amount: Decimal, idempotency_key: str
    ) -> None:
        """Pay a platform to close one contract, at most once per key (as S1)."""
        ...
