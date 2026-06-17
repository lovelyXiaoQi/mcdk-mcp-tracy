from mcdk_mcp_tracy.analysis.store import Capture, CaptureStore


def _cap(cid, created_at):
    return Capture(
        capture_id=cid,
        label=cid,
        side="client",
        unit="ms",
        field_map={},
        polls=1,
        frames=1,
        unique_functions=0,
        total_self_ms=0.0,
        total_total_ms=0.0,
        rows=[],
        created_at=created_at,
    )


def test_new_id_increments():
    s = CaptureStore()
    assert s.new_id() == "cap-1"
    assert s.new_id() == "cap-2"


def test_put_get_list():
    s = CaptureStore()
    s.put(_cap("cap-1", 100.0))
    s.put(_cap("cap-2", 200.0))
    assert s.get("cap-1").capture_id == "cap-1"
    assert s.get("missing") is None
    listed = s.list()
    assert [c["capture_id"] for c in listed] == ["cap-2", "cap-1"]  # newest first


def test_eviction_drops_oldest():
    s = CaptureStore(max_captures=2)
    s.put(_cap("cap-1", 100.0))
    s.put(_cap("cap-2", 200.0))
    s.put(_cap("cap-3", 300.0))
    assert s.get("cap-1") is None  # oldest evicted
    assert s.get("cap-2") is not None
    assert s.get("cap-3") is not None
