"""
Standard Slack thread reply headers (3 modes).
"""

from __future__ import annotations

from enum import Enum


class SlackReplyMode(str, Enum):
    MISSING_INFORMATION = "missing_information"
    PROCESSING = "processing"
    OUTCOME = "outcome"  # completed vs failed via success flag


def format_slack_reply(
    mode: SlackReplyMode,
    body: str,
    *,
    outcome_ok: bool | None = None,
) -> str:
    """
    Prefix a consistent operational header; body should be concise Slack-ready text.
    """
    body = (body or "").strip()
    if mode is SlackReplyMode.MISSING_INFORMATION:
        header = ":warning: *Missing information*"
    elif mode is SlackReplyMode.PROCESSING:
        header = ":hourglass_flowing_sand: *Processing*"
    elif mode is SlackReplyMode.OUTCOME:
        if outcome_ok is True:
            header = ":white_check_mark: *Completed*"
        else:
            header = ":x: *Failed*"
    else:
        header = "*Update*"

    if not body:
        return header
    return f"{header}\n{body}"
