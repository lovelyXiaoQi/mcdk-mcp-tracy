"""Orchestration tests with a fake MCDK client (no live game).

Covers the MCDK-driven helpers that remain after the in-game getCpuFrameData
path was removed: FPS sampling and jank-log scraping. Per-function capture is
now the native-Tracy path (see test_native.py).
"""

import asyncio
from contextlib import asynccontextmanager

from mcdk_mcp_tracy.profiler import operations
from mcdk_mcp_tracy.state import ServerState


class FakeClient:
    """Stands in for McdkClient: serves the FPS snippet and get_latest_logs."""

    def __init__(self, fps_seq=None, logs=None):
        # fps_seq: list of (fps, frame_time) per poll; cycles if shorter.
        self.fps_seq = fps_seq if fps_seq is not None else [(60.0, 16.6)]
        self.logs = logs if logs is not None else []
        self._i = 0
        self.codes: list[str] = []
        self.tool_calls: list[tuple] = []

    async def execute_code(self, code, is_client=True, direct_return=True, timeout_s=20.0):
        self.codes.append(code)
        if "__tracy_fps" in code:
            fps, ft = self.fps_seq[self._i % len(self.fps_seq)]
            self._i += 1
            return {"ok": True, "fps": fps, "frame_time": ft}
        return {"ok": True}

    async def call_tool(self, name, args, timeout_s=20.0):
        self.tool_calls.append((name, args))
        return {"content": [{"type": "text", "text": "\n".join(self.logs)}]}

    @asynccontextmanager
    async def session_scope(self):
        """No real connection in tests; sample loops wrap themselves in this."""
        yield


def test_plan_polls_caps_at_max():
    # 100s @ 1ms would be 100k polls; must clamp to MAX_POLLS and widen interval.
    polls, interval = operations._plan_polls(100.0, 1.0)
    assert polls == operations.MAX_POLLS
    assert interval >= operations.MIN_INTERVAL_S


def test_plan_polls_normal():
    polls, interval = operations._plan_polls(1.0, 250.0)
    assert polls == 4
    assert abs(interval - 0.25) < 1e-9


def test_sample_fps_aggregates_percentiles():
    seq = [(float(x), 1000.0 / x) for x in (30, 60, 120, 90)]
    state = ServerState(client=FakeClient(fps_seq=seq))
    res = asyncio.run(operations.sample_fps(state, duration_seconds=1.0))
    assert res["ok"] is True
    assert res["samples"] >= 1
    assert res["min_fps"] <= res["avg_fps"] <= res["max_fps"]
    assert "p50_fps" in res and "p1_fps" in res and "p5_fps" in res


def test_sample_fps_warns_when_no_samples():
    class Empty(FakeClient):
        async def execute_code(self, code, is_client=True, direct_return=True, timeout_s=20.0):
            return {"ok": False}

    state = ServerState(client=Empty())
    res = asyncio.run(operations.sample_fps(state, duration_seconds=0.5))
    assert res["ok"] is True
    assert res["samples"] == 0
    assert "warning" in res


def test_read_jank_logs_filters_relevant_lines():
    logs = ["hello world", "FPS drop detected", "SimpleProfiler report", "unrelated noise"]
    client = FakeClient(logs=logs)
    state = ServerState(client=client)
    res = asyncio.run(operations.read_jank_logs(state, log_lines=50))
    assert res["ok"] is True
    assert res["matched_count"] == 2  # "FPS..." + "SimpleProfiler..."
    assert client.tool_calls and client.tool_calls[0][0] == "get_latest_logs"
