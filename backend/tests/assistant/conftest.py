"""The app API fixture with the clock fixed at 2026-11-10 (Bangkok)."""

from datetime import date

import pytest

from app.clock import today
from app.main import app
from tests.user_settings.conftest import Api, api

__all__ = ["api", "plan_api"]

TODAY = date(2026, 11, 10)


@pytest.fixture
def plan_api(api: Api) -> Api:
    app.dependency_overrides[today] = lambda: TODAY
    return api  # the api fixture clears every override afterwards
