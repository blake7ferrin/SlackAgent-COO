from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import Settings

logger = logging.getLogger(__name__)


class BackendClient:
    """
    HTTP client for the existing backend (source of truth).
    If requests fail or URL is unreachable, callers should degrade gracefully.
    """

    def __init__(self, settings: Settings) -> None:
        self._base = settings.backend_base_url.rstrip("/")
        self._timeout = httpx.Timeout(30.0)

    async def post_json(self, path: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    return False, None, "non_object_json_response"
                return True, data, None
        except httpx.HTTPStatusError as e:
            logger.warning(
                "backend_http_error path=%s status=%s",
                path,
                e.response.status_code,
            )
            return False, None, f"http_{e.response.status_code}"
        except httpx.RequestError as e:
            logger.warning("backend_request_error path=%s err=%s", path, type(e).__name__)
            return False, None, "request_error"
