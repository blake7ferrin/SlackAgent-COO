"""
Map Grok-validated GenerateReportInput → backend JSON contract.

Keep request-shape logic out of orchestrator and thin tool implementations.
"""

from __future__ import annotations

import json
from typing import Any

from app.tools.schemas import GenerateReportInput

# Keys the backend may return that we surface to Slack / logs (extend as contract evolves).
_BACKEND_FLAG_KEYS = ("flags", "warnings", "alerts", "validation_flags")
_BACKEND_SUMMARY_KEYS = ("operator_summary", "short_summary", "summary")


def build_backend_report_payload(inp: GenerateReportInput) -> dict[str, Any]:
    """
    Normalized body for POST /v1/reports (adjust field names here when backend contract changes).
    """
    return {
        "thread_ts": inp.thread_ts,
        "channel_id": inp.channel_id,
        "job_summary": inp.job_summary,
        "customer_hint": inp.customer_hint,
        "image_urls": [str(u) for u in inp.image_urls],
    }


def log_summary_report_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Structured, non-secret summary for logs (no full URLs)."""
    urls = payload.get("image_urls") or []
    if not isinstance(urls, list):
        urls = []
    job = payload.get("job_summary")
    job_preview = (job[:120] + "…") if isinstance(job, str) and len(job) > 120 else job
    return {
        "channel_id": payload.get("channel_id"),
        "thread_ts": payload.get("thread_ts"),
        "has_customer_hint": bool(payload.get("customer_hint")),
        "image_count": len(urls),
        "job_summary_chars": len(job) if isinstance(job, str) else 0,
        "job_summary_preview": job_preview,
    }


def log_summary_backend_response(
    data: dict[str, Any] | None,
    *,
    success: bool,
    status_code: int | None,
    error_tag: str | None = None,
) -> dict[str, Any]:
    """Structured summary of backend JSON (no secrets)."""
    out: dict[str, Any] = {
        "success": success,
        "http_status": status_code,
        "error_tag": error_tag,
    }
    if not data:
        return out
    out["report_id"] = data.get("report_id")
    out["status"] = data.get("status")
    out["has_pdf_url"] = bool(data.get("pdf_url"))
    for k in _BACKEND_FLAG_KEYS:
        if k in data and data[k] is not None:
            out["flags_key"] = k
            try:
                out["flags_preview"] = json.dumps(data[k], default=str)[:200]
            except (TypeError, ValueError):
                out["flags_preview"] = str(data[k])[:200]
            break
    return out


def extract_operator_summary_from_response(data: dict[str, Any]) -> str | None:
    for k in _BACKEND_SUMMARY_KEYS:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def extract_flags_from_response(data: dict[str, Any]) -> dict[str, Any] | None:
    for k in _BACKEND_FLAG_KEYS:
        v = data.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            return dict(v)
        if isinstance(v, list) and v:
            return {"items": v}
        if isinstance(v, str) and v.strip():
            return {"note": v.strip()}
    return None
