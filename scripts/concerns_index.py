#!/usr/bin/env python3
"""Print the open-concerns index, built from each concern file's front-matter.

The index used to be a hand-edited table in docs/concerns/README.md. Every PR
that filed or resolved a concern edited the same table, so parallel PRs
conflicted on it: tonight's measurement (2026-09-27) found 30 merge-main commits
across 15 of 22 merged PRs, and the table was a standing source. Now each file
carries its own row, so filing or resolving a concern touches exactly one file:

    ---
    severity: P1          # P0 / P1 / P2 / P3 / Watch / note, or null
    title: One-line name of the finding
    filed: '2026-09-27'
    summary: what is wrong, in one or two sentences
    ---

Usage:
    python scripts/concerns_index.py            # markdown table, most severe first
    python scripts/concerns_index.py --check    # validate every file; exit 1 on problems
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

CONCERNS = Path(__file__).resolve().parent.parent / "docs" / "concerns"
SEVERITIES = ["P0", "P1", "P2", "P3", "Watch", "note", None]
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def concern_files(directory: Path = CONCERNS) -> list[Path]:
    return sorted(p for p in directory.glob("*.md") if p.name != "README.md")


def read_front_matter(path: Path) -> dict:
    """Return the front-matter mapping; raise ValueError when it is missing or invalid."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: no front-matter (file must start with '---')")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"{path.name}: front-matter is not closed by '---'")
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise ValueError(f"{path.name}: front-matter is not valid YAML ({exc})") from None
    if not isinstance(meta, dict):
        raise ValueError(f"{path.name}: front-matter is not a mapping")
    problems = []
    if meta.get("severity") not in SEVERITIES:
        problems.append(f"severity {meta.get('severity')!r} not in {SEVERITIES}")
    if not isinstance(meta.get("title"), str) or not meta["title"].strip():
        problems.append("title is missing")
    filed = str(meta.get("filed", ""))
    if not _DATE.match(filed):
        problems.append(f"filed {meta.get('filed')!r} is not YYYY-MM-DD")
    if "summary" in meta and not isinstance(meta["summary"], str):
        problems.append("summary is not a string")
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems))
    meta["filed"] = filed
    return meta


def render(directory: Path = CONCERNS) -> str:
    rows = []
    for path in concern_files(directory):
        meta = read_front_matter(path)
        rows.append((SEVERITIES.index(meta["severity"]), meta["filed"], path.name, meta))
    # Most severe first, newest first within a severity.
    rows.sort(key=lambda r: (r[0], [-ord(c) for c in r[1]], r[2]))
    lines = ["| Severity | Concern | Filed |", "|---|---|---|"]
    for _, filed, name, meta in rows:
        severity = f"**{meta['severity']}**" if meta["severity"] else "—"
        summary = f" — {meta['summary']}" if meta.get("summary") else ""
        cell = f"[{meta['title']}]({name}){summary}".replace("|", "\\|")
        lines.append(f"| {severity} | {cell} | {filed} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="validate every concern file")
    args = ap.parse_args()
    if args.check:
        problems = []
        for path in concern_files():
            try:
                read_front_matter(path)
            except ValueError as exc:
                problems.append(str(exc))
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
