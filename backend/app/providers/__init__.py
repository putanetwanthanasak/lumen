"""Provider selection (04 section 8): PROVIDER_MODE picks the implementation."""

from functools import lru_cache

from app.config import get_settings
from app.providers.base import (
    BankAccountProvider,
    ConsolidationBankProvider,
    PlatformProvider,
    PushProvider,
)
from app.providers.mock_bank import MockBankAccountProvider
from app.providers.mock_consolidation import MockConsolidationBank
from app.providers.mock_platform import MockPlatformProvider
from app.providers.mock_push import MockPushProvider


@lru_cache
def get_bank_provider() -> BankAccountProvider:
    """One shared instance per process. Settings only accepts PROVIDER_MODE=mock so
    far; a real provider gets its own branch here, and core logic does not change."""
    return MockBankAccountProvider()


@lru_cache
def get_push_provider() -> PushProvider:
    """As get_bank_provider. Also a FastAPI dependency, so tests can swap it."""
    return MockPushProvider()


@lru_cache
def get_platform_provider() -> PlatformProvider:
    """As get_push_provider."""
    return MockPlatformProvider()


@lru_cache
def get_consolidation_bank() -> ConsolidationBankProvider:
    """As get_push_provider. The mock's answer comes from CONSOLIDATION_MOCK_DECISION."""
    return MockConsolidationBank(get_settings().consolidation_mock_decision)
