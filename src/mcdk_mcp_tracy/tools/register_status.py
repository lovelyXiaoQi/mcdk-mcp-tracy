"""Status / introspection tools: tracy_status, tracy_list_captures."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..errors import Reason, TracyError
from ..profiler import native
from ..state import ServerState
from ._common import anno, err_payload


def register(mcp: FastMCP, state: ServerState) -> None:
    @mcp.tool(
        annotations=anno(read_only=True, idempotent=True, title="Tracy status / probe"),
    )
    async def tracy_status(
        address: str = "127.0.0.1", port: int = 8086, project_dir: str | None = None
    ) -> dict[str, Any]:
        """Probe whether native-Tracy profiling is usable on the running game.

        RUN THIS FIRST. The capture path used by this server is the game's
        embedded **native Tracy server** (TCP 8086), driven by the bundled
        tracy-capture / tracy-csvexport CLIs. It does NOT use the Python
        ``_utility.getCpuFrameData`` binding (absent on most release builds) and
        does NOT go through MCDK. Reports:

        * ``native_tracy.reachable`` — can we open a TCP connection to 8086? (the
          tracy-profiler GUI connects to the same port)
        * ``bin_present`` — are the bundled Tracy CLIs available?
        * ``mcdk`` — MCDK MCP endpoint, informational only (just tracy_jank_fps
          needs it; native capture is independent). Best-effort.

        ``ok`` is true when the native path is ready (reachable + bin present);
        otherwise ``reason``/``hint`` pinpoint the broken leg.

        Args:
            address/port: native Tracy endpoint (default 127.0.0.1:8086).
            project_dir: optional path whose .mcdev.json gives MCDK's MCP port.
        """
        out: dict[str, Any] = {"ok": False}

        # MCDK endpoint is informational here (only tracy_jank_fps needs it).
        try:
            if project_dir:
                await state.client.reconfigure(project_dir=project_dir)
            cfg = state.client.resolve_config(require_enabled=True)
            out["mcdk"] = {
                "url": cfg.sse_url,
                "mcdev_json": str(cfg.source_path) if cfg.source_path else None,
                "note": "MCDK is only needed for tracy_jank_fps; native capture is independent",
            }
        except TracyError as e:
            out["mcdk"] = {"error": e.message, "reason": e.reason}

        probe = await native.probe_native(address=address, port=int(port))
        out["native_tracy"] = probe
        out["bin_present"] = native.bin_available()

        out["ok"] = bool(probe.get("reachable") and out["bin_present"])
        if not out["ok"]:
            out["reason"] = Reason.PROFILER_UNAVAILABLE
            if not probe.get("reachable"):
                out["error"] = "no native Tracy server reachable on %s:%s" % (address, port)
                out["hint"] = (
                    "launch the game (the client embeds Tracy on 8086); confirm it "
                    "with the tracy-profiler GUI, or check the address/port"
                )
            else:
                out["error"] = "bundled Tracy CLIs not found"
                out["hint"] = (
                    "ensure bin/tracy-capture.exe and bin/tracy-csvexport.exe exist, "
                    "or set the TRACY_BIN_DIR env var"
                )
        return out

    @mcp.tool(annotations=anno(read_only=True, idempotent=True, title="List captures"))
    async def tracy_list_captures() -> dict[str, Any]:
        """List stored captures (id, label, side, totals, timestamp) for diffing."""
        try:
            return {"ok": True, "captures": state.store.list()}
        except Exception as e:  # noqa: BLE001
            return err_payload(e)
