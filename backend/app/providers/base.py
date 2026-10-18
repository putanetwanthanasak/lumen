"""Data-source interfaces (04 section 8). Core logic depends on these, never on a mock."""

from decimal import Decimal
from typing import Protocol


class BankAccountProvider(Protocol):
    def get_balance(self, user_id: str) -> Decimal: ...
    def transfer_to_savings(self, user_id: str, amount: Decimal, *, idempotency_key: str) -> None:
        """Move amount into savings. The bank applies a given key at most once (S1): a
        retry with the same key after a lost commit is a no-op, not a second debit."""
        ...

    def transfer_from_savings(self, user_id: str, amount: Decimal) -> None: ...


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
