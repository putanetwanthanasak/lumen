"""MockPushProvider (04 section 8): can be set to fail; records every attempt."""

import threading

from app.providers import get_push_provider
from app.providers.mock_push import MockPushProvider, Push


def test_push_delivers_and_records() -> None:
    push = MockPushProvider()
    assert push.send("u", "t", "b") is True
    assert push.attempts == [Push("u", "t", "b", delivered=True)]
    assert push.delivered == push.attempts


def test_push_set_to_fail_records_the_failed_attempt() -> None:
    push = MockPushProvider(fail=True)
    assert push.send("u", "t", "b") is False
    assert push.attempts == [Push("u", "t", "b", delivered=False)]
    assert push.delivered == []


def test_push_records_concurrent_attempts() -> None:
    push = MockPushProvider()
    threads = [threading.Thread(target=push.send, args=(f"u{i}", "t", "b")) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(p.user_id for p in push.attempts) == sorted(f"u{i}" for i in range(20))


def test_app_uses_one_shared_push_mock_in_mock_mode() -> None:
    assert isinstance(get_push_provider(), MockPushProvider)
    assert get_push_provider() is get_push_provider()
