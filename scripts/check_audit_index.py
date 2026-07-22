"""Check that every audit under docs/audits/ is reachable from its INDEX.md.

`docs/conventions.md` § *Linking* requires every durable note to be linked from
at least one index page. `docs/audits/` had no index at all until 2026-07-22,
and audits are the one note class AGENTS.md § *Truth And Freshness* tells you to
re-check before acting on ("audit docs decay too") — which you cannot do for a
document you cannot find.

This checker is deliberately narrow. It verifies three things and nothing else:

- every `docs/audits/**/*.md` has a link entry in `docs/audits/INDEX.md`;
- every link in the index resolves to a file that exists;
- no audit is listed twice.

It does NOT check hook text quality, ordering, or section placement — those are
editorial and would make the check noisy.

Exit 0 when clean, 2 when the index is out of sync, matching
`check_cross_provider_drift.py` so a hook or CI step can block on it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass

AUDITS_DIR = Path("docs/audits")
INDEX_NAME = "INDEX.md"

# Matches a markdown link whose target ends in .md, tolerating <angle> wrapping
# and a #fragment. Deliberately link-syntax-only: a bare filename mentioned in
# prose is a mention, not a link, and does not make a note reachable.
LINK_RE = re.compile(r"\]\(\s*<?([^)>\s#]+\.md)(?:#[^)]*)?>?\s*\)")


def find_audits(root: Path) -> set[str]:
    """Every audit .md, as a path relative to the audits dir, POSIX-separated."""
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*.md")
        if p.name != INDEX_NAME
    }


def indexed_targets(index_path: Path) -> list[str]:
    text = index_path.read_text(encoding="utf-8")
    return [
        t
        for t in LINK_RE.findall(text)
        if not t.startswith(("http://", "https://", "mailto:"))
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo-root",
        default=".",
        help="Repo root to check (default: cwd).",
    )
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    audits_dir = root / AUDITS_DIR
    index_path = audits_dir / INDEX_NAME

    if not audits_dir.is_dir():
        print(f"ERROR: {AUDITS_DIR} not found under {root}", file=sys.stderr)
        return 2
    if not index_path.is_file():
        print(f"ERROR: {AUDITS_DIR}/{INDEX_NAME} is missing.", file=sys.stderr)
        return 2

    audits = find_audits(audits_dir)
    targets = indexed_targets(index_path)

    unindexed = sorted(audits - set(targets))
    broken = sorted({t for t in targets if not (audits_dir / t).is_file()})
    duplicated = sorted({t for t in targets if targets.count(t) > 1})

    if not (unindexed or broken or duplicated):
        print(f"OK: all {len(audits)} audits are indexed in {AUDITS_DIR}/{INDEX_NAME}.")
        return 0

    if unindexed:
        print(
            f"{len(unindexed)} audit(s) missing from {AUDITS_DIR}/{INDEX_NAME}:",
            file=sys.stderr,
        )
        for name in unindexed:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nFix: add one line per audit under the section that fits, using the "
            "audit's own H1 as the hook:\n"
            "  - [`<filename>`](<filename>) — <its H1>",
            file=sys.stderr,
        )
    if broken:
        print(f"\n{len(broken)} index link(s) point at missing files:", file=sys.stderr)
        for name in broken:
            print(f"  - {name}", file=sys.stderr)
    if duplicated:
        print(f"\n{len(duplicated)} audit(s) listed more than once:", file=sys.stderr)
        for name in duplicated:
            print(f"  - {name}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
