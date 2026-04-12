from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import Settings
from app.tools.backend_types import BackendPostResult

logger = logging.getLogger(__name__)


class BackendClient:
    """
    HTTP client for the existing backend (source of truth).
    If requests fail or URL is unreachable, callers should degrade gracefully.
    """

    def __init__(self, settings: Settings) -> None:
        self._base = settings.backend_base_url.rstrip("/")
        t = float(settings.backend_http_timeout_seconds)
        self._timeout = httpx.Timeout(t)

    async def post_json_detailed(
        self, path: str, payload: dict[str, Any]
    ) -> BackendPostResult:
        """
        POST JSON and return status code without raising (for explicit logging).
        """
        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                code = resp.status_code
                if code < 200 or code >= 300:
                    logger.warning("backend_http_error path=%s status=%s", path, code)
                    return BackendPostResult(False, code, None, f"http_{code}")

                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("backend_invalid_json path=%s status=%s", path, code)
                    return BackendPostResult(False, code, None, "invalid_json")

                if not isinstance(data, dict):
                    return BackendPostResult(False, code, None, "non_object_json_response")
                return BackendPostResult(True, code, data, None)
        except httpx.TimeoutException:
            logger.warning("backend_request_timeout path=%s", path)
            return BackendPostResult(False, None, None, "timeout")
        except httpx.RequestError as e:
            logger.warning("backend_request_error path=%s err=%s", path, type(e).__name__)
            return BackendPostResult(False, None, None, "request_error")

    async def post_json(self, path: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Legacy helper for tools that fall back to mocks on any non-success."""
        r = await self.post_json_detailed(path, payload)
        if r.success and r.data is not None:
            return True, r.data, None
        return False, None, r.error_tag
