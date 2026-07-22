#!/usr/bin/env python3
"""Write a lane's activity entry as its own file under `.agents/activity.d/`.

Every lane appending to the single `.agents/activity.log` collides with every
other lane on the file's final hunk — a structural conflict with nothing to
reconcile. One file per lane removes the shared write target.

    python scripts/activity_append.py --lane status-janitor --body "what happened"
    python scripts/activity_append.py --lane status-janitor --body-file notes.md

Rationale and the rejected `merge=union` alternative: `.agents/activity.d/README.md`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

ACTIVITY_DIR = Path(".agents/activity.d")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated, filesystem-safe lane name."""
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"lane name produced an empty slug: {value!r}")
    return slug


def entry_path(lane: str, date: str, root: Path = Path(".")) -> Path:
    """First free `<date>-<lane>.md`, suffixing -2, -3, ... rather than appending.

    Appending to an existing file would recreate the shared write target this
    script exists to avoid, so a same-day second entry gets its own file.
    """
    directory = root / ACTIVITY_DIR
    base = f"{date}-{slugify(lane)}"
    candidate = directory / f"{base}.md"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{base}-{counter}.md"
        counter += 1
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", required=True, help="Lane/branch slug, e.g. status-janitor.")
    parser.add_argument("--body", help="Entry text.")
    parser.add_argument("--body-file", help="Read entry text from this file ('-' for stdin).")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today, UTC).")
    parser.add_argument("--root", default=".", help="Repo root (default: cwd).")
    args = parser.parse_args(argv)

    if bool(args.body) == bool(args.body_file):
        parser.error("pass exactly one of --body or --body-file")

    if args.body_file == "-":
        body = sys.stdin.read()
    elif args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    else:
        body = args.body

    body = body.strip()
    if not body:
        parser.error("refusing to write an empty entry")

    date = args.date or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")

    root = Path(args.root)
    directory = root / ACTIVITY_DIR
    if not directory.is_dir():
        parser.error(f"{directory} does not exist — are you at the repo root?")

    path = entry_path(args.lane, date, root=root)
    path.write_text(f"# {date} — {args.lane}\n\n{body}\n", encoding="utf-8", newline="\n")
    print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
