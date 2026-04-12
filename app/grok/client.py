from __future__ import annotations

import logging
from pathlib import Path

import httpx
from openai import APIError, APITimeoutError, AsyncOpenAI, OpenAIError

from app.config.settings import Settings
from app.grok.errors import GrokTimeoutError

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.txt"


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


class GrokClient:
    """Thin sync/async wrapper around the OpenAI-compatible xAI Grok API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        timeout = httpx.Timeout(float(settings.grok_request_timeout_seconds))
        self._client = AsyncOpenAI(
            api_key=settings.xai_api_key.get_secret_value(),
            base_url=settings.xai_base_url,
            timeout=timeout,
        )

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
        """
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
            )
        except APITimeoutError:
            logger.warning("grok_request_timeout")
            raise GrokTimeoutError("Grok API request timed out") from None
        except (OpenAIError, APIError) as e:
            logger.exception("grok_request_failed error=%s", type(e).__name__)
            raise

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
        return text, tool_calls
