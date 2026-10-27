"""In-memory bank account for the demo (04 section 8).

State lives in this process only and resets when the server restarts. A lock guards
it because concurrent webhooks share one instance. Like a real bank API, it applies
each transfer idempotency key at most once (S1).
"""

import threading
from decimal import Decimal

from app.money import decimal_places

# Unseen users open with this balance, above the 500.00 safety net, so a demo
# purchase saves out of the box. Seed a lower one with set_balance to show a skip.
DEFAULT_OPENING_BALANCE = Decimal("10000.00")


def _require_amount(amount: object, *, positive: bool) -> Decimal:
    if type(amount) is not Decimal:
        raise ValueError(f"amount must be Decimal, got {type(amount).__name__}")
    if not amount.is_finite() or decimal_places(amount) > 2:
        raise ValueError("amount must be finite with at most 2 decimal places")
    if amount < 0 or (positive and amount == 0):
        raise ValueError("amount must be > 0" if positive else "amount must be >= 0")
    return amount


class MockBankAccountProvider:
    def __init__(self, opening_balance: Decimal = DEFAULT_OPENING_BALANCE) -> None:
        self._opening = _require_amount(opening_balance, positive=False)
        self._balances: dict[str, Decimal] = {}
        # idempotency key -> (direction, user, amount) of the transfer it applied
        self._applied: dict[str, tuple[str, str, Decimal]] = {}
        self._lock = threading.Lock()

    def set_balance(self, user_id: str, amount: Decimal) -> None:
        amount = _require_amount(amount, positive=False)
        with self._lock:
            self._balances[user_id] = amount

    def get_balance(self, user_id: str) -> Decimal:
        with self._lock:
            return self._balances.get(user_id, self._opening)

    def transfer_to_savings(self, user_id: str, amount: Decimal, *, idempotency_key: str) -> None:
        self._apply("to_savings", user_id, amount, idempotency_key)

    def transfer_from_savings(self, user_id: str, amount: Decimal, *, idempotency_key: str) -> None:
        self._apply("from_savings", user_id, amount, idempotency_key)

    def applied_to_savings(self, user_id: str, idempotency_key: str) -> Decimal | None:
        with self._lock:
            applied = self._applied.get(idempotency_key)
        if applied is None:
            return None
        direction, owner, amount = applied
        if (direction, owner) != ("to_savings", user_id):
            raise ValueError("idempotency key reused for a different transfer")
        return amount

    def _apply(self, direction: str, user_id: str, amount: Decimal, key: str) -> None:
        """Change the main-account balance once per key (S1). Savings itself lives in
        Lumen's ledger, so only the main account is tracked here."""
        amount = _require_amount(amount, positive=True)
        with self._lock:
            applied = self._applied.get(key)
            if applied is not None:
                if applied != (direction, user_id, amount):
                    raise ValueError("idempotency key reused for a different transfer")
                return  # already applied: a retry moves nothing
            balance = self._balances.get(user_id, self._opening)
            if direction == "to_savings":
                if amount > balance:
                    raise ValueError("insufficient funds")
                self._balances[user_id] = balance - amount
            else:
                self._balances[user_id] = balance + amount
            self._applied[key] = (direction, user_id, amount)
