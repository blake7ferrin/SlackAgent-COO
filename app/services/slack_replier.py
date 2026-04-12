from __future__ import annotations

import logging

from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)


class SlackReplyService:
    """Posts assistant responses into the correct Slack thread."""

    def __init__(self, client: AsyncWebClient) -> None:
        self._client = client

    async def post_thread_reply(self, *, channel_id: str, thread_ts: str, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            logger.warning("slack_post_skipped_empty channel=%s thread_ts=%s", channel_id, thread_ts)
            return False
        resp = await self._client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text,
        )
        if not resp.get("ok"):
            logger.warning(
                "chat_postMessage_failed channel=%s thread_ts=%s error=%s",
                channel_id,
                thread_ts,
                resp.get("error"),
            )
            return False
        logger.info("slack_reply_posted channel=%s thread_ts=%s", channel_id, thread_ts)
        return True
