"""Typed error reasons surfaced to the agent.

Every tool returns the mcdk-assistant-style envelope
``{"content": [{"type": "text", "text": <json>}], "isError": bool}``.
When ``isError`` is true the JSON payload carries a ``reason`` from
:class:`Reason` so the agent can pinpoint exactly which leg of the chain
(config -> MCDK -> game -> profiler) is broken.
"""

from __future__ import annotations


class Reason:
    """Stable, machine-readable error codes."""

    CONFIG_NOT_FOUND = "config_not_found"        # no .mcdev.json located
    MCP_DISABLED = "mcp_disabled"                # mcp_server_config.enabled == false
    MCDK_UNREACHABLE = "mcdk_unreachable"        # SSE refused / connect timeout
    GAME_NOT_CONNECTED = "game_not_connected"    # MCDK up but game not attached
    EXECUTE_TIMEOUT = "execute_timeout"          # execute_code blocked past deadline
    PROFILER_UNAVAILABLE = "profiler_unavailable"  # native Tracy unreachable / bundled CLIs missing
    PAYLOAD_TOO_LARGE = "payload_too_large"      # reduced payload still > IPC cap
    SNIPPET_ERROR = "snippet_error"              # Py2 snippet raised (returned marker)
    BAD_REQUEST = "bad_request"                  # invalid tool arguments
    UNKNOWN_CAPTURE = "unknown_capture"          # capture_id not in store
    INTERNAL = "internal"                        # unexpected server-side failure


class TracyError(Exception):
    """Raised inside tool handlers; carries a :class:`Reason` and optional detail.

    Tool handlers catch this and convert it into the error envelope; nothing
    else needs to know about the envelope shape.
    """

    def __init__(self, reason: str, message: str, **detail: object) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.detail = detail

    def to_payload(self) -> dict:
        payload: dict = {"ok": False, "reason": self.reason, "error": self.message}
        if self.detail:
            payload.update(self.detail)
        return payload
