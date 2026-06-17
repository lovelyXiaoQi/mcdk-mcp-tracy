"""Diff two captures by function to validate an optimization (before vs after)."""

from __future__ import annotations

from typing import Any

from .store import Capture

_METRIC_KEY = {"self": "self_ms", "total": "total_ms"}


def _index(rows: list[dict], metric_key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        out[r["name"]] = float(r.get(metric_key, 0.0))
    return out


def diff_captures(
    base: Capture, new: Capture, metric: str = "self", top_n: int = 25, round_to: int = 3
) -> dict[str, Any]:
    """Per-function delta ranking + overall movement.

    Negative delta = faster (improved). Lists are capped at ``top_n``.
    """
    metric_key = _METRIC_KEY.get(metric, "self_ms")
    base_idx = _index(base.rows, metric_key)
    new_idx = _index(new.rows, metric_key)

    improved: list[dict] = []
    regressed: list[dict] = []
    for name, base_v in base_idx.items():
        if name in new_idx:
            new_v = new_idx[name]
            delta = new_v - base_v
            entry = {
                "name": name,
                "delta_ms": round(delta, round_to),
                "base_ms": round(base_v, round_to),
                "new_ms": round(new_v, round_to),
            }
            if delta < 0:
                improved.append(entry)
            elif delta > 0:
                regressed.append(entry)

    added = [
        {"name": n, "new_ms": round(v, round_to)}
        for n, v in new_idx.items()
        if n not in base_idx
    ]
    removed = [
        {"name": n, "base_ms": round(v, round_to)}
        for n, v in base_idx.items()
        if n not in new_idx
    ]

    improved.sort(key=lambda e: e["delta_ms"])              # most negative first
    regressed.sort(key=lambda e: e["delta_ms"], reverse=True)  # most positive first
    added.sort(key=lambda e: e["new_ms"], reverse=True)
    removed.sort(key=lambda e: e["base_ms"], reverse=True)

    base_total = base.total_self_ms if metric == "self" else base.total_total_ms
    new_total = new.total_self_ms if metric == "self" else new.total_total_ms
    delta_total = new_total - base_total
    pct = (delta_total / base_total * 100.0) if base_total else None

    return {
        "base_id": base.capture_id,
        "new_id": new.capture_id,
        "metric": metric,
        "base_label": base.label,
        "new_label": new.label,
        "unit_note": (
            "values in ms"
            if base.unit == "ms" and new.unit == "ms"
            else "raw units (unit detection inconclusive); deltas are relative"
        ),
        "summary": {
            "base_total_ms": round(base_total, round_to),
            "new_total_ms": round(new_total, round_to),
            "delta_ms": round(delta_total, round_to),
            "pct": (round(pct, 2) if pct is not None else None),
        },
        "improved": improved[: max(0, top_n)],
        "regressed": regressed[: max(0, top_n)],
        "added": added[: max(0, top_n)],
        "removed": removed[: max(0, top_n)],
    }
