"""Bounded in-memory store of reduced captures, keyed by ``capture_id``.

Large raw frame data is reduced in-game and server-side; only the compact
per-function rows live here. ``get_function_costs`` / ``diff_captures`` query
this store so big data never round-trips through the agent again.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Capture:
    capture_id: str
    label: str
    side: str
    unit: str
    field_map: dict[str, str | None]
    polls: int
    frames: int
    unique_functions: int
    total_self_ms: float
    total_total_ms: float
    rows: list[dict] = field(default_factory=list)  # full ranked rows
    created_at: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "label": self.label,
            "side": self.side,
            "unit": self.unit,
            "field_map": self.field_map,
            "polls": self.polls,
            "frames": self.frames,
            "unique_functions": self.unique_functions,
            "total_self_ms": self.total_self_ms,
            "total_total_ms": self.total_total_ms,
            "created_at": self.created_at,
        }


class CaptureStore:
    """Thread-safe, size-bounded capture store (evicts oldest)."""

    def __init__(self, max_captures: int = 20) -> None:
        self._max = max_captures
        self._lock = threading.Lock()
        self._captures: dict[str, Capture] = {}
        self._counter = 0

    def new_id(self) -> str:
        with self._lock:
            self._counter += 1
            return "cap-%d" % self._counter

    def put(self, capture: Capture) -> None:
        with self._lock:
            self._captures[capture.capture_id] = capture
            while len(self._captures) > self._max:
                oldest = min(self._captures.values(), key=lambda c: c.created_at)
                self._captures.pop(oldest.capture_id, None)

    def get(self, capture_id: str) -> Capture | None:
        with self._lock:
            return self._captures.get(capture_id)

    def list(self) -> list[dict]:
        with self._lock:
            caps = sorted(self._captures.values(), key=lambda c: c.created_at, reverse=True)
        return [c.summary() for c in caps]
