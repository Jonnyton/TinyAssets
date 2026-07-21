"""Compatibility command for the one-way encrypted legacy-vault migration.

The former subscription-only migration has been superseded by
``tinyassets.credential_migration``.  This module name remains runnable for
operators and images that already reference it, but it delegates to the single
broker migration and never imports or reads the retired vault module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tinyassets.credential_broker import LEGACY_ARTIFACT_DIR, LEGACY_VAULT_FILENAME
from tinyassets.credential_migration import migrate_universe_credentials


def _data_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    from tinyassets.storage import data_dir

    return data_dir()


def _universe_dirs(root: Path, only: str | None) -> list[Path]:
    candidates = [root / only] if only else list(root.iterdir()) if root.is_dir() else []
    return sorted(
        path
        for path in candidates
        if path.is_dir()
        and not path.name.startswith(".")
        and (
            (path / LEGACY_VAULT_FILENAME).exists()
            or (path / LEGACY_ARTIFACT_DIR).exists()
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tinyassets.migrations.retired_subscription_records"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--migrate", action="store_true")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--universe", default=None)
    args = parser.parse_args(argv)

    root = _data_root(args.data_dir)
    universes = _universe_dirs(root, args.universe)
    results: list[dict[str, object]] = []
    failures = 0
    for universe in universes:
        try:
            if args.inventory:
                results.append(
                    {"universe": universe.name, "status": "needs_migration"}
                )
            else:
                results.append(migrate_universe_credentials(universe, base=root))
        except Exception as exc:  # noqa: BLE001 - report every blocked universe
            failures += 1
            results.append({"universe": universe.name, "error": str(exc)})
    print(
        json.dumps(
            {
                "mode": "inventory" if args.inventory else "migrate",
                "data_root": str(root),
                "universes_scanned": len(universes),
                "results": results,
            },
            indent=2,
        )
    )
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
