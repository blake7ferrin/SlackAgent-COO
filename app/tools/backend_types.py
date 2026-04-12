from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BackendPostResult:
    """Result of a backend HTTP POST (never includes secrets)."""

    success: bool
    status_code: int | None
    data: dict[str, Any] | None
    error_tag: str | None
