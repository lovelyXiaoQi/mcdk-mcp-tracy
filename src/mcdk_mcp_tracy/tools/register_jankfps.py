"""Frame-level health tool: tracy_jank_fps."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..errors import Reason, TracyError
from ..profiler import operations
from ..state import ServerState
from ._common import anno, err_payload

_ACTIONS = ("sample_fps", "read_jank_logs")


def register(mcp: FastMCP, state: ServerState) -> None:
    @mcp.tool(annotations=anno(idempotent=True, title="Jank / FPS"))
    async def tracy_jank_fps(
        action: str,
        side: str = "client",
        duration_seconds: float = 5.0,
        log_lines: int = 200,
    ) -> dict[str, Any]:
        """Frame-level health, complementing the per-function view.

        Actions:
        - sample_fps: poll get_Fps()/get_frame_time() over the window; returns
          avg/min/max and p1/p5/p50 percentiles.
        - read_jank_logs: scrape recent jank/profile lines from MCDK logs.

        Args:
            action: one of sample_fps | read_jank_logs (required).
            side: 'client' or 'server'.
            duration_seconds: window for sample_fps (default 5).
            log_lines: lines to scan for read_jank_logs (default 200).
        """
        try:
            if action not in _ACTIONS:
                raise TracyError(
                    Reason.BAD_REQUEST, f"action must be one of {_ACTIONS}", action=action
                )
            if action == "sample_fps":
                return await operations.sample_fps(
                    state, duration_seconds=duration_seconds, side=side
                )
            return await operations.read_jank_logs(state, log_lines=log_lines)
        except Exception as e:  # noqa: BLE001
            return err_payload(e)
