"""
Format concise Slack text for generate_report outcomes.
"""

from __future__ import annotations

import json
from typing import Any


def _truncate(s: str, max_len: int) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def format_generate_report_completed_body(gr: dict[str, Any]) -> str:
    """Build the body under the OUTCOME header."""
    lines: list[str] = []
    op = gr.get("operator_summary")
    if isinstance(op, str) and op.strip():
        lines.append(f"*Summary:* {_truncate(op, 220)}")

    rid = gr.get("report_id")
    st = gr.get("status")
    if rid:
        lines.append(f"*Report:* `{rid}`  |  *Status:* {st or 'submitted'}")
    elif st:
        lines.append(f"*Status:* {st}")

    pdf = gr.get("pdf_url")
    if isinstance(pdf, str) and pdf.strip() and pdf.startswith("https://"):
        lines.append(f"<{pdf}|View PDF>")

    flags = gr.get("flags")
    if isinstance(flags, dict) and flags:
        try:
            flag_str = json.dumps(flags, default=str)
        except TypeError:
            flag_str = str(flags)
        lines.append(f"*Flags:* {_truncate(flag_str, 180)}")

    backend_mode = gr.get("backend_mode")
    if backend_mode == "mock_only":
        lines.append("_Mock mode — report API not called. Set BACKEND_GENERATE_REPORT_ENABLED=true for production._")

    msg = gr.get("message")
    if isinstance(msg, str) and msg.strip() and not lines:
        lines.append(_truncate(msg, 400))

    if not lines:
        return "Report submitted."

    return "\n".join(lines)


def format_generate_report_failed_body(gr: dict[str, Any]) -> str:
    """Concise failure text for Slack."""
    msg = gr.get("message")
    if isinstance(msg, str) and msg.strip():
        text = _truncate(msg, 350)
    else:
        text = "The report service didn't respond."

    http = gr.get("http_status")
    raw = gr.get("raw")
    error_tag = None
    if isinstance(raw, dict) and raw.get("error"):
        error_tag = raw["error"]

    details: list[str] = []
    if http is not None:
        details.append(f"HTTP {http}")
    if error_tag:
        details.append(str(error_tag))

    if details:
        text += f"\n_({', '.join(details)})_"

    text += "\nRetry in a moment, or flag your dispatcher if it keeps failing."
    return text
