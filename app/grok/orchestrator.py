from __future__ import annotations

import json
import logging
from typing import Any

from app.config.settings import Settings
from app.grok.client import GrokClient, load_system_prompt
from app.grok.run_trace import GrokRunTrace
from app.models.slack_events import ThreadContext
from app.tools.dispatcher import ToolDispatcher
from app.tools.registry import tool_definitions_openai

logger = logging.getLogger(__name__)


def _format_thread_for_prompt(ctx: ThreadContext) -> str:
    lines: list[str] = []
    lines.append(f"channel_id={ctx.channel_id}")
    lines.append(f"thread_ts={ctx.thread_ts}")
    lines.append("thread_messages:")
    for m in ctx.messages:
        who = m.user_id or m.role
        urls = ", ".join(m.image_urls) if m.image_urls else ""
        url_part = f" image_urls=[{urls}]" if urls else ""
        lines.append(f"- ts={m.ts} user={who}{url_part}\n  {m.text}")
    return "\n".join(lines)


class GrokOrchestrator:
    """
    Sends structured Slack thread context to Grok with tool definitions.
    Runs a small tool-calling loop and returns final assistant text for Slack.
    """

    def __init__(self, settings: Settings, grok: GrokClient, tools: ToolDispatcher) -> None:
        self._settings = settings
        self._grok = grok
        self._tools = tools

    async def run(self, *, thread: ThreadContext, trace: GrokRunTrace | None = None) -> tuple[str, GrokRunTrace]:
        trace = trace or GrokRunTrace()
        system = load_system_prompt()
        user_block = _format_thread_for_prompt(thread)

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
            logger.info("grok_round_start round=%s", rounds)
            try:
                text, tool_calls = await self._grok.chat_with_tools(
                    messages=messages, tools=tools, tool_choice="auto"
                )
            except Exception:
                msg = (
                    "I could not reach the AI service right now. "
                    "Please try again in a moment."
                )
                return msg, trace

            if not tool_calls:
                if text:
                    logger.info("grok_final_text rounds=%s", rounds)
                    return text, trace
                return "I did not get a usable response. Please try again.", trace

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
                    args = {}
                logger.info("grok_tool_call name=%s", name)
                try:
                    result = await self._tools.dispatch(name, args)
                except Exception:
                    logger.exception("tool_dispatch_failed name=%s", name)
                    result = {"ok": False, "error": "tool_dispatch_failed"}

                trace.record_tool(name, result)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, default=str),
                    }
                )

        return (
            "I hit the maximum number of tool steps for one request. "
            "Please continue in a new message with any missing details.",
            trace,
        )
