"""
Format concise Slack text for generate_report outcomes (operator summary + status + flags).
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
    """
    Build the body under the OUTCOME header (no mode prefix — pipeline adds that).
    """
    lines: list[str] = []
    op = gr.get("operator_summary")
    if isinstance(op, str) and op.strip():
        lines.append(f"*Summary:* {_truncate(op, 220)}")

    rid = gr.get("report_id")
    st = gr.get("status")
    if rid:
        lines.append(f"*Report ID:* `{rid}`")
    if st:
        lines.append(f"*Status:* {st}")

    pdf = gr.get("pdf_url")
    if isinstance(pdf, str) and pdf.strip() and pdf.startswith("https://"):
        lines.append(f"*PDF:* {pdf}")

    msg = gr.get("message")
    if isinstance(msg, str) and msg.strip() and not lines:
        lines.append(_truncate(msg, 400))

    flags = gr.get("flags")
    if isinstance(flags, dict) and flags:
        try:
            flag_str = json.dumps(flags, default=str)
        except TypeError:
            flag_str = str(flags)
        lines.append(f"*Flags:* {_truncate(flag_str, 180)}")

    backend_mode = gr.get("backend_mode")
    if backend_mode == "mock_only":
        lines.append("_Mock mode — backend report API not called._")

    if not lines:
        return "Report step finished."

    return "\n".join(lines)


def format_generate_report_failed_body(gr: dict[str, Any]) -> str:
    """Concise failure text for Slack (under Failed header)."""
    lines: list[str] = []
    msg = gr.get("message")
    if isinstance(msg, str) and msg.strip():
        lines.append(_truncate(msg, 350))
    http = gr.get("http_status")
    if http is not None:
        lines.append(f"*HTTP:* {http}")
    raw = gr.get("raw")
    if isinstance(raw, dict) and raw.get("error"):
        lines.append(f"*Error:* `{raw.get('error')}`")
    rs = gr.get("response_log_summary")
    if isinstance(rs, dict) and rs.get("error_tag"):
        lines.append(f"*Backend:* {rs.get('error_tag')}")
    if not lines:
        return "Report generation failed."
    return "\n".join(lines)
