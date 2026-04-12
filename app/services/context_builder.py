from __future__ import annotations

import logging
import re
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.models.slack_events import FileMeta, ThreadContext, ThreadMessage

logger = logging.getLogger(__name__)

_HTTPS_IMAGE = re.compile(r"https://[^\s<>\"']+\.(?:png|jpe?g|gif|webp)(?:\?[^\s<>\"']*)?", re.I)


def extract_https_image_urls_from_text(text: str) -> list[str]:
    """Extract only bare HTTPS image URLs embedded in message text (not Slack file URLs)."""
    return list(dict.fromkeys(_HTTPS_IMAGE.findall(text or "")))


def file_meta_from_slack_file_obj(f: dict[str, Any]) -> FileMeta:
    url_private = f.get("url_private")
    if url_private and not str(url_private).startswith("https://"):
        url_private = None
    permalink = f.get("permalink")
    if permalink and not str(permalink).startswith("https://"):
        permalink = None
    return FileMeta(
        file_id=str(f.get("id", "")),
        name=f.get("name"),
        mimetype=f.get("mimetype"),
        size_bytes=f.get("size"),
        url_private=str(url_private) if url_private else None,
        permalink=str(permalink) if permalink else None,
    )


def image_urls_from_file_meta(files: list[FileMeta]) -> list[str]:
    """Prefer direct HTTPS image file URLs from Slack metadata (url_private), else permalink."""
    out: list[str] = []
    for fm in files:
        if fm.mimetype and str(fm.mimetype).lower().startswith("image/"):
            candidate = fm.url_private or fm.permalink
            if candidate and candidate.startswith("https://"):
                out.append(candidate)
    return list(dict.fromkeys(out))


class ContextBuilder:
    """Fetches and normalizes Slack thread context for Grok."""

    def __init__(self, client: AsyncWebClient) -> None:
        self._client = client

    async def build_thread_context(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        extra_files: list[FileMeta] | None = None,
    ) -> ThreadContext:
        """
        Loads conversation replies and normalizes messages.
        `thread_ts` should be the root message ts of the thread.
        """
        extra_files = extra_files or []
        cursor: str | None = None
        messages_raw: list[dict[str, Any]] = []

        while True:
            resp = await self._client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                cursor=cursor,
                limit=200,
                include_all_metadata=True,
            )
            if not resp.get("ok"):
                logger.warning(
                    "conversations_replies_failed channel=%s thread_ts=%s error=%s",
                    channel_id,
                    thread_ts,
                    resp.get("error"),
                )
                break
            messages_raw.extend(resp.get("messages", []) or [])
            cursor = (resp.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

        messages_raw.sort(key=lambda m: float(m.get("ts", "0")))

        thread_messages: list[ThreadMessage] = []
        for m in messages_raw:
            text = (m.get("text") or "").strip()
            uid = m.get("user")
            ts = str(m.get("ts", ""))
            subtype = m.get("subtype")
            if subtype in {"message_deleted", "channel_join", "channel_leave", "channel_topic"}:
                continue

            files_payload = m.get("files") or []
            file_metas = [file_meta_from_slack_file_obj(f) for f in files_payload if isinstance(f, dict)]
            embedded = extract_https_image_urls_from_text(text)
            from_files = image_urls_from_file_meta(file_metas)
            image_urls = list(dict.fromkeys([*from_files, *embedded]))

            # Represent assistant/bot messages distinctly in text only (no fake user ids)
            if m.get("bot_id") or subtype == "bot_message":
                role = "assistant"
                label = m.get("username") or m.get("bot_id") or "bot"
                display = text if text else f"[bot message subtype={subtype}]"
                thread_messages.append(
                    ThreadMessage(role=role, user_id=label, text=display, ts=ts, image_urls=image_urls)
                )
            else:
                thread_messages.append(
                    ThreadMessage(role="user", user_id=uid, text=text or "[no text]", ts=ts, image_urls=image_urls)
                )

        # Attach any extra files (e.g. from file_shared) to the latest user message if possible
        if extra_files:
            urls = image_urls_from_file_meta(extra_files)
            if urls:
                for tm in reversed(thread_messages):
                    if tm.role == "user":
                        merged = list(dict.fromkeys([*tm.image_urls, *urls]))
                        tm.image_urls = merged
                        break
                else:
                    thread_messages.append(
                        ThreadMessage(
                            role="user",
                            user_id=None,
                            text="[attached images from file upload]",
                            ts=thread_ts,
                            image_urls=urls,
                        )
                    )

        return ThreadContext(channel_id=channel_id, thread_ts=thread_ts, messages=thread_messages)
