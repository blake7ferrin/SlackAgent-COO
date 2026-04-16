from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from app.config.settings import Settings
from app.tools.backend_types import BackendPostResult

logger = logging.getLogger(__name__)

# Retryable HTTP status codes (server errors + rate limit)
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class BackendClient:
    """
    HTTP client for the existing backend (source of truth).

    Uses a persistent connection pool and retries transient errors
    with exponential backoff + jitter.
    """

    def __init__(self, settings: Settings) -> None:
        self._base = settings.backend_base_url.rstrip("/")
        t = float(settings.backend_http_timeout_seconds)
        self._timeout = httpx.Timeout(t)
        self._max_retries = settings.backend_max_retries
        self._retry_base = settings.backend_retry_base_delay
        # Persistent connection pool — reused across all requests
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def post_json_detailed(
        self, path: str, payload: dict[str, Any]
    ) -> BackendPostResult:
        """POST JSON with retry on transient failures."""
        url = f"{self._base}{path}"
        last_result: BackendPostResult | None = None

        for attempt in range(1, self._max_retries + 2):  # +2 because range is exclusive and attempt 1 = first try
            try:
                resp = await self._client.post(url, json=payload)
                code = resp.status_code

                if code < 200 or code >= 300:
                    last_result = BackendPostResult(False, code, None, f"http_{code}")
                    if code in _RETRYABLE_STATUS and attempt <= self._max_retries:
                        delay = self._retry_base * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                        logger.warning(
                            "backend_http_retrying path=%s status=%s attempt=%s/%s delay=%.1fs",
                            path, code, attempt, self._max_retries + 1, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.warning("backend_http_error path=%s status=%s", path, code)
                    return last_result

                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("backend_invalid_json path=%s status=%s", path, code)
                    return BackendPostResult(False, code, None, "invalid_json")

                if not isinstance(data, dict):
                    return BackendPostResult(False, code, None, "non_object_json_response")

                if attempt > 1:
                    logger.info("backend_request_recovered path=%s attempt=%s", path, attempt)
                return BackendPostResult(True, code, data, None)

            except httpx.TimeoutException:
                last_result = BackendPostResult(False, None, None, "timeout")
                if attempt <= self._max_retries:
                    delay = self._retry_base * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                    logger.warning(
                        "backend_timeout_retrying path=%s attempt=%s/%s delay=%.1fs",
                        path, attempt, self._max_retries + 1, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning("backend_request_timeout path=%s attempts_exhausted=%s", path, attempt)
                return last_result

            except httpx.RequestError as e:
                last_result = BackendPostResult(False, None, None, "request_error")
                if attempt <= self._max_retries:
                    delay = self._retry_base * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                    logger.warning(
                        "backend_request_error_retrying path=%s err=%s attempt=%s/%s delay=%.1fs",
                        path, type(e).__name__, attempt, self._max_retries + 1, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning("backend_request_error path=%s err=%s attempts_exhausted=%s", path, type(e).__name__, attempt)
                return last_result

        return last_result or BackendPostResult(False, None, None, "max_retries_exhausted")

    async def post_json(self, path: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Legacy helper for tools that fall back to mocks on any non-success."""
        r = await self.post_json_detailed(path, payload)
        if r.success and r.data is not None:
            return True, r.data, None
        return False, None, r.error_tag
