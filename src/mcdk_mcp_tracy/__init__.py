"""mcdk-mcp-tracy: profiling MCP server for NetEase Minecraft Bedrock mods.

Captures per-function CPU timing from the game client's embedded *native* Tracy
server (TCP 8086) via the bundled tracy-capture / tracy-csvexport CLIs, reduces
the trace server-side, and exposes compact per-function timing / diff tools to
the agent. This path does not go through MCDK and needs no module whitelist.
(``tracy_jank_fps`` is the one tool that still uses MCDK's ``execute_code``, for
frame-level FPS health.)
"""

__version__ = "0.1.0"
