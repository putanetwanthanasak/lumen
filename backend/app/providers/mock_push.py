"""In-memory push for the demo (04 section 8). It can be set to fail, to demo the
inbox fallback (NT-03), and it records every attempt so tests can assert on them."""

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class Push:
    user_id: str
    title: str
    body: str
    delivered: bool


class MockPushProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self._attempts: list[Push] = []
        self._lock = threading.Lock()

    def send(self, user_id: str, title: str, body: str) -> bool:
        with self._lock:
            self._attempts.append(Push(user_id, title, body, delivered=not self.fail))
            return not self.fail

    @property
    def attempts(self) -> list[Push]:
        with self._lock:
            return list(self._attempts)

    @property
    def delivered(self) -> list[Push]:
        return [p for p in self.attempts if p.delivered]
