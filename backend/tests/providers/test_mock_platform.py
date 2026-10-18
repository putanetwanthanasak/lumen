"""MockPlatformProvider (L42): records each dispute signal; sends nothing."""

import threading

from app.providers import get_platform_provider
from app.providers.mock_platform import DisputeSignal, MockPlatformProvider


def test_signal_recorded() -> None:
    platform = MockPlatformProvider()
    platform.signal_dispute(vendor="shopdemo", contract_id="c_1", user_id="u")
    assert platform.signals == [DisputeSignal("shopdemo", "c_1", "u")]


def test_concurrent_signals_all_recorded() -> None:
    platform = MockPlatformProvider()

    def send(i: int) -> None:
        platform.signal_dispute(vendor="shopdemo", contract_id=f"c_{i}", user_id="u")

    threads = [threading.Thread(target=send, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(s.contract_id for s in platform.signals) == sorted(f"c_{i}" for i in range(20))


def test_app_uses_one_shared_platform_mock_in_mock_mode() -> None:
    assert isinstance(get_platform_provider(), MockPlatformProvider)
    assert get_platform_provider() is get_platform_provider()
