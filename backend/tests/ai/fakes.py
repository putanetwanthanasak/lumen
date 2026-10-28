"""A fake model for the summary tests: no network, records every call."""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class FakeWriter:
    """Answers `text`, or raises `error`. `during` runs inside the call (to look at
    the cache lock while the model is being asked)."""

    text: str = ""
    error: Exception | None = None
    model: str = "fake-model"
    during: Callable[[], None] | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def write(self, *, system: str, facts: str) -> str:
        self.calls.append((system, facts))
        if self.during is not None:
            self.during()
        if self.error is not None:
            raise self.error
        return self.text
