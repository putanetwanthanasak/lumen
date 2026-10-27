"""In-memory stand-in for a bank's consolidation API (L71, L72). MOCK: no bank is
involved, and nothing is sent anywhere.

Its decision is fixed by configuration (CONSOLIDATION_MOCK_DECISION) so a demo can
show both answers. When it approves, it takes the amounts in the application as
its own figures: a real bank would check them against each platform's payoff
quote. Like the mock bank account, it applies each key at most once.
"""

import hashlib
import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.providers.base import Application, Decision


@dataclass(frozen=True)
class PaidOut:
    vendor: str
    contract_id: str
    amount: Decimal


class MockConsolidationBank:
    def __init__(self, decision: Literal["approve", "decline"] = "approve") -> None:
        self._approve = decision == "approve"
        self._decisions: dict[str, Decision] = {}
        self._paid: dict[str, PaidOut] = {}
        self._lock = threading.Lock()

    def decide(self, application: Application) -> Decision:
        with self._lock:
            earlier = self._decisions.get(application.reference)
            if earlier is None:
                reference = (
                    "MOCK-" + hashlib.sha256(application.reference.encode()).hexdigest()[:16]
                )
                earlier = Decision(
                    approved=self._approve,
                    payoffs=application.payoffs if self._approve else (),
                    reference=reference,
                )
                self._decisions[application.reference] = earlier
            return earlier

    def pay_out(
        self, *, vendor: str, contract_id: str, amount: Decimal, idempotency_key: str
    ) -> None:
        if type(amount) is not Decimal or amount <= 0:
            raise ValueError("amount must be a positive Decimal")
        paid = PaidOut(vendor, contract_id, amount)
        with self._lock:
            earlier = self._paid.get(idempotency_key)
            if earlier is not None:
                if earlier != paid:
                    raise ValueError("idempotency key reused for a different payout")
                return  # already paid: a retry pays nothing
            self._paid[idempotency_key] = paid

    @property
    def payouts(self) -> list[PaidOut]:
        with self._lock:
            return list(self._paid.values())
