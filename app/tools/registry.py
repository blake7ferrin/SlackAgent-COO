"""
OpenAI-compatible tool definitions for Grok.

Schema JSON is derived from Pydantic models to keep types aligned.
"""

from __future__ import annotations

import json
from typing import Any

from app.tools.schemas import (
    CreateEstimateInput,
    FlagOpportunityInput,
    GenerateReportInput,
    HousecallProSyncInput,
    RequestMissingDataInput,
)


def _parameters(model: type) -> dict[str, Any]:
    # Pydantic v2 JSON schema; strip $defs/$ref complexity for Grok by using model's schema
    schema = model.model_json_schema()
    return schema


def tool_definitions_openai() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "generate_report",
                "description": (
                    "Request report generation from the existing backend/report engine. "
                    "Only call when the thread contains sufficient verified facts. "
                    "Pass only HTTPS image URLs that appeared in Slack file metadata."
                ),
                "parameters": _parameters(GenerateReportInput),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_estimate",
                "description": "Create or draft an estimate via the backend when scope is clear enough.",
                "parameters": _parameters(CreateEstimateInput),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "housecall_pro_sync",
                "description": "Sync notes/photos/summary to Housecall Pro through the backend integration.",
                "parameters": _parameters(HousecallProSyncInput),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "flag_opportunity",
                "description": "Flag a sales/ops opportunity based on explicit thread evidence.",
                "parameters": _parameters(FlagOpportunityInput),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "request_missing_data",
                "description": (
                    "Use when critical information is missing. "
                    "Provides structured missing fields and a concise user question. "
                    "Do not invent missing field values."
                ),
                "parameters": _parameters(RequestMissingDataInput),
            },
        },
    ]


def pretty_tool_list_for_logs() -> str:
    return json.dumps([t["function"]["name"] for t in tool_definitions_openai()])
