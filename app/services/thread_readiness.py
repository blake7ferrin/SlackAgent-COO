"""
Lightweight pre-check before invoking Grok: enough thread signal for report workflow.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.models.slack_events import ThreadContext

logger = logging.getLogger(__name__)

_PLACEHOLDER_USER = re.compile(
    r"^\[(?:no text|file_shared|attached images from file upload)\]\s*$",
    re.I,
)
_BOTISH = re.compile(r"^\[bot", re.I)


@dataclass(frozen=True)
class ThreadReadiness:
    ok: bool
    has_usable_notes: bool
    has_https_images: bool
    user_message: str


def _normalize_user_text(text: str) -> str:
    t = (text or "").strip()
    # Slack mrkdwn / links often appear as <url|label> — strip angle blocks loosely
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_usable_note_line(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if _PLACEHOLDER_USER.match(raw):
        return False
    if _BOTISH.match(raw):
        return False
    norm = _normalize_user_text(raw)
    if len(norm) < 20 and len(norm.split()) < 5:
        return False
    return True


def assess_thread_readiness(thread: ThreadContext) -> ThreadReadiness:
    """
    - usable notes: substantive user-authored text in the thread (not placeholders).
    - HTTPS images: any image_urls collected on messages (Slack file metadata only).
    """
    has_images = any(bool(m.image_urls) for m in thread.messages)
    usable = False
    for m in thread.messages:
        if m.role != "user":
            continue
        if _is_usable_note_line(m.text):
            usable = True
            break

    if not usable and not has_images:
        msg = (
            "I need job notes, readings, or at least one photo in this thread to generate a report. "
            "What system or issue are we documenting?"
        )
        logger.info(
            "thread_readiness fail reason=no_notes_no_images channel=%s thread_ts=%s",
            thread.channel_id,
            thread.thread_ts,
        )
        return ThreadReadiness(False, False, False, msg)

    if has_images and not usable:
        msg = (
            "I see photo(s) but no job context yet. In one or two sentences: what was done or observed, "
            "what’s wrong (if anything), and customer or site name if you have it?"
        )
        logger.info(
            "thread_readiness fail reason=images_only_no_context channel=%s thread_ts=%s",
            thread.channel_id,
            thread.thread_ts,
        )
        return ThreadReadiness(False, True, True, msg)

    logger.info(
        "thread_readiness ok channel=%s thread_ts=%s usable_notes=%s images=%s",
        thread.channel_id,
        thread.thread_ts,
        usable,
        has_images,
    )
    return ThreadReadiness(True, usable, has_images, "")
