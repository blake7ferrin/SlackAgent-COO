"""
Mock/stub tool implementations that call BACKEND_BASE_URL when available.

Replace `post_json` paths and payload shapes with your real backend contract.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.tools.backend_client import BackendClient
from app.tools.schemas import (
    CreateEstimateInput,
    CreateEstimateOutput,
    FlagOpportunityInput,
    FlagOpportunityOutput,
    GenerateReportInput,
    GenerateReportOutput,
    HousecallProSyncInput,
    HousecallProSyncOutput,
    RequestMissingDataInput,
    RequestMissingDataOutput,
)

logger = logging.getLogger(__name__)


def _mock_report_result(inp: GenerateReportInput) -> GenerateReportOutput:
    rid = f"rpt_{uuid.uuid4().hex[:12]}"
    return GenerateReportOutput(
        ok=True,
        report_id=rid,
        status="queued",
        pdf_url=None,
        message=(
            "Report generation accepted (mock). "
            "Replace BackendClient POST /v1/reports with your real endpoint."
        ),
        raw={"mock": True, "thread_ts": inp.thread_ts, "channel_id": inp.channel_id},
    )


async def generate_report(inp: GenerateReportInput, backend: BackendClient) -> GenerateReportOutput:
    """
    Calls the existing report engine via HTTP.

    **Replace** path `/v1/reports` and JSON body with your backend's schema.
    """
    payload: dict[str, Any] = {
        "thread_ts": inp.thread_ts,
        "channel_id": inp.channel_id,
        "job_summary": inp.job_summary,
        "customer_hint": inp.customer_hint,
        "image_urls": [str(u) for u in inp.image_urls],
    }
    ok, data, err = await backend.post_json("/v1/reports", payload)
    if ok and data:
        return GenerateReportOutput(
            ok=True,
            report_id=str(data.get("report_id", "")) or None,
            status=str(data.get("status", "")) or None,
            pdf_url=str(data.get("pdf_url", "")) or None,
            message=str(data.get("message", "")) or None,
            raw=data,
        )
    logger.info("generate_report_fallback_mock err=%s", err)
    return _mock_report_result(inp)


async def create_estimate(inp: CreateEstimateInput, backend: BackendClient) -> CreateEstimateOutput:
    """**Replace** with POST to your estimates service."""
    payload = {
        "thread_ts": inp.thread_ts,
        "channel_id": inp.channel_id,
        "scope_summary": inp.scope_summary,
        "line_items_hint": inp.line_items_hint,
    }
    ok, data, err = await backend.post_json("/v1/estimates", payload)
    if ok and data:
        return CreateEstimateOutput(
            ok=True,
            estimate_id=str(data.get("estimate_id", "")) or None,
            status=str(data.get("status", "")) or None,
            message=str(data.get("message", "")) or None,
            raw=data,
        )
    eid = f"est_{uuid.uuid4().hex[:12]}"
    return CreateEstimateOutput(
        ok=True,
        estimate_id=eid,
        status="draft_mock",
        message=f"Estimate stubbed (backend unavailable: {err}).",
        raw={"mock": True},
    )


async def housecall_pro_sync(inp: HousecallProSyncInput, backend: BackendClient) -> HousecallProSyncOutput:
    """**Replace** with your integration worker/API route."""
    payload = {
        "thread_ts": inp.thread_ts,
        "channel_id": inp.channel_id,
        "action": inp.action,
        "payload_summary": inp.payload_summary,
    }
    ok, data, err = await backend.post_json("/v1/integrations/housecall-pro", payload)
    if ok and data:
        return HousecallProSyncOutput(
            ok=True,
            external_ref=str(data.get("external_ref", "")) or None,
            status=str(data.get("status", "")) or None,
            message=str(data.get("message", "")) or None,
            raw=data,
        )
    ref = f"hcp_{uuid.uuid4().hex[:10]}"
    return HousecallProSyncOutput(
        ok=True,
        external_ref=ref,
        status="queued_mock",
        message=f"Housecall Pro sync stubbed (backend unavailable: {err}).",
        raw={"mock": True},
    )


async def flag_opportunity(inp: FlagOpportunityInput, backend: BackendClient) -> FlagOpportunityOutput:
    """**Replace** with CRM / ops flags endpoint."""
    payload = {
        "thread_ts": inp.thread_ts,
        "channel_id": inp.channel_id,
        "opportunity_type": inp.opportunity_type,
        "rationale": inp.rationale,
    }
    ok, data, err = await backend.post_json("/v1/opportunities/flags", payload)
    if ok and data:
        return FlagOpportunityOutput(
            ok=True,
            flag_id=str(data.get("flag_id", "")) or None,
            status=str(data.get("status", "")) or None,
            message=str(data.get("message", "")) or None,
            raw=data,
        )
    fid = f"flg_{uuid.uuid4().hex[:10]}"
    return FlagOpportunityOutput(
        ok=True,
        flag_id=fid,
        status="logged_mock",
        message=f"Opportunity flag stubbed (backend unavailable: {err}).",
        raw={"mock": True},
    )


async def request_missing_data(inp: RequestMissingDataInput) -> RequestMissingDataOutput:
    """
    Local tool: model asks for missing fields. Slack reply is still sent by the orchestrator's
    final assistant text; this tool exists so the model can structure the missing-data step.
    """
    logger.info(
        "request_missing_data fields=%s",
        inp.missing_fields,
    )
    return RequestMissingDataOutput(
        ok=True,
        recorded=True,
        message=inp.question_for_user,
    )
