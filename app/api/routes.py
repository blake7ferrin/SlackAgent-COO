from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request, Response

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_START_TIME = time.monotonic()


def create_api_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict:
        """Liveness probe — always returns ok if the process is running."""
        return {"status": "ok"}

    @router.get("/healthz")
    async def healthz() -> dict:
        """Readiness probe with basic diagnostics."""
        settings = get_settings()
        uptime = round(time.monotonic() - _START_TIME, 1)
        return {
            "status": "ok",
            "uptime_seconds": uptime,
            "model": settings.xai_model,
            "environment": settings.environment,
            "backend_url_configured": bool(settings.backend_base_url),
            "backend_report_enabled": settings.backend_generate_report_enabled,
        }

    return router


def mount_slack_handler(app, slack_handler) -> None:  # FastAPI app
    """
    Slack Events endpoint.

    `slack_handler` is typically `AsyncSlackRequestHandler(bolt_app).handle`.
    """

    @app.post("/slack/events")
    async def slack_events(req: Request) -> Response:
        return await slack_handler(req)

    logger.info("mounted_route path=/slack/events")
