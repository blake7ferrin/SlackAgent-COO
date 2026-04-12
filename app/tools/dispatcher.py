from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.config.settings import Settings
from app.tools import implementations as impl
from app.tools.backend_client import BackendClient
from app.tools.schemas import (
    CreateEstimateInput,
    FlagOpportunityInput,
    GenerateReportInput,
    HousecallProSyncInput,
    RequestMissingDataInput,
)

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Maps Grok function names to async implementations."""

    def __init__(self, backend: BackendClient, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        logger.info("tool_dispatch_selected tool=%s", name)
        try:
            if name == "generate_report":
                model = GenerateReportInput.model_validate(args)
                out = await impl.generate_report(model, self._backend, self._settings)
                dumped = out.model_dump()
                logger.info(
                    "tool_dispatch_result tool=generate_report ok=%s backend_mode=%s http_status=%s",
                    dumped.get("ok"),
                    dumped.get("backend_mode"),
                    dumped.get("http_status"),
                )
                return dumped
            if name == "create_estimate":
                model = CreateEstimateInput.model_validate(args)
                out = await impl.create_estimate(model, self._backend)
                dumped = out.model_dump()
                logger.info("tool_dispatch_result tool=create_estimate ok=%s", dumped.get("ok"))
                return dumped
            if name == "housecall_pro_sync":
                model = HousecallProSyncInput.model_validate(args)
                out = await impl.housecall_pro_sync(model, self._backend)
                dumped = out.model_dump()
                logger.info("tool_dispatch_result tool=housecall_pro_sync ok=%s", dumped.get("ok"))
                return dumped
            if name == "flag_opportunity":
                model = FlagOpportunityInput.model_validate(args)
                out = await impl.flag_opportunity(model, self._backend)
                dumped = out.model_dump()
                logger.info("tool_dispatch_result tool=flag_opportunity ok=%s", dumped.get("ok"))
                return dumped
            if name == "request_missing_data":
                model = RequestMissingDataInput.model_validate(args)
                out = await impl.request_missing_data(model)
                dumped = out.model_dump()
                logger.info("tool_dispatch_result tool=request_missing_data ok=%s", dumped.get("ok"))
                return dumped
        except ValidationError as e:
            logger.warning("tool_validation_error name=%s err=%s", name, e.errors())
            return {"ok": False, "error": "validation_error", "details": json.loads(e.json())}

        logger.warning("unknown_tool name=%s", name)
        return {"ok": False, "error": "unknown_tool", "name": name}
