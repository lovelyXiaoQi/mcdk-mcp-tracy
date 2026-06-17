"""Native Tracy path: drive the bundled tracy-capture / tracy-csvexport CLIs.

Some NetEase client builds lack the Python ``_utility.getCpuFrameData`` binding
but still embed a *native* Tracy server listening on TCP 8086 (the one the
tracy-profiler GUI connects to). This module captures a short trace with
``tracy-capture.exe`` and reduces it with ``tracy-csvexport.exe`` into the same
compact per-function rows as the in-game path, so the existing store / diff /
get_function_costs tools work unchanged.

No module whitelist is needed — native Tracy traces every instrumented zone
(across the client's MAIN_THREAD and MC_SERVER threads).

The pure reduction (:func:`reduce_csv`, :func:`parse_capture_stats`) is split
from the subprocess orchestration so it can be unit-tested without a live game.
"""

from __future__ import annotations

import asyncio
import csv as _csv
import io
import os
import re
import subprocess
import sys
import tempfile
from typing import Any

from ..errors import Reason, TracyError

# bin/ sits at the repo root, next to src/. __file__ is .../src/mcdk_mcp_tracy/profiler/native.py
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../src/mcdk_mcp_tracy
_REPO_DIR = os.path.dirname(os.path.dirname(_PKG_DIR))                  # .../mcdk-mcp-tracy
_BIN_DIR = os.environ.get("TRACY_BIN_DIR") or os.path.join(_REPO_DIR, "bin")

MAX_SAMPLE_SECONDS = 60.0
_NS_PER_MS = 1.0e6


def _exe(name: str) -> str:
    path = os.path.join(_BIN_DIR, name)
    if not os.path.isfile(path):
        raise TracyError(
            Reason.PROFILER_UNAVAILABLE,
            "bundled Tracy tool not found: %s (looked in %s). Reinstall the tracy "
            "CLI tools or set the TRACY_BIN_DIR env var." % (name, _BIN_DIR),
        )
    return path


def bin_available() -> bool:
    """Whether the bundled tracy-capture / tracy-csvexport CLIs are present."""
    return all(
        os.path.isfile(os.path.join(_BIN_DIR, n))
        for n in ("tracy-capture.exe", "tracy-csvexport.exe")
    )


async def probe_native(
    address: str = "127.0.0.1", port: int = 8086, timeout: float = 2.0
) -> dict[str, Any]:
    """Reachability check for the game's native Tracy server (no capture).

    The native path is usable when this returns ``reachable=True`` and
    :func:`bin_available` is True. Used by ``tracy_status``.
    """
    loop = asyncio.get_running_loop()

    def _check() -> bool:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((address, int(port)))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    reachable = await loop.run_in_executor(None, _check)
    return {"reachable": reachable, "address": address, "port": int(port)}


def _popen_kwargs() -> dict:
    kw: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW — no console flash
    return kw


def _run_sync(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, timeout=timeout, **_popen_kwargs())


