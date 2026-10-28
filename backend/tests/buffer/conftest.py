"""The app API fixture, shared with the settings tests; plan_api fixes the clock at
2026-11-10 for GET /buffer/shortfalls."""

from tests.assistant.conftest import plan_api
from tests.user_settings.conftest import api

__all__ = ["api", "plan_api"]
