"""Entry point: ``python -m mcdk_mcp_tracy`` / console-script ``mcdk-mcp-tracy``.

Defaults to stdio transport (the agent spawns us and talks over stdio; we dial
MCDK's SSE endpoint ourselves). All diagnostics go to stderr so stdout stays a
clean JSON-RPC channel.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .server import build_server


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcdk-mcp-tracy",
        description="Profiling MCP server for NetEase Minecraft Bedrock mods.",
    )
    p.add_argument("--stdio", action="store_true", help="Use stdio transport (default).")
    p.add_argument("--sse", action="store_true", help="Use SSE transport instead of stdio.")
    p.add_argument(
        "--project-dir",
        help="Mod project dir whose .mcdev.json provides MCDK's MCP port.",
    )
    p.add_argument("--mcdev-json", help="Explicit path to a .mcdev.json file.")
    p.add_argument(
        "--mcdk-url",
        help="Override MCDK's MCP base/SSE URL (e.g. http://127.0.0.1:19133).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level for diagnostics on stderr (default INFO).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp, _state = build_server(
        project_dir=args.project_dir,
        mcdev_json=args.mcdev_json,
        mcdk_url=args.mcdk_url,
    )
    transport = "sse" if args.sse else "stdio"
    logging.getLogger("mcdk_mcp_tracy").info("starting mcdk-mcp-tracy (transport=%s)", transport)
    mcp.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
