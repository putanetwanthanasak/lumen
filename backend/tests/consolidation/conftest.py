"""The app API and webhook fixtures, shared with the settings and webhook tests."""

from tests.user_settings.conftest import api
from tests.webhooks.conftest import webhook

__all__ = ["api", "webhook"]
