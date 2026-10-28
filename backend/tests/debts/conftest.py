"""The webhook fixture drives the app over HTTP; the summary is read the same way.
GET /debts/months uses the app API with the clock fixed at 2026-11-10 (plan_api)."""

from tests.assistant.conftest import plan_api
from tests.user_settings.conftest import api
from tests.webhooks.conftest import webhook

__all__ = ["api", "plan_api", "webhook"]
