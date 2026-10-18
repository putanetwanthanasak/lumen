"""In-memory stand-in for the platform's dispute API (L42). Records every signal so
tests can assert on them; it sends nothing anywhere."""

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class DisputeSignal:
    vendor: str
    contract_id: str
    user_id: str


class MockPlatformProvider:
    def __init__(self) -> None:
        self._signals: list[DisputeSignal] = []
        self._lock = threading.Lock()

    def signal_dispute(self, *, vendor: str, contract_id: str, user_id: str) -> None:
        with self._lock:
            self._signals.append(DisputeSignal(vendor, contract_id, user_id))

    @property
    def signals(self) -> list[DisputeSignal]:
        with self._lock:
            return list(self._signals)
