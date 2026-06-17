"""Server-side orchestration of the MCDK-driven helpers (FPS + jank logs).

Tool handlers stay thin; the windowed FPS sampling lives here. The sample loop
spaces fast polls with ``asyncio.sleep`` on the *server* so the game keeps
ticking (we never sleep on the game thread).

Per-function CPU profiling no longer lives here: the in-game ``getCpuFrameData``
path was removed (binding absent on release builds). Use ``profiler.native``
(native Tracy on TCP 8086) via ``tracy_native_capture`` for per-function timing.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..errors import Reason, TracyError
from ..state import ServerState
from . import snippets
from .execinject import run_snippet

MAX_SAMPLE_SECONDS = 60.0
MAX_POLLS = 200
MIN_INTERVAL_S = 0.02
GRAB_TIMEOUT_S = 15.0


def _is_client(side: str) -> bool:
    if side not in ("client", "server"):
        raise TracyError(Reason.BAD_REQUEST, "side must be 'client' or 'server'", side=side)
    return side == "client"


def _plan_polls(sample_seconds: float, poll_interval_ms: float) -> tuple[int, float]:
    """Compute (poll_count, interval_s), widening interval if capped by MAX_POLLS."""
    sample_seconds = max(0.1, min(MAX_SAMPLE_SECONDS, float(sample_seconds)))
    interval = max(MIN_INTERVAL_S, float(poll_interval_ms) / 1000.0)
    polls = int(max(1, round(sample_seconds / interval)))
    if polls > MAX_POLLS:
        polls = MAX_POLLS
        interval = sample_seconds / polls
    return polls, interval


async def sample_fps(state: ServerState, duration_seconds: float = 5.0, side: str = "client") -> dict:
    """Poll get_Fps()/get_frame_time() across the window; return percentiles."""
    is_client = _is_client(side)
    duration_seconds = max(0.5, min(MAX_SAMPLE_SECONDS, float(duration_seconds)))
    polls, interval = _plan_polls(duration_seconds, 250.0)
    fps_code = snippets.build_fps_sample()
    samples: list[float] = []
    frame_times: list[float] = []
    async with state.client.session_scope():
        for _ in range(polls):
            await asyncio.sleep(interval)
            part = await run_snippet(state.client, fps_code, is_client=is_client, timeout_s=GRAB_TIMEOUT_S)
            if not isinstance(part, dict) or not part.get("ok"):
                continue
            fps = part.get("fps")
            ft = part.get("frame_time")
            if isinstance(fps, (int, float)):
                samples.append(float(fps))
            if isinstance(ft, (int, float)):
                frame_times.append(float(ft))
    if not samples:
        return {
            "ok": True,
            "samples": 0,
            "warning": "no FPS samples; get_Fps may be unavailable on this build/side",
        }
    ordered = sorted(samples)

    def pct(p: float) -> float:
        idx = min(len(ordered) - 1, max(0, int(len(ordered) * p)))
        return round(ordered[idx], 2)

    return {
        "ok": True,
        "samples": len(samples),
        "avg_fps": round(sum(samples) / len(samples), 2),
        "min_fps": round(ordered[0], 2),
        "p1_fps": pct(0.01),
        "p5_fps": pct(0.05),
        "p50_fps": pct(0.50),
        "max_fps": round(ordered[-1], 2),
        "avg_frame_time_ms": (round(sum(frame_times) / len(frame_times), 3) if frame_times else None),
    }


async def read_jank_logs(state: ServerState, log_lines: int = 200) -> dict:
    """Scrape recent jank/profile log lines via MCDK's get_latest_logs."""
    log_lines = max(1, min(2000, int(log_lines)))
    text = await state.client.call_tool(
        "get_latest_logs", {"max_count": log_lines, "order": "desc"}, timeout_s=20.0
    )
    lines = _lines_from_logs(text)
    needles = ("jank", "Jank", "profile", "Profiler", "frameTime", "FPS", "SimpleProfiler")
    matched = [ln for ln in lines if any(n in ln for n in needles)]
    return {
        "ok": True,
        "scanned": len(lines),
        "jank_events": matched[:100],
        "matched_count": len(matched),
    }


def _lines_from_logs(text: Any) -> list[str]:
    """MCDK get_latest_logs returns JSON content; coerce to a list of lines."""
    import json

    if text is None:
        return []
    if isinstance(text, list):
        return [str(x) for x in text]
    if isinstance(text, str):
        stripped = text.strip()
        try:
            data = json.loads(stripped)
        except ValueError:
            return stripped.splitlines()
        return _lines_from_json(data)
    return _lines_from_json(text)


def _lines_from_json(data: Any) -> list[str]:
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, list):
            out: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    out.extend(str(block["text"]).splitlines())
            if out:
                return out
        for key in ("logs", "lines", "entries"):
            if isinstance(data.get(key), list):
                return [str(x) for x in data[key]]
    return [str(data)]
