"""Native Tracy capture tool: tracy_native_capture (TCP 8086 via bundled CLIs)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..analysis.store import Capture
from ..errors import TracyError
from ..profiler import native
from ..state import ServerState
from ._common import anno, err_payload


def register(mcp: FastMCP, state: ServerState) -> None:
    @mcp.tool(annotations=anno(title="Tracy native capture (8086)"))
    async def tracy_native_capture(
        seconds: float = 5.0,
        name_contains: str | None = None,
        top_n: int = 25,
        address: str = "127.0.0.1",
        port: int = 8086,
        label: str | None = None,
    ) -> dict[str, Any]:
        """Capture function timings from the game's NATIVE Tracy server (TCP 8086).

        Use this when ``tracy_status`` reports ``getCpuFrameData=false`` but the
        tracy-profiler GUI can still connect to the game — that means the client
        embeds a native Tracy server even though the Python profiler binding is
        missing. This drives the bundled tracy-capture / tracy-csvexport CLIs; no
        module whitelist is needed (native Tracy traces every zone, across the
        client's MAIN_THREAD and MC_SERVER threads).

        Drive the gameplay you want to measure DURING the window. The returned
        ``capture_id`` plugs into tracy_get_function_costs / tracy_diff_captures
        exactly like an in-game capture.

        Args:
            seconds: capture window, 0 < s <= 60 (default 5).
            name_contains: case-insensitive filter, e.g. 'arrisCreate' to keep
                only your mod's functions (matched against "name @ src_file").
            top_n: rows returned inline (default 25; the full set is stored for
                later get_function_costs / diff queries).
            address/port: native Tracy endpoint (default 127.0.0.1:8086).
            label: tag for diffing, e.g. 'before' / 'after'.
        """
        try:
            res = await native.native_capture(
                seconds=seconds,
                address=address,
                port=int(port),
                name_contains=name_contains,
                top_n=top_n,
            )
        except TracyError as e:
            return err_payload(e)
        except Exception as e:  # noqa: BLE001
            return err_payload(e)

        cap_id = state.store.new_id()
        capture = Capture(
            capture_id=cap_id,
            label=label or cap_id,
            side="native",
            unit="ms",
            field_map={"source": "native_tracy", "self": "self_ns", "total": "total_ns"},
            polls=1,
            frames=res.get("frames") or 0,
            unique_functions=res["unique_functions"],
            total_self_ms=res["total_self_ms"],
            total_total_ms=res["total_total_ms"],
            rows=res["_all_rows"],
        )
        state.store.put(capture)

        out: dict[str, Any] = {
            "ok": True,
            "capture_id": cap_id,
            "label": capture.label,
            "source": "native_tracy",
            "seconds": seconds,
            "frames": res.get("frames"),
            "zones": res.get("zones"),
            "unique_functions": res["unique_functions"],
            "unit": "ms",
            "total_self_ms": res["total_self_ms"],
            "total_total_ms": res["total_total_ms"],
            "top": res["top"],
        }
        if name_contains:
            out["filter"] = name_contains
        if not res["_all_rows"]:
            out["warning"] = (
                "no zones captured — drive real gameplay during the window, and "
                "confirm the native Tracy server is reachable on %s:%s" % (address, port)
            )
        return out
