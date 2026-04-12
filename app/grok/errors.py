"""Grok client errors surfaced to the orchestrator."""


class GrokTimeoutError(Exception):
    """Raised when a Grok API call exceeds the configured timeout."""
