import json

import pytest

from mcdk_mcp_tracy.config import (
    DEFAULT_IP,
    DEFAULT_PORT,
    load_config,
    parse_config,
    resolve_mcdev_path,
)
from mcdk_mcp_tracy.errors import Reason, TracyError


def _write_mcdev(path, **mcp_cfg):
    path.write_text(json.dumps({"mcp_server_config": mcp_cfg}), encoding="utf-8")


def test_localhost_normalized_and_urls(tmp_path):
    f = tmp_path / ".mcdev.json"
    _write_mcdev(f, enabled=True, server_ip="localhost", server_port=19133)
    cfg = parse_config(f)
    assert cfg.ip == DEFAULT_IP
    assert cfg.port == 19133
    assert cfg.base_url == "http://127.0.0.1:19133"
    assert cfg.sse_url == "http://127.0.0.1:19133/sse"


def test_defaults_when_missing_keys(tmp_path):
    f = tmp_path / ".mcdev.json"
    f.write_text("{}", encoding="utf-8")
    cfg = parse_config(f)
    assert cfg.enabled is False
    assert cfg.ip == DEFAULT_IP
    assert cfg.port == DEFAULT_PORT


def test_resolve_walks_up_from_subdir(tmp_path):
    _write_mcdev(tmp_path / ".mcdev.json", enabled=True, server_port=20000)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    found = resolve_mcdev_path(start_dir=deep)
    assert found == tmp_path / ".mcdev.json"


def test_resolve_explicit_and_project_dir(tmp_path):
    f = tmp_path / ".mcdev.json"
    _write_mcdev(f, enabled=True)
    assert resolve_mcdev_path(explicit_path=str(f)) == f
    assert resolve_mcdev_path(project_dir=str(tmp_path)) == f
    assert resolve_mcdev_path(explicit_path=str(tmp_path / "nope.json")) is None


def test_load_config_disabled_raises(tmp_path):
    _write_mcdev(tmp_path / ".mcdev.json", enabled=False)
    with pytest.raises(TracyError) as ei:
        load_config(project_dir=str(tmp_path))
    assert ei.value.reason == Reason.MCP_DISABLED


def test_load_config_not_found_raises(tmp_path):
    with pytest.raises(TracyError) as ei:
        load_config(project_dir=str(tmp_path / "empty"), start_dir=tmp_path / "empty")
    assert ei.value.reason == Reason.CONFIG_NOT_FOUND


def test_override_url_makes_mcdev_optional(tmp_path, monkeypatch):
    monkeypatch.delenv("MCDK_MCDEV_JSON", raising=False)
    cfg = load_config(
        project_dir=str(tmp_path / "missing"),
        override_url="http://127.0.0.1:9999",
    )
    assert cfg.sse_url == "http://127.0.0.1:9999/sse"
    assert cfg.source_path is None


def test_override_url_appends_sse_once():
    from mcdk_mcp_tracy.config import McdkConfig

    cfg = McdkConfig(True, "127.0.0.1", 1, None, override_url="http://h:1/sse")
    assert cfg.sse_url == "http://h:1/sse"
    assert cfg.base_url == "http://h:1"
