from __future__ import annotations

import logging
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)


class RecentDedup:
    """Tiny TTL deduper for Slack retries / duplicate deliveries (in-memory, single process)."""

    def __init__(self, *, ttl_seconds: float = 600.0, max_keys: int = 5000) -> None:
        self._ttl = ttl_seconds
        self._max = max_keys
        self._seen: OrderedDict[str, float] = OrderedDict()

    def is_duplicate(self, key: str) -> bool:
        now = time.monotonic()
        self._prune(now)
        if key in self._seen:
            logger.info("dedup_hit key=%s", key)
            return True
        self._seen[key] = now
        self._seen.move_to_end(key)
        while len(self._seen) > self._max:
            self._seen.popitem(last=False)
        return False

    def _prune(self, now: float) -> None:
        cutoff = now - self._ttl
        # iterate from oldest
        keys_to_drop: list[str] = []
        for k, ts in self._seen.items():
            if ts < cutoff:
                keys_to_drop.append(k)
            else:
                break
        for k in keys_to_drop:
            self._seen.pop(k, None)
