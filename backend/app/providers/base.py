"""Data-source interfaces (04 section 8). Core logic depends on these, never on a mock."""

from decimal import Decimal
from typing import Protocol


class BankAccountProvider(Protocol):
    def get_balance(self, user_id: str) -> Decimal: ...
    def transfer_to_savings(self, user_id: str, amount: Decimal) -> None: ...
    def transfer_from_savings(self, user_id: str, amount: Decimal) -> None: ...


class PushProvider(Protocol):
    def send(self, user_id: str, title: str, body: str) -> bool:
        """True if the push reached the device. May also raise; callers treat both
        a False and an exception as a failed attempt."""
        ...
