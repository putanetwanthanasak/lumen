"""Provider selection (04 section 8): PROVIDER_MODE picks the implementation."""

from functools import lru_cache

from app.providers.base import BankAccountProvider
from app.providers.mock_bank import MockBankAccountProvider


@lru_cache
def get_bank_provider() -> BankAccountProvider:
    """One shared instance per process. Settings only accepts PROVIDER_MODE=mock so
    far; a real provider gets its own branch here, and core logic does not change."""
    return MockBankAccountProvider()
