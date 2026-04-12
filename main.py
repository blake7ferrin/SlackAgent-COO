from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api.routes import create_api_router, mount_slack_handler
from app.config.settings import get_settings
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from app.slack.bolt_app import create_bolt_app, resolve_bot_user_id
from app.utils.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

bolt_app, pipeline = create_bolt_app(settings)

slack_handler = AsyncSlackRequestHandler(bolt_app).handle

app = FastAPI(title="Home Service Slack Orchestrator", version="0.1.0")
app.include_router(create_api_router())
mount_slack_handler(app, slack_handler)


@app.on_event("startup")
async def _startup() -> None:
    bot_user_id = await resolve_bot_user_id(settings)
    pipeline.set_bot_user_id(bot_user_id)
    logger.info(
        "app_startup host=%s port=%s bot_user_id=%s",
        settings.host,
        settings.port,
        bot_user_id or "unknown",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
