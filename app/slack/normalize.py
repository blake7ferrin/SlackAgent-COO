from __future__ import annotations

import logging
from typing import Any

from app.models.slack_events import FileMeta, NormalizedSlackEvent
from app.services.context_builder import file_meta_from_slack_file_obj

logger = logging.getLogger(__name__)


def normalized_from_message_event(event: dict[str, Any], *, event_id: str | None) -> NormalizedSlackEvent | None:
    """Map a Slack `message` event into our normalized shape. Returns None if should ignore."""
    if event.get("type") != "message":
        return None

    subtype = event.get("subtype")
    if subtype in {
        "message_deleted",
        "message_changed",
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "channel_archive",
        "channel_unarchive",
        "pinned_message",
        "unpinned_message",
    }:
        return None

    channel_id = event.get("channel")
    if not channel_id:
        return None

    user_id = event.get("user")
    bot_id = event.get("bot_id")
    is_bot_message = bool(bot_id) or subtype == "bot_message"

    text = event.get("text") or ""
    ts = event.get("ts") or event.get("event_ts")
    if not ts:
        return None

    thread_ts = event.get("thread_ts") or ts

    files: list[FileMeta] = []
    for f in event.get("files") or []:
        if isinstance(f, dict):
            files.append(file_meta_from_slack_file_obj(f))

    return NormalizedSlackEvent(
        event_id=event_id,
        team_id=event.get("team"),
        channel_id=channel_id,
        user_id=user_id,
        message_ts=str(ts),
        thread_ts=str(thread_ts),
        text=text,
        event_type="message",
        subtype=subtype,
        is_bot_message=is_bot_message,
        files=files,
    )


async def enrich_file_shared(
    client: Any,
    *,
    file_id: str,
    channel_id: str | None,
    user_id: str | None,
    event_id: str | None,
) -> NormalizedSlackEvent | None:
    """Use files.info to build a normalized event for file uploads."""
    resp = await client.files_info(file=file_id)
    if not resp.get("ok"):
        logger.warning("files_info_failed file_id=%s err=%s", file_id, resp.get("error"))
        return None
    f = resp.get("file") or {}
    ch = channel_id
    thread_ts: str | None = None

    shares = f.get("shares") or {}
    if not ch:
        for scope in ("public", "private"):
            inner = shares.get(scope) or {}
            if inner:
                # pick first channel key
                ch = next(iter(inner.keys()), None)
                break

    if not ch:
        logger.warning("file_shared_missing_channel file_id=%s", file_id)
        return None

    # Attempt to find a message ts in shares for threading
    for scope in ("public", "private"):
        inner = shares.get(scope) or {}
        msgs = inner.get(ch) or []
        if msgs and isinstance(msgs, list):
            first = msgs[0]
            if isinstance(first, dict) and first.get("ts"):
                thread_ts = str(first["ts"])
                break
            if isinstance(first, (list, tuple)) and first:
                thread_ts = str(first[0])
                break

    if not thread_ts:
        thread_ts = str(f.get("timestamp") or f.get("created") or "")

    if not thread_ts:
        logger.warning("file_shared_missing_thread_ts file_id=%s channel=%s", file_id, ch)
        return None

    meta = file_meta_from_slack_file_obj(f if isinstance(f, dict) else {})
    name = meta.name or file_id
    text = f"[file_shared] {name}"

    return NormalizedSlackEvent(
        event_id=event_id,
        team_id=None,
        channel_id=str(ch),
        user_id=user_id,
        message_ts=str(thread_ts),
        thread_ts=str(thread_ts),
        text=text,
        event_type="file_shared",
        subtype=None,
        is_bot_message=False,
        files=[meta],
    )
