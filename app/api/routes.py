from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)


def create_api_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

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
