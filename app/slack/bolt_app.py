from __future__ import annotations

import logging

from slack_bolt.async_app import AsyncApp
from slack_bolt.authorization import AuthorizeResult
from slack_sdk.web.async_client import AsyncWebClient

from app.config.settings import Settings
from app.slack.pipeline import OrchestrationPipeline, register_handlers

logger = logging.getLogger(__name__)


async def resolve_bot_user_id(settings: Settings) -> str | None:
    """Call auth.test once so we can ignore our own messages and detect mentions."""
    client = AsyncWebClient(token=settings.slack_bot_token.get_secret_value())
    try:
        auth = await client.auth_test()
        if auth.get("ok"):
            return str(auth.get("user_id"))
    except Exception:
        logger.exception("slack_auth_test_failed")
    return None


def create_bolt_app(settings: Settings) -> tuple[AsyncApp, OrchestrationPipeline]:
    """
    Slack Bolt app with token-based installation (single workspace).

    For multi-workspace installs later, replace authorize with an OAuth flow + token store.
    """

    async def authorize(**kwargs) -> AuthorizeResult:  # type: ignore[no-untyped-def]
        return AuthorizeResult(
            enterprise_id=None,
            team_id=None,
            bot_token=settings.slack_bot_token.get_secret_value(),
            bot_id=None,
            bot_user_id=None,
        )

    app = AsyncApp(
        signing_secret=settings.slack_signing_secret.get_secret_value(),
        authorize=authorize,
    )

    pipeline = OrchestrationPipeline(settings)
    register_handlers(app, pipeline)

    return app, pipeline
