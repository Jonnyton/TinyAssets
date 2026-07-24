"""``python -m command_center`` — launch the Agent Village web command center."""

from __future__ import annotations

import argparse

from . import __version__
from .collector import Config
from .server import serve


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="command_center",
        description=(
            "Agent Village — watch every AI agent working this repo as sprites "
            "on a loopback-only live village map."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="literal loopback bind host: 127.0.0.1 or ::1 (default 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=8787, help="bind port (default 8787)")
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    try:
        cfg = Config.from_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    serve(cfg)


if __name__ == "__main__":
    main()
