"""The model that words the summary (04 section 14: the LLMProvider interface).

The app reaches the model only through `Writer`. The real one calls Claude through
the official `anthropic` SDK; the tests pass a fake, and tests/conftest.py fails any
test that builds the real client, so no test reaches the network.

Config, env only (the names config.py already had): LLM_API_KEY (its value is only
passed to the SDK, never logged or printed), LLM_MODEL_PLANNER (default
claude-haiku-5-5) and LLM_PROVIDER (empty or "anthropic"; anything else means no
model, so another provider's key is never sent to Anthropic).
"""

from collections.abc import Callable
from typing import Annotated, Protocol

import anthropic
from anthropic.types import MessageParam, OutputConfigParam
from fastapi import Depends
from pydantic import SecretStr

from app.config import Settings, get_settings

DEFAULT_MODEL = "claude-haiku-5-5"
TIMEOUT_SECONDS = 8.0  # the SDK's per-phase timeout: connect, send, and wait for the answer
MAX_TOKENS = 1024  # room for brief thinking plus 2 to 4 short sentences
# A short wording task: low effort keeps it quick (Haiku 5.5 thinks adaptively).
OUTPUT_CONFIG: OutputConfigParam = {"effort": "low"}


class WriterTimeoutError(Exception):
    """The model did not answer in time."""


class WriterError(Exception):
    """No usable answer: an API or transport error, a refusal, a cut-off or an empty
    reply. The message is a short code, never the prompt or the reply."""


class Writer(Protocol):
    model: str

    def write(self, *, system: str, facts: str) -> str:
        """The model's text for these instructions and facts. Raises WriterTimeoutError or
        WriterError; it never retries."""
        ...


class AnthropicWriter:
    """Claude through the official SDK: one request, no retries (max_retries=0)."""

    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        *,
        client: Callable[..., anthropic.Anthropic] = anthropic.Anthropic,
    ) -> None:
        self.model = model
        self._key = api_key
        self._client = client

    def write(self, *, system: str, facts: str) -> str:
        # Built per call: the key leaves the SecretStr only here, into the SDK.
        client = self._client(
            api_key=self._key.get_secret_value().strip(),
            timeout=TIMEOUT_SECONDS,
            max_retries=0,
        )
        messages: list[MessageParam] = [{"role": "user", "content": facts}]
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                output_config=OUTPUT_CONFIG,
            )
        except anthropic.APITimeoutError:
            raise WriterTimeoutError from None
        except Exception as exc:  # any SDK or transport error: no answer to show
            raise WriterError(type(exc).__name__) from None
        finally:
            client.close()
        if message.stop_reason != "end_turn":  # refusal, max_tokens, ...
            raise WriterError(f"stop_reason={message.stop_reason}")
        # A reply can start with thinking blocks: read the text blocks by type.
        text = "".join(block.text for block in message.content if block.type == "text")
        if not text.strip():
            raise WriterError("empty")
        return text


def summary_writer(settings: Settings) -> Writer | None:
    """The real writer, or None unless LLM_PROVIDER is "anthropic" and the key is set
    (not blank). An unset provider gives None too, so a key meant for another
    provider is never sent to Anthropic. Checks only whether the key is set."""
    provider = (settings.llm_provider or "").strip().lower()
    key = settings.llm_api_key
    if provider != "anthropic" or key is None or not key.get_secret_value().strip():
        return None
    model = (settings.llm_model_planner or "").strip() or DEFAULT_MODEL
    return AnthropicWriter(key, model)


def get_summary_writer(settings: Annotated[Settings, Depends(get_settings)]) -> Writer | None:
    """FastAPI dependency; the tests override it with a fake."""
    return summary_writer(settings)
