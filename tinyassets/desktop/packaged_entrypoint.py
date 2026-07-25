"""Single-binary role dispatcher used by native desktop packages."""

from __future__ import annotations

import sys
from pathlib import Path

from tinyassets.desktop.onboarding import (
    AutostartManager,
    PackagedAuthorityUnavailable,
    require_packaged_authority,
)


class PackagedRuntimeUnavailable(RuntimeError):
    """A packaged role cannot start until its runtime authority is valid."""


def _data_root() -> Path:
    from tinyassets.storage import data_dir

    return data_dir()


def _require_authority() -> None:
    try:
        require_packaged_authority(_data_root() / "desktop")
    except PackagedAuthorityUnavailable as exc:
        raise PackagedRuntimeUnavailable(str(exc)) from exc


def _ensure_autostart() -> None:
    AutostartManager(
        command=[sys.executable],
        platform_name=sys.platform,
    ).enable()


def _health_probe() -> None:
    root = _data_root()
    (root / "logs").mkdir(parents=True, exist_ok=True)
    import tinyassets_tray  # noqa: F401


def dispatch(arguments: list[str] | None = None) -> int:
    """Run the tray or a child daemon/MCP role from one frozen executable."""
    args = list(sys.argv[1:] if arguments is None else arguments)
    if not args:
        _ensure_autostart()
        import tinyassets_tray

        return tinyassets_tray.main()
    if args[0] != "--packaged-role" or len(args) < 2:
        raise SystemExit("unknown packaged runtime arguments")
    role = args[1]
    forwarded = args[2:]
    sys.argv = [sys.argv[0], *forwarded]
    if role == "health-probe":
        _health_probe()
        return 0
    if role == "daemon":
        try:
            _require_authority()
        except PackagedRuntimeUnavailable as exc:
            raise SystemExit(str(exc)) from exc
        from fantasy_daemon.__main__ import main

        main()
        return 0
    if role == "mcp":
        try:
            _require_authority()
        except PackagedRuntimeUnavailable as exc:
            raise SystemExit(str(exc)) from exc
        from tinyassets.universe_server import main

        main(host="0.0.0.0", port=8001, transport="streamable-http")
        return 0
    raise SystemExit(f"unknown packaged runtime role: {role}")


def main() -> int:
    return dispatch()


if __name__ == "__main__":
    raise SystemExit(main())
