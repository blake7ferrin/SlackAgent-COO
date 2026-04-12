from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GrokRunTrace:
    """Observability + Slack reply classification (single turn)."""

    tools_called: list[str] = field(default_factory=list)
    generate_report_result: dict[str, Any] | None = None
    last_tool_name: str | None = None
    last_tool_ok: bool | None = None

    def record_tool(self, name: str, result: dict[str, Any]) -> None:
        self.tools_called.append(name)
        self.last_tool_name = name
        ok = result.get("ok")
        self.last_tool_ok = bool(ok) if isinstance(ok, bool) else None
        if name == "generate_report":
            self.generate_report_result = result
