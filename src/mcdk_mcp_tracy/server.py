"""FastMCP server bootstrap: build the server + shared state and register tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .mcdk_client import McdkClient
from .state import ServerState
from .tools import register_all

SERVER_NAME = "mcdk-mcp-tracy"

SERVER_INSTRUCTIONS = (
    "Profiles a running NetEase Minecraft Bedrock mod via its embedded native "
    "Tracy server (TCP 8086) to surface per-function timing for code review and "
    "optimization. Workflow: tracy_status (probe 8086 + bundled CLIs) -> drive "
    "gameplay + tracy_native_capture (optionally name_contains your mod) -> "
    "tracy_get_function_costs -> optimize -> capture again -> tracy_diff_captures. "
    "tracy_jank_fps gives frame-level FPS health. The native capture path needs no "
    "module whitelist and is independent of MCDK; only tracy_jank_fps uses MCDK's "
    "execute_code, so launch the game via MCDK with mcp_server_config.enabled=true."
)


def build_server(
    project_dir: str | None = None,
    mcdev_json: str | None = None,
    mcdk_url: str | None = None,
) -> tuple[FastMCP, ServerState]:
    """Construct the FastMCP server and its shared state (no I/O yet)."""
    client = McdkClient(
        explicit_path=mcdev_json, project_dir=project_dir, override_url=mcdk_url
    )
    state = ServerState(client=client)
    mcp = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    register_all(mcp, state)
    return mcp, state
