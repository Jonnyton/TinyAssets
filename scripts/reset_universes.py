#!/usr/bin/env python3
"""Clean-slate universe reset CLI — start fresh for the first real universe.

Thin wrapper over ``tinyassets.reset.reset`` (which holds the clear/preserve
policy + tests). Clears all universes + hosted-daemon state while preserving the
branch commons. DESTRUCTIVE: dry-run by default; pass --confirm to execute.

  python scripts/reset_universes.py                 # dry-run plan
  python scripts/reset_universes.py --confirm       # execute
  python scripts/reset_universes.py --data-dir DIR --confirm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Clean-slate universe reset.")
    p.add_argument("--data-dir", default=None, help="Data root (default: data_dir()).")
    p.add_argument(
        "--confirm", action="store_true",
        help="Actually delete. Without this, prints a dry-run plan only.",
    )
    args = p.parse_args()

    from tinyassets.reset import _PRESERVED, reset

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        from tinyassets.storage import data_dir as _dd
        data_dir = _dd()

    plan = reset(data_dir, confirm=args.confirm)
    print(f"[reset_universes] data_dir: {plan['data_dir']}")
    print(f"[reset_universes] universe dirs: {plan['universe_dirs'] or '(none)'}")
    print(f"[reset_universes] .active_universe: {plan['active_universe_marker']}")
    print(f"[reset_universes] db rows to clear: {plan['db_rows_to_clear'] or '(none)'}")
    print(f"[reset_universes] PRESERVED (untouched): {', '.join(_PRESERVED)}")
    print(
        "[reset_universes] DONE — universes + daemons cleared; commons preserved."
        if args.confirm
        else "[reset_universes] DRY RUN — pass --confirm to execute."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
