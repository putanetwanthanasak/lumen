"""Data-source interfaces (04 section 8). Core logic depends on these, never on a mock."""

from decimal import Decimal
from typing import Protocol


class BankAccountProvider(Protocol):
    def get_balance(self, user_id: str) -> Decimal: ...
    def transfer_to_savings(self, user_id: str, amount: Decimal) -> None: ...
    def transfer_from_savings(self, user_id: str, amount: Decimal) -> None: ...
