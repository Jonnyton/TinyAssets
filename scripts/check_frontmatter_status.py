"""Measure (and optionally gate) frontmatter `status:` compliance under `docs/`.

`docs/conventions.md` § "Frontmatter `status:` field" used to hardcode compliance
counts in prose ("80/80 notes carry it"). Those numbers were measured once, on
2026-04-28, and silently expired — a correct-but-expired fact reads exactly like a
current one, which `AGENTS.md` § Truth And Freshness calls out as the defect class.
This script is the fix: the doc points here, and the number is computed on demand.

Usage
-----
    # Report: print the compliance table plus every non-compliant file.
    python scripts/check_frontmatter_status.py

    # Gate: same output, but exit 1 if a required directory has any violation.
    python scripts/check_frontmatter_status.py --check

    # Measure a different tree (used by the tests).
    python scripts/check_frontmatter_status.py --root /path/to/tree

Exit codes
----------
    0  OK        — report mode, or `--check` with no violations.
    1  VIOLATION — `--check` only: a required-directory file breaks a rule.
    2  ERROR     — bad usage (e.g. `--root` is not a directory).

What `--check` enforces, in the required directories only, matching the three
testable claims the conventions section makes:

    1. every `*.md` (except `INDEX.md`) has a `status:` key in YAML frontmatter;
    2. its value is one of the five documented lifecycle values;
    3. `status: superseded` carries a `superseded_by:` whose every path resolves.

Directories listed as informational are counted but never gated — `docs/audits/`
holds event-records whose `status:` is descriptive, not lifecycle, and the
exec-plan directories encode lifecycle by directory placement instead.

Glob semantics match the doc: `docs/design-notes/*.md` is top-level only, so
`docs/design-notes/proposed/` is reported as its own (informational) directory.

Stdlib-only. Read-only — never writes to the tree it measures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Force UTF-8 stdout for Windows consoles (matches scripts/check_primitive_exists.py).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass

# Directories where `status:` is REQUIRED — these are what `--check` gates.
REQUIRED_DIRS = ("docs/design-notes", "docs/specs")

# Counted for visibility, never gated. See the module docstring for why.
INFORMATIONAL_DIRS = (
    "docs/design-notes/proposed",
    "docs/exec-plans/active",
    "docs/exec-plans/completed",
    "docs/audits",
)

# The five documented lifecycle values.
LIFECYCLE_VALUES = ("active", "shipped", "superseded", "research", "historical")

# Index pages describe a directory rather than a unit of work.
EXCLUDED_NAMES = frozenset({"INDEX.md"})


def parse_frontmatter(text: str) -> dict[str, str | list[str]] | None:
    """Parse a leading YAML frontmatter block.

    Returns the key/value mapping, or None when the document has no frontmatter
    block (no `---` on the very first line, or no closing delimiter).

    Deliberately a small subset of YAML — enough for the shapes this repo
    actually uses, and stdlib-only so the script has no dependency:
      * `key: value`                        -> str
      * `key:` followed by `  - item` lines -> list[str]
    A `status:` mentioned in the body, or inside a fenced block, is NOT
    frontmatter and is correctly ignored. Keys are not parsed recursively;
    nested mappings collapse to an empty string, which is fine because every
    key this script reads is scalar-or-list.
    """
    lines = text.lstrip("﻿").split("\n")
    if not lines or lines[0].strip() != "---":
        return None

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return None

    fields: dict[str, str | list[str]] = {}
    key: str | None = None
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw[:1].isspace() or raw.startswith("-"):
            # Continuation of the previous key: a `- item` list entry.
            if key is not None and stripped.startswith("- "):
                item = stripped[2:].strip()
                current = fields.get(key)
                if isinstance(current, list):
                    current.append(item)
                elif not current:
                    fields[key] = [item]
            continue
        if ":" not in stripped:
            continue
        name, _, value = stripped.partition(":")
        name = name.strip()
        if not name:
            continue
        key = name
        fields[key] = value.strip()
    return fields


class FileResult:
    """One document's verdict."""

    def __init__(self, path: Path, problem: str | None, detail: str = "") -> None:
        self.path = path
        self.problem = problem  # None | "no-status" | "bad-value" | "bad-superseded-by"
        self.detail = detail


