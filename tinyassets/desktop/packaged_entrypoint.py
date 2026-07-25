"""Single-binary role dispatcher used by native desktop packages."""

from __future__ import annotations

import sys


def dispatch(arguments: list[str] | None = None) -> int:
    """Run the tray or a child daemon/MCP role from one frozen executable."""
    args = list(sys.argv[1:] if arguments is None else arguments)
    if not args:
        import tinyassets_tray

        return tinyassets_tray.main()
    if args[0] != "--packaged-role" or len(args) < 2:
        raise SystemExit("unknown packaged runtime arguments")
    role = args[1]
    forwarded = args[2:]
    sys.argv = [sys.argv[0], *forwarded]
    if role == "daemon":
        from fantasy_daemon.__main__ import main

        main()
        return 0
    if role == "mcp":
        from tinyassets.universe_server import main

        main(host="0.0.0.0", port=8001, transport="streamable-http")
        return 0
    raise SystemExit(f"unknown packaged runtime role: {role}")


def main() -> int:
    return dispatch()


if __name__ == "__main__":
    raise SystemExit(main())
