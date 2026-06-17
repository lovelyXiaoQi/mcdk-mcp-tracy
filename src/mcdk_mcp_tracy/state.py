"""Shared server state passed to tool handlers."""

from __future__ import annotations

from dataclasses import dataclass, field

from .analysis.store import CaptureStore
from .mcdk_client import McdkClient


@dataclass
class ServerState:
    client: McdkClient
    store: CaptureStore = field(default_factory=CaptureStore)
    # Cached frame-record schema sample from the last successful probe; used to
    # pick field-name candidates and the time unit for captures.
    schema_sample: dict | None = None
