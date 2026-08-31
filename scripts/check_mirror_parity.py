"""Fail when the packaged-plugin mirror does not match canonical `tinyassets/`.

The pre-commit hook calls this with the staged canonical paths; run it with no
paths for a whole-tree scan (what CI does through
``invariants_run.py --pre-commit``). Both routes share one implementation in
``scripts/invariants/mirror_parity.py``, because the hook and the CI job
disagreeing about what parity means is how a mirror goes stale for three
commits while both gates report clean.

Exit 0 when parity holds, 1 when any canonical file is missing from the mirror
or diverges from it. Every offending path is named.

    python scripts/check_mirror_parity.py                       # whole tree
    python scripts/check_mirror_parity.py tinyassets/runs.py    # staged subset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.invariants.mirror_parity import (  # noqa: E402
    CANONICAL_ROOT,
    MIRROR_ROOT,
    scan_parity,
)

_CANONICAL_PREFIX = "tinyassets/"


def _relative(raw: str) -> str:
    """Accept a repo-relative path (what git stages) or a canonical-relative one."""
    text = str(raw).replace("\\", "/").strip()
    if text.startswith(_CANONICAL_PREFIX):
        return text[len(_CANONICAL_PREFIX) :]
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="canonical paths to check; omit for the whole tree",
    )
    parser.add_argument("--canonical-root", default=str(CANONICAL_ROOT))
    parser.add_argument("--mirror-root", default=str(MIRROR_ROOT))
    args = parser.parse_args(argv)

    canonical_root = Path(args.canonical_root)
    mirror_root = Path(args.mirror_root)
    if not canonical_root.is_dir():
        print(f"mirror-parity: canonical root not found: {canonical_root}")
        return 0
    if not mirror_root.is_dir():
        print(f"mirror-parity: mirror root not found: {mirror_root}")
        return 0

    relative = [_relative(path) for path in args.paths] if args.paths else None
    report = scan_parity(canonical_root, mirror_root, relative_paths=relative)
    if report.ok:
        print(f"mirror-parity: {report.message()}")
        return 0

    print(f"mirror-parity: {report.message()}", file=sys.stderr)
    for line in report.detail_lines():
        print(line, file=sys.stderr)
    print("", file=sys.stderr)
    print("Rebuild the mirror and stage it in the same commit:", file=sys.stderr)
    print("  python packaging/claude-plugin/build_plugin.py", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
