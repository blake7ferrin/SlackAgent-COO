from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FileMeta(BaseModel):
    """Minimal file metadata we pass to Grok (no invented URLs)."""

    file_id: str
    name: str | None = None
    mimetype: str | None = None
    size_bytes: int | None = None
    url_private: str | None = None
    permalink: str | None = None


class SlackMessagePayload(BaseModel):
    """Subset of Slack message we care about for orchestration."""

    type: str = "message"
    channel: str | None = None
    user: str | None = None
    text: str = ""
    ts: str
    thread_ts: str | None = None
    bot_id: str | None = None
    subtype: str | None = None
    files: list[dict[str, Any]] | None = None


class NormalizedSlackEvent(BaseModel):
    """Single inbound user-visible event after Bolt normalization."""

    event_id: str | None = None
    team_id: str | None = None
    channel_id: str
    user_id: str | None = None
    message_ts: str
    thread_ts: str | None = None
    text: str = ""
    event_type: str
    subtype: str | None = None
    is_bot_message: bool = False
    files: list[FileMeta] = Field(default_factory=list)
    raw_subtype: str | None = None


class ThreadMessage(BaseModel):
    role: str  # "user" | "assistant" | "system" (we use user/assistant)
    user_id: str | None = None
    text: str
    ts: str
    image_urls: list[str] = Field(default_factory=list)


class ThreadContext(BaseModel):
    """Structured thread history for Grok."""

    channel_id: str
    thread_ts: str
    messages: list[ThreadMessage] = Field(default_factory=list)
