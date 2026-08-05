"""Verify that OpenSpec task preconditions name changes that actually exist.

Run BEFORE building from an OpenSpec task whose text gates the work on other
changes landing first. Catches the "precondition names a change nobody ever
created" class — see PR #2289, where
`activate-custom-agent-runtimes` task 2.3 gated admission of
`enable-custom-agent-workflow-iteration` on four hardening changes and **three
of them had never been created**. They existed only as planned-successor prose,
yet read as real because they were precisely named, cross-referenced in two
`design.md` files and an audit, and sat inside a numbered contract.

The distinction that makes this precise
---------------------------------------
A task may legitimately name a change that does not exist yet — when that
change is the task's *output*:

    2.4 After the underlying transitions land, admit `expose-custom-agent-runtime-control` ...
        \\________ precondition clause ________/        \\____ target (may not exist) ____/

Only names in the *precondition clause* — the span between a dependency cue
(`After`, `Once`, `Depends on`, ...) and the target verb (`admit`, `create`,
...) — are required to resolve. Names after the target verb are what the task
will create, so their absence is expected and never reported.

Usage
-----
    # Scan every active change.
    python scripts/check_openspec_preconditions.py

    # Scan one change (name or path).
    python scripts/check_openspec_preconditions.py activate-custom-agent-runtimes

    # Show resolved preconditions and their open-task counts too.
    python scripts/check_openspec_preconditions.py --verbose

Exit codes
----------
    0  CLEAN    — every precondition reference resolves.
    1  WARNING  — a reference resolves only fuzzily (e.g. it matches an
                  archived change by suffix). Investigate before relying on it.
    2  MISSING  — a precondition names something that resolves nowhere.

A MISSING finding needs classifying, not blind fixing. It means "this name is
referenced as a dependency and matches no change, archived change, or
capability spec." Usually that is the real defect — a gate that can never be
satisfied as written. Sometimes it is a slice or vocabulary term the change's
own design prose defines and deliberately leaves unowned. The report marks
which findings the change's design/proposal also mentions, so you know where to
look; it does not guess, because both cases appear in design.md and no
heuristic separates them reliably.

Read-only. Stdlib-only. No network, no git calls.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Force UTF-8 stdout for Windows consoles (matches scripts/claim_check.py).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

EXIT_CLEAN = 0
EXIT_WARNING = 1
EXIT_MISSING = 2

# A dependency cue opens a precondition clause. Matched case-insensitively.
# These are regexes, not literals, because real task prose uses every
# inflection: "Depend on", "depends on", "depending on" all appear.
PRECONDITION_CUES = (
    r"after",
    r"once",
    r"following",
    r"depend(?:s|ed|ing)?\s+on",
    r"dependent\s+on",
    r"blocked\s+(?:by|on)",
    r"gated\s+(?:on|by)",
    r"requir(?:es|ed|ing)",
    r"prerequisite",
    r"precondition",
    r"upon",
)

# A target verb closes the precondition clause: whatever follows is the thing
# this task produces, which is allowed not to exist yet. `sync` belongs here
# because a change syncs its delta into a capability spec that may not exist
# until that very sync.
#
# Keep this list SHORT and unambiguous. Every entry is a silencer: everything
# after it in the sentence stops being checked, so a word that also occurs as a
# noun creates false negatives. `design` was here briefly and had exactly that
# effect — "its exact ledger dependencies (`design.md` ...)" truncated the
# clause and exempted the real dependency list that followed. Only verbs that
# unambiguously mean "this task produces a new change or spec" belong here.
TARGET_VERBS = (
    "admit",
    "create",
    "author",
    "propose",
    "draft",
    "introduce",
    "spec out",
    "sync",
    # "register a scenario ID" produces an identifier that is not a change.
    # Unambiguous as a verb in this prose; a noun "register" does not occur.
    "register",
)

# A precondition clause also ends at a clause or sentence boundary. Without
# this, a long task sentence leaks unrelated backticked identifiers into the
# clause — e.g. `goal-public-commons`, described after a semicolon as "the
# public-only constant", is not a precondition at all.
_CLAUSE_END = re.compile(r";|(?<!\w\.\w)\.(?:\s|$)")

# Change names in this repo run 2-5 segments (`engine-os-sandbox`,
# `harden-branch-access-authority`). Hyphenated prose in backticks
# (`read-only`, `fail-closed`, `two-actor`, `exact-head`) is 2 segments, so
# requiring 3+ segments discriminates cleanly. Configurable via --min-segments.
DEFAULT_MIN_SEGMENTS = 3

_BACKTICKED = re.compile(r"`([^`\n]+)`")
_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
_ARCHIVE_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_TASK_LINE = re.compile(r"^\s*-\s*\[([ xX])\]\s*([0-9]+(?:\.[0-9]+)*)\s+(.*)$")


class Inventory:
    """Everything a precondition reference is allowed to resolve to."""

    def __init__(self, repo_root: Path) -> None:
        changes_dir = repo_root / "openspec" / "changes"
        archive_dir = changes_dir / "archive"
        specs_dir = repo_root / "openspec" / "specs"

        self.active: set[str] = _dir_names(changes_dir) - {"archive"}
        self.archived_raw: set[str] = _dir_names(archive_dir)
        # Archived changes are stored as `YYYY-MM-DD-<name>`.
        self.archived: set[str] = {
            _ARCHIVE_DATE_PREFIX.sub("", name) for name in self.archived_raw
        }
        self.capabilities: set[str] = _dir_names(specs_dir)

    def resolve(self, name: str) -> tuple[str, str]:
        """Return (status, detail) for a referenced name.

        status is one of "active", "archived", "capability", "fuzzy", "missing".
        """
        if name in self.active:
            return "active", "openspec/changes/"
        if name in self.archived:
            return "archived", "openspec/changes/archive/"
        if name in self.capabilities:
            return "capability", "openspec/specs/"
        # An archived directory may carry a name we only match by suffix, e.g. a
        # rename. Report it, but flag it as fuzzy rather than silently passing.
        for raw in sorted(self.archived_raw):
            if raw.endswith(name):
                return "fuzzy", f"openspec/changes/archive/{raw}"
        return "missing", ""


def _dir_names(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {p.name for p in path.iterdir() if p.is_dir()}


def _find_cue(text: str) -> int:
    """Index just past the earliest dependency cue, or -1 if there is none."""
    lowered = text.lower()
    best = -1
    for cue in PRECONDITION_CUES:
        # Cues are regexes. Word boundaries stop "afterwards" and "reopen".
        for match in re.finditer(rf"\b(?:{cue})\b", lowered):
            end = match.end()
            if best == -1 or end < best:
                best = end
    return best


def _find_target(text: str, start: int) -> int:
    """Index of the earliest target verb at or after `start`, or len(text)."""
    lowered = text.lower()
    best = len(text)
    for verb in TARGET_VERBS:
        match = re.search(rf"\b{re.escape(verb)}\b", lowered[start:])
        if match:
            best = min(best, start + match.start())
    return best


def precondition_span(text: str) -> str:
    """Extract the precondition clause from a task's text.

    Returns "" when the text carries no dependency cue.
    """
    cue_end = _find_cue(text)
    if cue_end == -1:
        return ""
    end = _find_target(text, cue_end)
    # Whichever comes first: the task's target verb or a clause boundary.
    boundary = _CLAUSE_END.search(text, cue_end)
    if boundary and boundary.start() < end:
        end = boundary.start()
    return text[cue_end:end]


def referenced_names(span: str, min_segments: int) -> list[str]:
    """Backticked change-name candidates inside a precondition clause."""
    found: list[str] = []
    for token in _BACKTICKED.findall(span):
        token = token.strip()
        # _KEBAB is anchored, so it already rejects paths (`a/b.py`), dotted
        # names, spaces, underscores, and capitals. No separate check needed.
        if not _KEBAB.match(token):
            continue
        if token.count("-") + 1 < min_segments:
            continue
        if token not in found:
            found.append(token)
    return found


def open_task_count(change_dir: Path) -> int | None:
    """Unchecked task count for a change, or None when it has no tasks.md."""
    tasks = change_dir / "tasks.md"
    if not tasks.is_file():
        return None
    count = 0
    for line in tasks.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _TASK_LINE.match(line)
        if match and match.group(1) == " ":
            count += 1
    return count


def scan_change(change_dir: Path, inv: Inventory, min_segments: int) -> list[dict]:
    """Findings for one change directory."""
    tasks = change_dir / "tasks.md"
    if not tasks.is_file():
        return []
    findings: list[dict] = []
    for lineno, line in enumerate(
        tasks.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        match = _TASK_LINE.match(line)
        if not match:
            continue
        checked, task_id, text = match.group(1) != " ", match.group(2), match.group(3)
        span = precondition_span(text)
        if not span:
            continue
        for name in referenced_names(span, min_segments):
            # A change referencing itself is a wording quirk, not a dependency.
            if name == change_dir.name:
                continue
            status, detail = inv.resolve(name)
            findings.append(
                {
                    "change": change_dir.name,
                    "task": task_id,
                    "line": lineno,
                    "checked": checked,
                    "name": name,
                    "status": status,
                    "detail": detail,
                    "local_vocab": (
                        defines_locally(change_dir, name)
                        if status == "missing"
                        else False
                    ),
                }
            )
    return findings


def defines_locally(change_dir: Path, name: str) -> bool:
    """Does this change's own design/proposal prose define `name` as a term?

    This is a *classification hint*, not a suppression. Both real cases look
    identical to a resolver:

      - `pooled-training-ownership` is a row in this change's design.md slice
        ledger whose owning-change column literally reads `unassigned` — local
        vocabulary, correctly nonexistent.
      - `harden-run-branch-access-authority` is also named in its change's
        design.md, but as a planned successor that should exist and does not.

    No heuristic separates those reliably, so the guard reports both and prints
    this flag to tell the operator where to look. Guessing here would either
    hide the real defect or cry wolf.
    """
    for fname in ("design.md", "proposal.md"):
        path = change_dir / fname
        if path.is_file() and name in path.read_text(
            encoding="utf-8", errors="replace"
        ):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify OpenSpec task preconditions name changes that exist. "
            "Names after a target verb (admit/create/...) are the task's own "
            "output and are never reported."
        )
    )
    parser.add_argument(
        "change",
        nargs="?",
        help="Change name or path to scan. Omit to scan every active change.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: the repo this script lives in).",
    )
    parser.add_argument(
        "--min-segments",
        type=int,
        default=DEFAULT_MIN_SEGMENTS,
        help=(
            "Minimum hyphen-separated segments for a backticked token to count "
            f"as a change name (default: {DEFAULT_MIN_SEGMENTS})."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Also list preconditions that resolve, with their open-task counts.",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root
    changes_dir = repo_root / "openspec" / "changes"
    if not changes_dir.is_dir():
        print(f"no openspec/changes/ under {repo_root}", file=sys.stderr)
        return EXIT_CLEAN

    inv = Inventory(repo_root)

    if args.change:
        candidate = Path(args.change)
        change_dir = candidate if candidate.is_dir() else changes_dir / args.change
        if not change_dir.is_dir():
            print(f"no such change: {args.change}", file=sys.stderr)
            return EXIT_MISSING
        targets = [change_dir]
    else:
        targets = sorted(
            p for p in changes_dir.iterdir() if p.is_dir() and p.name != "archive"
        )

    findings: list[dict] = []
    for change_dir in targets:
        findings.extend(scan_change(change_dir, inv, args.min_segments))

    missing = [f for f in findings if f["status"] == "missing"]
    fuzzy = [f for f in findings if f["status"] == "fuzzy"]
    resolved = [f for f in findings if f["status"] in ("active", "archived", "capability")]

    print(f"# check_openspec_preconditions — {len(targets)} change(s) scanned")
    print()

    if missing:
        print(f"## MISSING ({len(missing)}) — precondition names nothing that exists")
        for f in missing:
            state = "done" if f["checked"] else "open"
            hint = (
                "  [also defined in this change's design/proposal prose"
                " — may be local vocabulary rather than a change reference]"
                if f["local_vocab"]
                else ""
            )
            print(
                f"- {f['change']} task {f['task']} ({state}, tasks.md:{f['line']})"
                f" -> `{f['name']}` does not exist{hint}"
            )
        print()
        print(
            "Classify each: a dangling *change* reference is a defect (the gate "
            "can never be satisfied); a name your design prose defines as a slice "
            "or vocabulary term is not."
        )
        print()

    if fuzzy:
        print(f"## FUZZY ({len(fuzzy)}) — resolved only by suffix match")
        for f in fuzzy:
            print(
                f"- {f['change']} task {f['task']} (tasks.md:{f['line']})"
                f" -> `{f['name']}` ~ {f['detail']}"
            )
        print()

    if args.verbose and resolved:
        print(f"## RESOLVED ({len(resolved)})")
        for f in resolved:
            extra = ""
            if f["status"] == "active":
                count = open_task_count(changes_dir / f["name"])
                if count is not None:
                    extra = f" — {count} open task(s)" if count else " — complete"
            print(
                f"- {f['change']} task {f['task']} -> `{f['name']}`"
                f" [{f['status']}]{extra}"
            )
        print()

    if not findings:
        print("No precondition references found.")
    elif not missing and not fuzzy:
        print(f"CLEAN — all {len(resolved)} precondition reference(s) resolve.")

    if missing:
        return EXIT_MISSING
    if fuzzy:
        return EXIT_WARNING
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
