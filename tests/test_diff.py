from mcdk_mcp_tracy.analysis.diff import diff_captures
from mcdk_mcp_tracy.analysis.store import Capture


def _cap(cid, rows, label="x"):
    total_self = sum(r["self_ms"] for r in rows)
    total_total = sum(r["total_ms"] for r in rows)
    return Capture(
        capture_id=cid,
        label=label,
        side="client",
        unit="ms",
        field_map={},
        polls=1,
        frames=1,
        unique_functions=len(rows),
        total_self_ms=total_self,
        total_total_ms=total_total,
        rows=rows,
    )


def _row(name, self_ms, total_ms=None, calls=1):
    return {"name": name, "self_ms": self_ms, "total_ms": total_ms if total_ms is not None else self_ms, "calls": calls}


def test_diff_improved_regressed_added_removed():
    base = _cap("cap-1", [_row("hot", 10.0), _row("warm", 5.0), _row("gone", 3.0)], "before")
    new = _cap("cap-2", [_row("hot", 4.0), _row("warm", 7.0), _row("fresh", 2.0)], "after")
    d = diff_captures(base, new, metric="self", top_n=10)

    assert d["base_id"] == "cap-1" and d["new_id"] == "cap-2"
    improved = {e["name"]: e for e in d["improved"]}
    regressed = {e["name"]: e for e in d["regressed"]}
    assert improved["hot"]["delta_ms"] == -6.0
    assert regressed["warm"]["delta_ms"] == 2.0
    assert [e["name"] for e in d["added"]] == ["fresh"]
    assert [e["name"] for e in d["removed"]] == ["gone"]


def test_diff_summary_pct():
    base = _cap("cap-1", [_row("a", 100.0)])
    new = _cap("cap-2", [_row("a", 75.0)])
    d = diff_captures(base, new, metric="self")
    assert d["summary"]["base_total_ms"] == 100.0
    assert d["summary"]["new_total_ms"] == 75.0
    assert d["summary"]["delta_ms"] == -25.0
    assert d["summary"]["pct"] == -25.0


def test_diff_improved_sorted_by_biggest_win():
    base = _cap("cap-1", [_row("a", 10.0), _row("b", 20.0)])
    new = _cap("cap-2", [_row("a", 9.0), _row("b", 5.0)])
    d = diff_captures(base, new, metric="self")
    assert [e["name"] for e in d["improved"]] == ["b", "a"]  # -15 before -1
