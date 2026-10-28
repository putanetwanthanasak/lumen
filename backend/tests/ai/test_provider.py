"""AI-15, AI-23 and AI-24: the writer that calls the model (app.ai.provider), with a
fake SDK client. No test reaches the network: tests/conftest.py fails any test that
builds the real Anthropic client (AI-23)."""

import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from app.ai.provider import (
    DEFAULT_MODEL,
    MAX_TOKENS,
    TIMEOUT_SECONDS,
    AnthropicWriter,
    WriterError,
    WriterTimeoutError,
    summary_writer,
)
from app.config import Settings

KEY = "sk-test-NOT-A-REAL-KEY"
REQUEST = httpx2.Request("POST", "https://api.invalid/v1/messages")


def settings(key: str | None, model: str | None = None, provider: str | None = None) -> Settings:
    """Every LLM field given, so the developer's .env never leaks into a test."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_api_key=None if key is None else SecretStr(key),
        llm_model_planner=model,
        llm_provider=provider,
    )


def reply(*blocks: tuple[str, str], stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type=kind, text=text) for kind, text in blocks],
    )


@dataclass
class FakeSdk:
    """Stands in for anthropic.Anthropic: records how it was built and called."""

    answer: Any = None
    error: BaseException | None = None
    built: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: int = 0

    def __call__(self, **kw: Any) -> Any:
        self.built.append(kw)
        return SimpleNamespace(messages=SimpleNamespace(create=self.create), close=self.close)

    def create(self, **kw: Any) -> Any:
        self.calls.append(kw)
        if self.error is not None:
            raise self.error
        return self.answer

    def close(self) -> None:
        self.closed += 1


def writer(sdk: FakeSdk, model: str = DEFAULT_MODEL) -> AnthropicWriter:
    return AnthropicWriter(SecretStr(f"  {KEY} "), model, client=sdk)


# --- AI-15: no key, no writer ----------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        settings(None),
        settings(""),
        settings("   "),
        settings(KEY, provider="openai"),  # another provider's key never goes to Anthropic
        settings(KEY, provider="gemini"),
    ],
)
def test_AI_15_no_key_or_another_provider_gives_no_writer(config: Settings) -> None:
    assert summary_writer(config) is None


def test_AI_15_a_key_gives_the_anthropic_writer_without_building_the_client() -> None:
    made = summary_writer(settings(KEY, provider="Anthropic"))
    assert isinstance(made, AnthropicWriter)
    assert made.model == DEFAULT_MODEL  # claude-haiku-5-5 when LLM_MODEL_PLANNER is unset
    assert DEFAULT_MODEL == "claude-haiku-5-5"
    named = summary_writer(settings(KEY, model=" claude-sonnet-5-5 "))
    assert named is not None
    assert named.model == "claude-sonnet-5-5"
    blank = summary_writer(settings(KEY, model="  "))
    assert blank is not None
    assert blank.model == DEFAULT_MODEL
    # Building the writer built no client: the guard (AI-23) would have failed the test.


# --- AI-23: the real client can never be built in a test ------------------------------


def test_AI_23_building_the_real_client_fails_the_test_loudly() -> None:
    with pytest.raises(pytest.fail.Exception, match="real Anthropic client"):
        anthropic.Anthropic(api_key=KEY)
    with pytest.raises(pytest.fail.Exception, match="real Anthropic client"):
        anthropic.AsyncAnthropic(api_key=KEY)


def test_AI_23_the_real_writer_cannot_reach_the_network_in_a_test() -> None:
    real = summary_writer(settings(KEY))
    assert real is not None
    # A BaseException: the writer's `except Exception` does not turn it into an error.
    with pytest.raises(pytest.fail.Exception, match="real Anthropic client"):
        real.write(system="s", facts="f")


# --- AI-24: one request, no retries, text by block type, errors mapped ----------------


def test_AI_24_one_request_with_the_model_timeout_and_no_retries() -> None:
    sdk = FakeSdk(answer=reply(("thinking", ""), ("text", "บรรทัดแรก\n"), ("text", "บรรทัดสอง")))
    assert writer(sdk, "claude-haiku-5-5").write(system="SYSTEM", facts="FACTS") == (
        "บรรทัดแรก\nบรรทัดสอง"
    )
    assert sdk.built == [{"api_key": KEY, "timeout": TIMEOUT_SECONDS, "max_retries": 0}]
    assert TIMEOUT_SECONDS == 8.0
    assert sdk.calls == [
        {
            "model": "claude-haiku-5-5",
            "max_tokens": MAX_TOKENS,
            "system": "SYSTEM",
            "messages": [{"role": "user", "content": "FACTS"}],
            "output_config": {"effort": "low"},
        }
    ]
    assert sdk.closed == 1


@pytest.mark.parametrize(
    ("error", "raised"),
    [
        (anthropic.APITimeoutError(request=REQUEST), WriterTimeoutError),
        (anthropic.APIConnectionError(request=REQUEST), WriterError),
        (
            anthropic.InternalServerError(
                "boom", response=httpx2.Response(500, request=REQUEST), body=None
            ),
            WriterError,
        ),
        (
            anthropic.RateLimitError(
                "slow down", response=httpx2.Response(429, request=REQUEST), body=None
            ),
            WriterError,
        ),
        (
            anthropic.AuthenticationError(
                "bad key", response=httpx2.Response(401, request=REQUEST), body=None
            ),
            WriterError,
        ),
        (RuntimeError("anything else"), WriterError),
    ],
)
def test_AI_24_sdk_errors_become_timeout_or_api_error_and_the_client_is_closed(
    error: Exception, raised: type[Exception]
) -> None:
    sdk = FakeSdk(error=error)
    with pytest.raises(raised):
        writer(sdk).write(system="s", facts="f")
    assert len(sdk.calls) == 1  # no retry
    assert sdk.closed == 1


@pytest.mark.parametrize(
    "answer",
    [
        reply(("text", "ไม่ตอบ"), stop="refusal"),
        reply(("thinking", ""), stop="max_tokens"),  # thinking used the whole budget
        reply(("thinking", "")),
        reply(("text", "  \n ")),
    ],
)
def test_AI_24_a_refusal_a_cut_off_or_an_empty_reply_is_an_api_error(answer: Any) -> None:
    with pytest.raises(WriterError):
        writer(FakeSdk(answer=answer)).write(system="s", facts="f")


def test_AI_24_an_error_never_carries_the_key_or_the_prompt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    sdk = FakeSdk(error=RuntimeError(f"failed with {KEY} and SECRET-PROMPT"))
    with pytest.raises(WriterError) as raised:
        writer(sdk).write(system="SECRET-PROMPT", facts="SECRET-FACTS")
    assert str(raised.value) == "RuntimeError"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
    assert KEY not in caplog.text
    assert "SECRET" not in caplog.text
