"""Typed input/output models for Grok tools (Pydantic v2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class GenerateReportInput(BaseModel):
    """Payload to request report generation from the existing backend."""

    thread_ts: str = Field(..., description="Slack thread timestamp anchor.")
    channel_id: str = Field(..., description="Slack channel ID where the thread lives.")
    job_summary: str = Field(..., description="Factual summary from the thread only; no invented details.")
    customer_hint: str | None = Field(
        default=None,
        description="Customer name/identifier only if explicitly present in thread.",
    )
    image_urls: list[HttpUrl] = Field(
        default_factory=list,
        description="HTTPS image URLs taken from Slack file metadata only.",
    )


class GenerateReportOutput(BaseModel):
    ok: bool
    report_id: str | None = None
    status: str | None = None
    pdf_url: str | None = None
    message: str | None = None
    raw: dict[str, Any] | None = None


class CreateEstimateInput(BaseModel):
    thread_ts: str
    channel_id: str
    scope_summary: str = Field(..., description="Estimate scope grounded in thread facts.")
    line_items_hint: str | None = Field(
        default=None,
        description="Optional notes; do not invent pricing lines not confirmed by the business.",
    )


class CreateEstimateOutput(BaseModel):
    ok: bool
    estimate_id: str | None = None
    status: str | None = None
    message: str | None = None
    raw: dict[str, Any] | None = None


class HousecallProSyncInput(BaseModel):
    thread_ts: str
    channel_id: str
    action: str = Field(..., description="e.g. sync_job_notes, attach_photos, create_follow_up")
    payload_summary: str = Field(..., description="What to sync, strictly from verified thread content.")


class HousecallProSyncOutput(BaseModel):
    ok: bool
    external_ref: str | None = None
    status: str | None = None
    message: str | None = None
    raw: dict[str, Any] | None = None


class FlagOpportunityInput(BaseModel):
    thread_ts: str
    channel_id: str
    opportunity_type: str = Field(..., description="upsell, replacement, maintenance_plan, etc.")
    rationale: str = Field(..., description="Why this is flagged; cite thread evidence, no fabrication.")


class FlagOpportunityOutput(BaseModel):
    ok: bool
    flag_id: str | None = None
    status: str | None = None
    message: str | None = None
    raw: dict[str, Any] | None = None


class RequestMissingDataInput(BaseModel):
    thread_ts: str
    channel_id: str
    missing_fields: list[str] = Field(
        ...,
        description="Explicit list of missing items (e.g. 'model/serial', 'customer approval').",
    )
    question_for_user: str = Field(
        ...,
        description="Single concise Slack-ready question; no invented facts.",
    )


class RequestMissingDataOutput(BaseModel):
    ok: bool
    recorded: bool = False
    message: str | None = None
