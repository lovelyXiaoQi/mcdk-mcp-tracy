"""Shared helpers for tool handlers: error payloads and annotation hints."""

from __future__ import annotations

from typing import Any

from ..errors import Reason, TracyError

try:  # annotations are optional hints; tolerate older SDKs
    from mcp.types import ToolAnnotations
except Exception:  # pragma: no cover
    ToolAnnotations = None  # type: ignore[assignment]


def err_payload(exc: Exception) -> dict[str, Any]:
    """Convert any exception into the uniform ``ok:false`` structured payload."""
    if isinstance(exc, TracyError):
        return exc.to_payload()
    return {"ok": False, "reason": Reason.INTERNAL, "error": repr(exc)}


def anno(
    *,
    read_only: bool = False,
    idempotent: bool = False,
    destructive: bool = False,
    title: str | None = None,
) -> Any:
    """Build a ToolAnnotations object, or None when unsupported by the SDK."""
    if ToolAnnotations is None:
        return None
    return ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        idempotentHint=idempotent,
        destructiveHint=destructive,
    )
