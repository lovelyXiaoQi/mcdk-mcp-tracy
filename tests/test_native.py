"""Pure-reduction tests for the native Tracy path (no live game / no subprocess)."""

from mcdk_mcp_tracy.profiler import native

_HEADER = "name,src_file,src_line,total_ns,total_perc,counts,mean_ns,min_ns,max_ns,std_ns"

# Same two functions in both dumps; self (-e) <= total (plain).
_SELF = "\n".join([
    _HEADER,
    "update,arrisCreateScripts.Content.Server.Systems.BeltInventorySystem,377,2000000,0,4,500000,1,2,3",
    "GetFootPos,mod/client/component/posCompClient.py,43,500000,0,8,62500,1,2,3",
]) + "\n"

_TOTAL = "\n".join([
    _HEADER,
    "update,arrisCreateScripts.Content.Server.Systems.BeltInventorySystem,377,9000000,0,4,2250000,1,2,3",
    "GetFootPos,mod/client/component/posCompClient.py,43,1200000,0,8,150000,1,2,3",
]) + "\n"


def test_reduce_csv_merges_self_and_total_to_ms():
    res = native.reduce_csv(_SELF, _TOTAL, top_n=10)
    assert res["unit"] == "ms"
    assert res["unique_functions"] == 2
    rows = {r["name"]: r for r in res["_all_rows"]}
    upd = rows["update @ arrisCreateScripts.Content.Server.Systems.BeltInventorySystem"]
    assert upd["self_ms"] == 2.0       # 2_000_000 ns / 1e6
    assert upd["total_ms"] == 9.0      # 9_000_000 ns / 1e6
    assert upd["calls"] == 4
    # totals across functions
    assert res["total_self_ms"] == 2.5     # 2.0 + 0.5
    assert res["total_total_ms"] == 10.2   # 9.0 + 1.2


def test_reduce_csv_ranks_by_self_desc():
    res = native.reduce_csv(_SELF, _TOTAL, top_n=10)
    # update (2.0ms self) ranks above GetFootPos (0.5ms self)
    assert res["top"][0]["name"].startswith("update @")
    assert res["top"][1]["name"].startswith("GetFootPos @")


def test_reduce_csv_name_contains_filter():
    res = native.reduce_csv(_SELF, _TOTAL, name_contains="arrisCreate", top_n=10)
    assert res["unique_functions"] == 1
    assert res["_all_rows"][0]["name"].startswith("update @")


def test_reduce_csv_top_n_caps_inline_rows_but_keeps_all():
    res = native.reduce_csv(_SELF, _TOTAL, top_n=1)
    assert len(res["top"]) == 1
    assert len(res["_all_rows"]) == 2


def test_parse_capture_stats_extracts_counts():
    stats = native.parse_capture_stats("Frames: 830\nTime span: 2.17 s\nZones: 180,446\n")
    assert stats["frames"] == 830
    assert stats["zones"] == 180446


def test_parse_capture_stats_missing_is_none():
    stats = native.parse_capture_stats("Connecting to 127.0.0.1:8086...\n")
    assert stats["frames"] is None
    assert stats["zones"] is None
