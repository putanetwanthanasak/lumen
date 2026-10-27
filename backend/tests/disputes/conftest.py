"""The webhook fixture drives the app over HTTP; the summary is read the same way.
The api fixture records manual entries (L62) for the L68 tests."""

from tests.user_settings.conftest import api
from tests.webhooks.conftest import webhook

__all__ = ["api", "webhook"]
