"""``python -m command_center`` — launch the Agent Village web command center."""

from __future__ import annotations

import argparse
import os

from . import __version__
from .collector import Config
from .server import serve


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="command_center",
        description=(
            "Agent Village — watch every AI agent working this repo as sprites "
            "on a live village map, from your phone."
        ),
    )
    parser.add_argument("--host", default="0.0.0.0", help="bind host (default 0.0.0.0 = LAN)")
    parser.add_argument("--port", type=int, default=8787, help="bind port (default 8787)")
    parser.add_argument("--token", default=None, help="optional shared token for ?token= access")
    parser.add_argument(
        "--dispatch",
        action="store_true",
        help="also dispatch talk messages to provider CLIs via scripts/peer_agent.py "
        "(spends that provider's subscription budget; default is inbox-only)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="state poll interval seconds (default 3)",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help="remote Workflow MCP endpoint (e.g. https://tinyassets.io/mcp) to include "
        "live universes alongside local ones",
    )
    parser.add_argument(
        "--directory-url",
        default="https://tinyassets.io",
        help="platform base URL for the world view + live universes "
        "(default https://tinyassets.io; '' disables)",
    )
    parser.add_argument(
        "--mcp-token",
        default=os.environ.get("WORKFLOW_MCP_TOKEN"),
        help="Bearer token for the platform MCP endpoint (or WORKFLOW_MCP_TOKEN env)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    serve(Config.from_args(args))


if __name__ == "__main__":
    main()
