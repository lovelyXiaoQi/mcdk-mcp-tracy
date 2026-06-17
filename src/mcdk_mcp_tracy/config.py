"""Locate the active mod project's ``.mcdev.json`` and extract MCDK's MCP endpoint.

MCDK (mcdk.exe) embeds an MCP server (HTTP + SSE) whose ip/port live in
``.mcdev.json -> mcp_server_config``. We connect *out* to that SSE endpoint to
reach the game via ``execute_code``. See
``demo/mcdk-mcp-game-testing/.mcdev.json`` for the contract::

    {"mcp_server_config": {"enabled": true, "server_ip": "localhost", "server_port": 19133}}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import Reason, TracyError

DEFAULT_PORT = 19133
DEFAULT_IP = "127.0.0.1"
MCDEV_FILENAME = ".mcdev.json"
ENV_MCDEV_JSON = "MCDK_MCDEV_JSON"


@dataclass(frozen=True)
class McdkConfig:
    """Resolved MCDK MCP endpoint plus where we found it."""

    enabled: bool
    ip: str
    port: int
    source_path: Path | None
    override_url: str | None = None

    @property
    def base_url(self) -> str:
        if self.override_url:
            return self.override_url.rstrip("/").removesuffix("/sse")
        return f"http://{self.ip}:{self.port}"

    @property
    def sse_url(self) -> str:
        if self.override_url:
            url = self.override_url.rstrip("/")
            return url if url.endswith("/sse") else url + "/sse"
        return f"{self.base_url}/sse"


def _normalize_ip(ip: str) -> str:
    return DEFAULT_IP if ip.strip().lower() in ("localhost", "") else ip.strip()


def resolve_mcdev_path(
    explicit_path: str | os.PathLike[str] | None = None,
    project_dir: str | os.PathLike[str] | None = None,
    start_dir: str | os.PathLike[str] | None = None,
) -> Path | None:
    """Find ``.mcdev.json``.

    Priority: explicit path -> ``$MCDK_MCDEV_JSON`` -> ``project_dir/.mcdev.json``
    -> walk up from ``start_dir`` (or CWD) to the filesystem root.
    """
    if explicit_path:
        p = Path(explicit_path).expanduser()
        return p if p.is_file() else None

    env = os.environ.get(ENV_MCDEV_JSON)
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p

    if project_dir:
        p = Path(project_dir).expanduser() / MCDEV_FILENAME
        if p.is_file():
            return p

    cur = Path(start_dir).expanduser().resolve() if start_dir else Path.cwd()
    for d in (cur, *cur.parents):
        candidate = d / MCDEV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_config(path: Path, override_url: str | None = None) -> McdkConfig:
    """Parse ``mcp_server_config`` from a ``.mcdev.json`` file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TracyError(
            Reason.CONFIG_NOT_FOUND, f"failed to read {path}: {exc}", path=str(path)
        ) from exc

    mcp_cfg = raw.get("mcp_server_config") or {}
    return McdkConfig(
        enabled=bool(mcp_cfg.get("enabled", False)),
        ip=_normalize_ip(str(mcp_cfg.get("server_ip", DEFAULT_IP))),
        port=int(mcp_cfg.get("server_port", DEFAULT_PORT)),
        source_path=path,
        override_url=override_url,
    )


def load_config(
    explicit_path: str | os.PathLike[str] | None = None,
    project_dir: str | os.PathLike[str] | None = None,
    override_url: str | None = None,
    require_enabled: bool = True,
    start_dir: str | os.PathLike[str] | None = None,
) -> McdkConfig:
    """Resolve + parse the config, raising typed errors the agent can act on.

    If ``override_url`` is given, ``.mcdev.json`` is optional (we still try to
    read gates from it, but a missing file is not fatal).
    """
    if override_url:
        path = resolve_mcdev_path(explicit_path, project_dir, start_dir)
        if path is not None:
            cfg = parse_config(path, override_url=override_url)
        else:
            cfg = McdkConfig(True, DEFAULT_IP, DEFAULT_PORT, None, override_url=override_url)
        return cfg

    path = resolve_mcdev_path(explicit_path, project_dir, start_dir)
    if path is None:
        raise TracyError(
            Reason.CONFIG_NOT_FOUND,
            "could not locate .mcdev.json; pass --project-dir / --mcdev-json "
            "or set $MCDK_MCDEV_JSON",
        )
    cfg = parse_config(path)
    if require_enabled and not cfg.enabled:
        raise TracyError(
            Reason.MCP_DISABLED,
            "mcp_server_config.enabled is false in .mcdev.json; enable it and "
            "relaunch the game via MCDK",
            mcdev_json=str(path),
        )
    return cfg
