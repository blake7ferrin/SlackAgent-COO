from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path

import httpx
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from app.config.settings import Settings
from app.grok.errors import GrokTimeoutError

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.txt"


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
    if isinstance(exc, APITimeoutError):
        return True
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIConnectionError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return True
    return False


class GrokClient:
    """Async wrapper around the OpenAI-compatible xAI Grok API with retry."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        timeout = httpx.Timeout(float(settings.grok_request_timeout_seconds))
        self._client = AsyncOpenAI(
            api_key=settings.xai_api_key.get_secret_value(),
            base_url=settings.xai_base_url,
            timeout=timeout,
        )
        self._max_retries = settings.grok_max_retries
        self._retry_base = settings.grok_retry_base_delay

    @property
    def model(self) -> str:
        return self._settings.xai_model

    async def chat_with_tools(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str | dict | None = "auto",
        temperature: float = 0.2,
    ) -> tuple[str | None, list[dict]]:
        """
        Returns (assistant_text, tool_calls) where tool_calls is a list of dicts:
        {"id", "name", "arguments": str}

        Retries transient errors (5xx, rate-limit, connection, timeout) with
        exponential backoff + jitter.
        """
        last_exc: BaseException | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=temperature,
                )
                if attempt > 1:
                    logger.info("grok_request_recovered attempt=%s", attempt)

                choice = resp.choices[0].message
                text = (choice.content or "").strip() or None
                tool_calls: list[dict] = []
                if choice.tool_calls:
                    for tc in choice.tool_calls:
                        tool_calls.append(
                            {
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            }
                        )

                usage = getattr(resp, "usage", None)
                if usage:
                    logger.info(
                        "grok_usage prompt_tokens=%s completion_tokens=%s total_tokens=%s model=%s",
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        self.model,
                    )

                return text, tool_calls

            except APITimeoutError as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt == self._max_retries:
                    logger.warning(
                        "grok_request_timeout attempt=%s/%s", attempt, self._max_retries
                    )
                    raise GrokTimeoutError("Grok API request timed out") from None

            except (OpenAIError, APIError) as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt == self._max_retries:
                    logger.exception(
                        "grok_request_failed error=%s attempt=%s/%s",
                        type(exc).__name__,
                        attempt,
                        self._max_retries,
                    )
                    raise

            # Exponential backoff with jitter
            delay = self._retry_base * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "grok_request_retrying error=%s attempt=%s/%s delay=%.1fs",
                type(last_exc).__name__,
                attempt,
                self._max_retries,
                delay,
            )
            await asyncio.sleep(delay)

        # Should not reach here, but safety net
        raise last_exc  # type: ignore[misc]