async def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    """Run a CLI in a worker thread (avoids Windows asyncio-subprocess quirks)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _run_sync(cmd, timeout))


def _parse_csv(text: str) -> dict:
    """Reduce one csvexport dump to ``(name, src_file) -> {ns, calls, src_line}``."""
    out: dict = {}
    reader = _csv.DictReader(io.StringIO(text))
    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        src = (row.get("src_file") or "").strip()
        key = (name, src)
        try:
            ns = float(row.get("total_ns") or 0.0)
        except ValueError:
            ns = 0.0
        try:
            calls = int(float(row.get("counts") or 0))
        except ValueError:
            calls = 0
        cur = out.get(key)
        if cur is None:
            out[key] = {"ns": ns, "calls": calls, "src_line": (row.get("src_line") or "").strip()}
        else:  # same name+file at multiple lines: fold together
            cur["ns"] += ns
            cur["calls"] = max(cur["calls"], calls)
    return out


def reduce_csv(
    self_text: str,
    total_text: str,
    name_contains: str | None = None,
    top_n: int = 25,
    round_to: int = 3,
) -> dict[str, Any]:
    """Merge self-time and total-time csvexport dumps into ranked per-function rows.

    ``self_text`` is the ``-e`` (self/exclusive) export, ``total_text`` the plain
    (inclusive) export. Output shape matches the stored capture rows so the
    result stores and queries exactly like any other capture.
    """
    self_map = _parse_csv(self_text)
    total_map = _parse_csv(total_text)
    needle = name_contains.lower() if name_contains else None

    rows: list[dict] = []
    total_self = 0.0
    total_total = 0.0
    for key in set(self_map) | set(total_map):
        name, src = key
        s = self_map.get(key)
        t = total_map.get(key)
        disp = ("%s @ %s" % (name, src)) if src else name
        if needle and needle not in disp.lower():
            continue
        self_ms = (s["ns"] if s else 0.0) / _NS_PER_MS
        total_ms = (t["ns"] if t else 0.0) / _NS_PER_MS
        calls = (t["calls"] if t else 0) or (s["calls"] if s else 0)
        total_self += self_ms
        total_total += total_ms
        rows.append(
            {
                "name": disp,
                "self_ms": round(self_ms, round_to),
                "total_ms": round(total_ms, round_to),
                "calls": calls,
                "src_file": src,
                "src_line": (t or s or {}).get("src_line", ""),
            }
        )
    rows.sort(key=lambda r: (r["self_ms"], r["total_ms"], r["calls"]), reverse=True)
    return {
        "unit": "ms",
        "unique_functions": len(rows),
        "total_self_ms": round(total_self, round_to),
        "total_total_ms": round(total_total, round_to),
        "top": rows[: max(0, int(top_n))],
        "_all_rows": rows,
    }


def parse_capture_stats(text: str) -> dict:
    """Pull Frames / Zones counts out of tracy-capture's console output."""

    def grab(label: str) -> int | None:
        m = re.search(label + r"\s*:?\s*([\d,]+)", text)
        if not m:
            return None
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None

    return {"frames": grab("Frames"), "zones": grab("Zones")}


async def native_capture(
    seconds: float = 5.0,
    address: str = "127.0.0.1",
    port: int = 8086,
    name_contains: str | None = None,
    top_n: int = 25,
) -> dict[str, Any]:
    """Capture from the native Tracy server and reduce to ranked rows + totals."""
    if seconds <= 0 or seconds > MAX_SAMPLE_SECONDS:
        raise TracyError(Reason.BAD_REQUEST, "seconds must be in (0, %g]" % MAX_SAMPLE_SECONDS)
    capture_exe = _exe("tracy-capture.exe")
    csv_exe = _exe("tracy-csvexport.exe")

    fd, trace_path = tempfile.mkstemp(suffix=".tracy")
    os.close(fd)
    try:
        cap = await _run(
            [capture_exe, "-o", trace_path, "-a", address, "-p", str(int(port)),
             "-s", str(seconds), "-f"],
            timeout=seconds + 25.0,
        )
        cap_text = (
            (cap.stdout or b"").decode("utf-8", "replace")
            + "\n"
            + (cap.stderr or b"").decode("utf-8", "replace")
        )
        if cap.returncode != 0:
            raise TracyError(
                Reason.MCDK_UNREACHABLE,
                "tracy-capture failed (rc=%s); is the game's native Tracy server "
                "listening on %s:%s? %s" % (cap.returncode, address, port, cap_text.strip()[-300:]),
            )
        if not os.path.getsize(trace_path):
            raise TracyError(
                Reason.MCDK_UNREACHABLE,
                "tracy-capture produced an empty trace; no data on %s:%s" % (address, port),
            )

        self_csv = await _run([csv_exe, "-e", trace_path], timeout=60.0)
        total_csv = await _run([csv_exe, trace_path], timeout=60.0)
        if self_csv.returncode != 0 or total_csv.returncode != 0:
            raise TracyError(
                Reason.SNIPPET_ERROR,
                "tracy-csvexport failed (rc=%s/%s)" % (self_csv.returncode, total_csv.returncode),
            )
        reduced = reduce_csv(
            self_csv.stdout.decode("utf-8", "replace"),
            total_csv.stdout.decode("utf-8", "replace"),
            name_contains=name_contains,
            top_n=top_n,
        )
    finally:
        try:
            os.remove(trace_path)
        except OSError:
            pass

    stats = parse_capture_stats(cap_text)
    reduced["frames"] = stats.get("frames")
    reduced["zones"] = stats.get("zones")
    return reduced
