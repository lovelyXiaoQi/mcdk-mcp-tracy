"""mcdk-mcp-tracy: profiling MCP server for NetEase Minecraft Bedrock mods.

Drives the game's in-game CPU profiler (``utility.getCpuFrameData`` / the
NetEase engine "tracy_mod") through MCDK's ``execute_code`` MCP tool, reduces
the per-frame data in-game and server-side, and exposes compact per-function
timing / hotspot / diff tools to the agent.
"""

__version__ = "0.1.0"
