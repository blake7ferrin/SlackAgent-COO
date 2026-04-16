from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config.settings import Settings
from app.grok.client import GrokClient, load_system_prompt
from app.grok.errors import GrokTimeoutError
from app.grok.run_trace import GrokRunTrace
from app.models.slack_events import ThreadContext
from app.tools.dispatcher import ToolDispatcher
from app.tools.registry import tool_definitions_openai

logger = logging.getLogger(__name__)


def _format_thread_for_prompt(ctx: ThreadContext, max_messages: int) -> str:
    """Format thread context for Grok, truncating to the newest max_messages."""
    messages = ctx.messages
    truncated = False
    if len(messages) > max_messages:
        messages = messages[-max_messages:]
        truncated = True

    lines: list[str] = []
    lines.append(f"channel_id={ctx.channel_id}")
    lines.append(f"thread_ts={ctx.thread_ts}")
    if truncated:
        lines.append(f"(thread truncated to newest {max_messages} of {len(ctx.messages)} messages)")
    lines.append("thread_messages:")
    for m in messages:
        who = m.user_id or m.role
        urls = ", ".join(m.image_urls) if m.image_urls else ""
        url_part = f" image_urls=[{urls}]" if urls else ""
        lines.append(f"- ts={m.ts} user={who}{url_part}\n  {m.text}")
    return "\n".join(lines)


class GrokOrchestrator:
    """
    Sends structured Slack thread context to Grok with tool definitions.
    Runs a tool-calling loop and returns final assistant text for Slack.
    """

    def __init__(self, settings: Settings, grok: GrokClient, tools: ToolDispatcher) -> None:
        self._settings = settings
        self._grok = grok
        self._tools = tools

    async def run(self, *, thread: ThreadContext, trace: GrokRunTrace | None = None) -> tuple[str, GrokRunTrace]:
        trace = trace or GrokRunTrace()
        system = load_system_prompt()
        user_block = _format_thread_for_prompt(thread, self._settings.max_thread_messages)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Slack thread context follows. Decide the next operational step.\n\n"
                    f"{user_block}"
                ),
            },
        ]

        tools = tool_definitions_openai()
        rounds = 0

        while rounds < self._settings.grok_max_tool_rounds:
            rounds += 1
            logger.info("grok_round_start round=%s channel=%s thread_ts=%s", rounds, thread.channel_id, thread.thread_ts)
            try:
                text, tool_calls = await asyncio.wait_for(
                    self._grok.chat_with_tools(
                        messages=messages, tools=tools, tool_choice="auto"
                    ),
                    timeout=float(self._settings.grok_request_timeout_seconds),
                )
            except GrokTimeoutError:
                logger.warning("grok_orchestration_timeout source=grok_client channel=%s", thread.channel_id)
                return (
                    "I'm taking too long to respond right now. Try sending your message again in a moment.",
                    trace,
                )
            except asyncio.TimeoutError:
                logger.warning("grok_orchestration_timeout source=wait_for channel=%s", thread.channel_id)
                return (
                    "I'm taking too long to respond right now. Try sending your message again in a moment.",
                    trace,
                )
            except Exception as exc:
                logger.exception(
                    "grok_orchestration_failed error_type=%s error=%s model=%s base_url=%s channel=%s",
                    type(exc).__name__,
                    str(exc),
                    self._grok.model,
                    self._settings.xai_base_url,
                    thread.channel_id,
                )
                return (
                    "I couldn't connect to the AI service. Please try again in a moment — if it keeps happening, let your ops lead know.",
                    trace,
                )

            if not tool_calls:
                if text:
                    logger.info("grok_final_text rounds=%s channel=%s", rounds, thread.channel_id)
                    return text, trace
                logger.warning("grok_empty_response rounds=%s channel=%s", rounds, thread.channel_id)
                return "I wasn't able to process that. Could you rephrase or add more detail?", trace

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": text if text is not None else "",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)

            for tc in tool_calls:
                name = tc["name"]
                raw_args = tc["arguments"]
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    logger.warning("grok_malformed_tool_args name=%s raw=%s", name, raw_args[:200])
                    args = {}
                logger.info("grok_tool_call name=%s channel=%s", name, thread.channel_id)
                try:
                    tool_timeout = float(self._settings.backend_http_timeout_seconds) + 15.0
                    result = await asyncio.wait_for(
                        self._tools.dispatch(name, args),
                        timeout=tool_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning("tool_dispatch_timeout name=%s channel=%s", name, thread.channel_id)
                    result = {"ok": False, "error": "tool_timeout", "message": "The backend took too long to respond."}
                except Exception:
                    logger.exception("tool_dispatch_failed name=%s channel=%s", name, thread.channel_id)
                    result = {"ok": False, "error": "tool_dispatch_failed", "message": "Something went wrong calling the backend."}

                trace.record_tool(name, result)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, default=str),
                    }
                )

        return (
            "I've used up my processing steps for this message. "
            "Send a follow-up with any remaining details and I'll pick up where I left off.",
            trace,
        )
