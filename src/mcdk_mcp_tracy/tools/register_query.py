"""Query tools over stored captures: get_function_costs, diff_captures."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..analysis.diff import diff_captures as _diff
from ..errors import Reason, TracyError
from ..state import ServerState
from ._common import anno, err_payload


def register(mcp: FastMCP, state: ServerState) -> None:
    @mcp.tool(annotations=anno(read_only=True, idempotent=True, title="Get function costs"))
    async def tracy_get_function_costs(
        capture_id: str,
        names: list[str] | None = None,
        name_contains: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Query per-function self/total/calls from a stored capture.

        Pure server-side slice (no game call). Filter by exact names and/or a
        substring; without a filter, returns the top `limit` by self-time.

        Args:
            capture_id: id from tracy_capture_and_rank (required).
            names: exact function names to include.
            name_contains: case-insensitive substring filter (e.g. your mod prefix).
            limit: max rows to return (default 50).
        """
        try:
            cap = state.store.get(capture_id)
            if cap is None:
                raise TracyError(
                    Reason.UNKNOWN_CAPTURE, f"no capture '{capture_id}' (it may have been evicted)"
                )
            rows = cap.rows
            if names:
                wanted = set(names)
                rows = [r for r in rows if r["name"] in wanted]
            if name_contains:
                needle = name_contains.lower()
                rows = [r for r in rows if needle in r["name"].lower()]
            limit = max(1, min(500, int(limit)))
            matched = rows[:limit]
            return {
                "ok": True,
                "capture_id": capture_id,
                "label": cap.label,
                "unit": cap.unit,
                "matched_count": len(matched),
                "matched": matched,
                "matched_self_ms": round(sum(r["self_ms"] for r in matched), 3),
            }
        except Exception as e:  # noqa: BLE001
            return err_payload(e)

    @mcp.tool(annotations=anno(read_only=True, idempotent=True, title="Diff captures"))
    async def tracy_diff_captures(
        base_id: str,
        new_id: str,
        metric: str = "self",
        top_n: int = 25,
    ) -> dict[str, Any]:
        """Diff two captures by function to validate an optimization.

        Negative delta = faster. Returns improved / regressed / added / removed
        plus overall movement (base vs new total, delta, pct).

        Args:
            base_id: the "before" capture id (required).
            new_id: the "after" capture id (required).
            metric: 'self' (default) or 'total'.
            top_n: max rows per list (default 25).
        """
        try:
            if metric not in ("self", "total"):
                raise TracyError(Reason.BAD_REQUEST, "metric must be 'self' or 'total'")
            base = state.store.get(base_id)
            new = state.store.get(new_id)
            missing = [i for i, c in ((base_id, base), (new_id, new)) if c is None]
            if missing:
                raise TracyError(
                    Reason.UNKNOWN_CAPTURE, f"unknown capture id(s): {missing}"
                )
            result = _diff(base, new, metric=metric, top_n=top_n)
            result["ok"] = True
            return result
        except Exception as e:  # noqa: BLE001
            return err_payload(e)
