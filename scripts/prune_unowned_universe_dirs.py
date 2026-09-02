#!/usr/bin/env python3
"""Show, then cut, the directories under the data root that nobody owns.

Founder, 2026-09-02: *"a prune cuts bad branches off. this made the branches
unconnected but still sitting in the tree."*

    # what is there, and who owns it (changes nothing)
    python scripts/prune_unowned_universe_dirs.py

    # cut the ones nobody owns
    python scripts/prune_unowned_universe_dirs.py --apply

    # cut exactly these
    python scripts/prune_unowned_universe_dirs.py --apply --only _removed_universes_20260828

Ownership is re-read inside the removal, per directory, so a listing printed
earlier can never authorise deleting a universe somebody has since claimed
(2026-08-26: a live user's bound universe was archived off a stale inventory).

Run it in the daemon's container, where ``TINYASSETS_DATA_DIR`` points at the
real volume:

    docker exec -i tinyassets-daemon python /app/scripts/prune_unowned_universe_dirs.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _human(byte_count: int) -> str:
    value = float(byte_count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--apply", action="store_true",
        help="actually remove. Without it, nothing changes.",
    )
    ap.add_argument(
        "--only", action="append", default=[], metavar="NAME",
        help="restrict to these directory names (repeatable)",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    from tinyassets.storage import data_dir
    from tinyassets.universe_prune import plan, prune

    base = data_dir()
    reports = plan(base)
    if not reports:
        print(f"no directories under {base}")
        return 0

    removable = [r for r in reports if r.removable]
    if args.only:
        wanted = set(args.only)
        removable = [r for r in removable if r.name in wanted]
        unknown = wanted - {r.name for r in reports}
        for name in sorted(unknown):
            print(f"  ! {name}: no such directory", file=sys.stderr)

    if args.json:
        print(json.dumps({
            "data_dir": str(base),
            "directories": [r.as_dict() for r in reports],
        }, indent=2))
    else:
        print(f"{base}\n")
        for r in reports:
            if r.is_infrastructure:
                kind = "infrastructure"
            elif r.owners:
                kind = "universe of " + ", ".join(r.owners)
            else:
                kind = "UNOWNED"
            notable = f"  [{', '.join(r.notable_files)}]" if r.notable_files else ""
            print(
                f"  {r.name:<48} {kind:<40} "
                f"{r.file_count:>6} files  {_human(r.byte_count):>10}{notable}"
            )
        print()

    if not removable:
        print("nothing unowned to cut.")
        return 0

    if not args.apply:
        print(
            f"{len(removable)} unowned director{'y' if len(removable) == 1 else 'ies'} "
            f"would be removed: {', '.join(r.name for r in removable)}\n"
            "Re-run with --apply to cut them."
        )
        return 0

    result = prune(base, names=[r.name for r in removable], apply=True)
    for name in result["removed"]:
        print(f"  cut {name}")
    for entry in result["refused"]:
        print(f"  kept {entry['name']}: {entry['reason']}", file=sys.stderr)
    print(f"\nremoved {result['removed_count']}, kept {result['refused_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