def check_file(path: Path, root: Path) -> FileResult:
    """Apply the three conventions-section rules to one document."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # pragma: no cover - unreadable file is an env problem
        return FileResult(path, "no-status", f"unreadable: {exc}")

    fields = parse_frontmatter(text)
    status = (fields or {}).get("status")
    if not isinstance(status, str) or not status:
        return FileResult(path, "no-status")

    if status not in LIFECYCLE_VALUES:
        return FileResult(path, "bad-value", f"status: {status}")

    if status == "superseded":
        assert fields is not None
        target = fields.get("superseded_by")
        targets = [target] if isinstance(target, str) else list(target or [])
        targets = [t for t in targets if t]
        if not targets:
            return FileResult(path, "bad-superseded-by", "missing superseded_by")
        unresolved = [t for t in targets if not (root / t).exists()]
        if unresolved:
            return FileResult(
                path, "bad-superseded-by", "does not resolve: " + ", ".join(unresolved)
            )

    return FileResult(path, None)


class DirResult:
    """One directory's tally."""

    def __init__(self, rel: str, exists: bool) -> None:
        self.rel = rel
        self.exists = exists
        self.files: list[FileResult] = []

    @property
    def total(self) -> int:
        return len(self.files)

    @property
    def compliant(self) -> int:
        return sum(1 for f in self.files if f.problem is None)

    def problems(self, kind: str) -> list[FileResult]:
        return [f for f in self.files if f.problem == kind]

    @property
    def with_status(self) -> int:
        """Count of files carrying any `status:` — the number the doc quotes."""
        return sum(1 for f in self.files if f.problem != "no-status")


def scan_dir(root: Path, rel: str) -> DirResult:
    """Scan one directory, top-level `*.md` only (matching the doc's glob)."""
    directory = root / rel
    result = DirResult(rel, directory.is_dir())
    if not result.exists:
        return result
    for path in sorted(directory.glob("*.md")):
        if path.name in EXCLUDED_NAMES:
            continue
        result.files.append(check_file(path, root))
    return result


def scan(root: Path) -> tuple[list[DirResult], list[DirResult]]:
    """Scan the required and informational directories."""
    return (
        [scan_dir(root, rel) for rel in REQUIRED_DIRS],
        [scan_dir(root, rel) for rel in INFORMATIONAL_DIRS],
    )


_PROBLEM_LABELS = (
    ("no-status", "no `status:` in frontmatter"),
    ("bad-value", "`status:` value outside the five lifecycle values"),
    ("bad-superseded-by", "`status: superseded` without a resolving `superseded_by:`"),
)


def _print_table(title: str, results: list[DirResult]) -> None:
    print(title)
    for r in results:
        if not r.exists:
            print(f"  {r.rel:<34} MISSING")
            continue
        if not r.total:
            print(f"  {r.rel:<34} (empty)")
            continue
        pct = 100.0 * r.with_status / r.total
        print(f"  {r.rel:<34} {r.with_status:>4}/{r.total:<4} carry `status:`  ({pct:.0f}%)")


def report(root: Path) -> int:
    """Print the compliance table and every violation. Returns the violation count."""
    required, informational = scan(root)

    _print_table("REQUIRED (gated by --check):", required)
    print()
    _print_table("INFORMATIONAL (counted, never gated):", informational)

    violations = 0
    for r in required:
        for kind, label in _PROBLEM_LABELS:
            hits = r.problems(kind)
            if not hits:
                continue
            violations += len(hits)
            print()
            print(f"{r.rel} — {len(hits)} file(s) with {label}:")
            for f in hits:
                suffix = f"  ({f.detail})" if f.detail else ""
                print(f"  {f.path.name}{suffix}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure frontmatter `status:` compliance under docs/.",
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="repository root to measure (default: this script's repo)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if a required-directory file breaks a rule",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: --root is not a directory: {root}", file=sys.stderr)
        return 2

    violations = report(root)
    print()
    if violations:
        print(f"{violations} violation(s) in required directories.")
        if args.check:
            return 1
        print("Report mode — rerun with --check to make this exit non-zero.")
    else:
        print("No violations in required directories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
