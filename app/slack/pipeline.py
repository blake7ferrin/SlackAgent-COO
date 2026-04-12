from __future__ import annotations

import asyncio
import logging

from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from app.config.settings import Settings
from app.grok.client import GrokClient
from app.grok.orchestrator import GrokOrchestrator
from app.models.slack_events import NormalizedSlackEvent
from app.grok.run_trace import GrokRunTrace
from app.services.context_builder import ContextBuilder
from app.services.slack_replier import SlackReplyService
from app.services.slack_reply_format import SlackReplyMode, format_slack_reply
from app.services.report_slack_reply import (
    format_generate_report_completed_body,
    format_generate_report_failed_body,
)
from app.services.thread_readiness import assess_thread_readiness
from app.slack.dedup import RecentDedup
from app.slack.normalize import enrich_file_shared, normalized_from_message_event
from app.tools.backend_client import BackendClient
from app.tools.dispatcher import ToolDispatcher

logger = logging.getLogger(__name__)


class OrchestrationPipeline:
    """Wires Slack events → context → Grok → Slack reply."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._dedup = RecentDedup()
        self._bot_user_id: str | None = None

        self._backend = BackendClient(settings)
        self._tools = ToolDispatcher(self._backend, settings)
        self._grok = GrokClient(settings)
        self._orchestrator = GrokOrchestrator(settings, self._grok, self._tools)

    def set_bot_user_id(self, bot_user_id: str | None) -> None:
        self._bot_user_id = bot_user_id

    def bot_is_mentioned_in_text(self, text: str | None) -> bool:
        if not self._bot_user_id or not text:
            return False
        return self._bot_user_id in text

    def _is_duplicate(self, body: dict) -> bool:
        eid = body.get("event_id")
        if eid:
            return self._dedup.is_duplicate(f"evt:{eid}")
        event = body.get("event") or {}
        key = f"fallback:{event.get('channel')}:{event.get('ts') or event.get('event_ts')}:{event.get('user')}"
        return self._dedup.is_duplicate(key)

    def _should_ignore_bot_loop(self, event: dict) -> bool:
        if event.get("bot_id"):
            return True
        if event.get("subtype") == "bot_message":
            return True
        uid = event.get("user")
        if self._bot_user_id and uid == self._bot_user_id:
            return True
        return False

    async def process_user_turn(self, *, client: AsyncWebClient, norm: NormalizedSlackEvent, event: dict) -> None:
        if norm.is_bot_message or self._should_ignore_bot_loop(event):
            logger.info("slack_ignore_bot_message channel=%s ts=%s", norm.channel_id, norm.message_ts)
            return

        # De-dupe Slack delivering the same user message via multiple event types (e.g. message + app_mention)
        if self._dedup.is_duplicate(f"msg:{norm.channel_id}:{norm.message_ts}"):
            return

        thread_ts = norm.thread_ts or norm.message_ts
        ctx_builder = ContextBuilder(client)
        replier = SlackReplyService(client)

        thread = await ctx_builder.build_thread_context(
            channel_id=norm.channel_id,
            thread_ts=str(thread_ts),
            extra_files=norm.files,
        )

        logger.info(
            "orchestration_start channel=%s thread_ts=%s messages=%s",
            norm.channel_id,
            thread_ts,
            len(thread.messages),
        )

        readiness = assess_thread_readiness(thread)
        if not readiness.ok:
            body = format_slack_reply(SlackReplyMode.MISSING_INFORMATION, readiness.user_message)
            posted = await replier.post_thread_reply(
                channel_id=norm.channel_id, thread_ts=str(thread_ts), text=body
            )
            logger.info(
                "slack_outcome mode=missing_information posted=%s channel=%s thread_ts=%s",
                posted,
                norm.channel_id,
                thread_ts,
            )
            return

        processing = format_slack_reply(
            SlackReplyMode.PROCESSING,
            "Reviewing the thread and coordinating the next step…",
        )
        await replier.post_thread_reply(
            channel_id=norm.channel_id, thread_ts=str(thread_ts), text=processing
        )

        trace = GrokRunTrace()
        try:
            reply, trace = await asyncio.wait_for(
                self._orchestrator.run(thread=thread, trace=trace),
                timeout=float(self._settings.orchestration_timeout_seconds),
            )
        except asyncio.TimeoutError:
            trace.timed_out = True
            logger.warning(
                "orchestration_timeout channel=%s thread_ts=%s limit_s=%s",
                norm.channel_id,
                thread_ts,
                self._settings.orchestration_timeout_seconds,
            )
            reply = (
                "This request took too long and timed out. "
                "Please try again with a shorter thread or fewer attachments."
            )

        rl = reply.lower()
        if "generate_report" in trace.tools_called and trace.generate_report_result is not None:
            gr = trace.generate_report_result
            outcome_ok = bool(gr.get("ok"))
            mode = SlackReplyMode.OUTCOME
            if outcome_ok:
                reply = format_generate_report_completed_body(gr)
            else:
                reply = format_generate_report_failed_body(gr)
        elif "request_missing_data" in trace.tools_called:
            mode = SlackReplyMode.MISSING_INFORMATION
            outcome_ok = None
        elif trace.tools_called and trace.last_tool_ok is False:
            mode = SlackReplyMode.OUTCOME
            outcome_ok = False
        elif trace.timed_out or (
            not trace.tools_called
            and (
                "could not reach the ai service" in rl
                or "did not get a usable response" in rl
                or "maximum number of tool steps" in rl
                or "timed out" in rl
            )
        ):
            mode = SlackReplyMode.OUTCOME
            outcome_ok = False
        else:
            mode = SlackReplyMode.OUTCOME
            outcome_ok = True

        body = format_slack_reply(mode, reply, outcome_ok=outcome_ok)
        posted = await replier.post_thread_reply(
            channel_id=norm.channel_id, thread_ts=str(thread_ts), text=body
        )
        logger.info(
            "slack_outcome mode=%s posted=%s channel=%s thread_ts=%s tools=%s generate_report_backend=%s http_status=%s",
            mode.value,
            posted,
            norm.channel_id,
            thread_ts,
            trace.tools_called,
            (trace.generate_report_result or {}).get("backend_mode"),
            (trace.generate_report_result or {}).get("http_status"),
        )

    async def handle_normalized(
        self,
        *,
        client: AsyncWebClient,
        body: dict,
        event: dict,
    ) -> None:
        if self._is_duplicate(body):
            return

        norm = normalized_from_message_event(event, event_id=body.get("event_id"))
        if not norm:
            return
        await self.process_user_turn(client=client, norm=norm, event=event)

    async def handle_file_shared(self, *, client: AsyncWebClient, body: dict, event: dict) -> None:
        if self._is_duplicate(body):
            return
        file_id = event.get("file_id")
        if not file_id:
            return
        if self._dedup.is_duplicate(f"file:{file_id}"):
            return
        norm = await enrich_file_shared(
            client,
            file_id=str(file_id),
            channel_id=event.get("channel_id"),
            user_id=event.get("user_id"),
            event_id=body.get("event_id"),
        )
        if not norm:
            return

        ch = str(norm.channel_id)
        is_im = ch.startswith("D")
        is_channel = ch.startswith("C") or ch.startswith("G")
        if is_channel and not is_im:
            in_thread_reply = norm.thread_ts != norm.message_ts
            if not in_thread_reply:
                logger.info(
                    "slack_ignore_file_shared_top_level channel=%s file_id=%s",
                    ch,
                    file_id,
                )
                return

        resp = await client.files_info(file=str(file_id))
        file_obj = resp.get("file") if resp.get("ok") else None
        files_payload = [file_obj] if isinstance(file_obj, dict) else []

        # Synthetic message event with Slack file dicts so image URLs can be extracted reliably.
        synthetic = {
            "type": "message",
            "channel": norm.channel_id,
            "user": str(norm.user_id) if norm.user_id else None,
            "text": norm.text,
            "ts": norm.message_ts,
            "thread_ts": norm.thread_ts,
            "files": files_payload,
        }
        await self.process_user_turn(client=client, norm=norm, event=synthetic)


def register_handlers(app: AsyncApp, pipeline: OrchestrationPipeline) -> None:
    @app.event("app_mention")
    async def on_app_mention(body, event, client, ack):
        await ack()
        logger.info("slack_event type=app_mention")
        # app_mention events are message events under the hood
        await pipeline.handle_normalized(client=client, body=body, event=event)

    @app.event("message")
    async def on_message(body, event, client, ack):
        await ack()
        ev = dict(event)
        channel_type = ev.get("channel_type")
        subtype = ev.get("subtype")

        # Ignore edits (often subtype message_changed with nested message)
        if subtype == "message_changed":
            return

        # Channels: channel_type may be missing for channel messages; rely on event channel prefix
        ch = str(ev.get("channel") or "")
        is_im = channel_type == "im" or ch.startswith("D")
        is_channel = ch.startswith("C") or ch.startswith("G")

        if not (is_im or is_channel):
            return

        # Reduce noise in public/private channels: only thread replies or explicit @mentions of this bot.
        # (Top-level @mentions are also delivered as `app_mention`; message de-dupe prevents double work.)
        if is_channel and not is_im:
            thread_ts = ev.get("thread_ts")
            ts = ev.get("ts")
            in_thread_reply = bool(thread_ts and ts and thread_ts != ts)
            mentioned = pipeline.bot_is_mentioned_in_text(ev.get("text"))
            if not (in_thread_reply or mentioned):
                logger.info("slack_ignore_channel_top_level channel=%s ts=%s", ch, ts)
                return

        logger.info("slack_event type=message channel=%s subtype=%s", ch, subtype)
        await pipeline.handle_normalized(client=client, body=body, event=ev)

    @app.event("file_shared")
    async def on_file_shared(body, event, client, ack):
        await ack()
        logger.info("slack_event type=file_shared")
        await pipeline.handle_file_shared(client=client, body=body, event=event)
