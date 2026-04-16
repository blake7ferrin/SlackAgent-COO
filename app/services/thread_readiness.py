"""
Lightweight pre-check before invoking Grok: enough thread signal for report workflow.

The bar is intentionally low — Grok itself can ask for more info if needed.
We only block completely empty threads (no text, no images at all).
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
    reason: str  # ok | no_notes_no_images | images_only_no_context


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
    # Low bar: even short messages like "AC leaking" or "furnace out" are useful.
    # Grok can ask for more detail if needed.
    if len(norm) < 3:
        return False
    return True


def assess_thread_readiness(thread: ThreadContext) -> ThreadReadiness:
    """
    - usable notes: any non-placeholder user text in the thread.
    - HTTPS images: any image_urls collected on messages (Slack file metadata only).

    Only blocks truly empty threads. Thin threads (images-only, short notes)
    are passed through to Grok, which can decide to ask follow-up questions.
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
            "Hey — I need something to work with. Drop some job notes, "
            "readings, or photos in this thread and I'll take it from there."
        )
        logger.info(
            "readiness_outcome reason=no_notes_no_images channel=%s thread_ts=%s",
            thread.channel_id,
            thread.thread_ts,
        )
        return ThreadReadiness(False, False, False, msg, "no_notes_no_images")

    logger.info(
        "readiness_outcome reason=ok channel=%s thread_ts=%s notes=%s images=%s",
        thread.channel_id,
        thread.thread_ts,
        usable,
        has_images,
    )
    return ThreadReadiness(True, usable, has_images, "", "ok")
