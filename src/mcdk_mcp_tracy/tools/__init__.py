"""Tool registration. ``register_all`` wires every tool group onto the server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..state import ServerState
from . import (
    register_jankfps,
    register_native,
    register_query,
    register_status,
)


def register_all(mcp: FastMCP, state: ServerState) -> None:
    register_status.register(mcp, state)
    register_query.register(mcp, state)
    register_jankfps.register(mcp, state)
    register_native.register(mcp, state)
