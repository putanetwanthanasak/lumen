"""The app API and webhook fixtures, shared with the settings and webhook tests, plus
`co`: the API with the clock fixed at 2026-11-10 and a fresh mock consolidation bank."""

from dataclasses import dataclass
from datetime import date

import pytest

from app.clock import today
from app.main import app
from app.providers import get_consolidation_bank
from app.providers.mock_consolidation import MockConsolidationBank
from tests.user_settings.conftest import Api, api
from tests.webhooks.conftest import webhook

__all__ = ["api", "co", "webhook"]

TODAY = date(2026, 11, 10)


@dataclass
class Co:
    api: Api
    bank: MockConsolidationBank

    def use_bank(self, bank: MockConsolidationBank) -> None:
        self.bank = bank
        app.dependency_overrides[get_consolidation_bank] = lambda: bank


@pytest.fixture
def co(api: Api) -> Co:
    app.dependency_overrides[today] = lambda: TODAY
    result = Co(api, MockConsolidationBank())
    result.use_bank(result.bank)
    return result  # the api fixture clears every override afterwards
