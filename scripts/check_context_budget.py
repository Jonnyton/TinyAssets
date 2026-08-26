#!/usr/bin/env python3
"""Guard the always-loaded agent-context budget.

Best-practice basis (2026-06-24 SDLC/vibe-coding + Claude-large-codebases audit,
`docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md`):
instruction files that load on *every* turn are static context the model pays
for unconditionally. The "lean and layered" rule only holds if something
measures it — a 2026-04-28 cross-check put AGENTS.md at ~17.6 KB, and by
2026-06-24 it had tripled to ~54 KB with no guardrail noticing. This script is
that guardrail: it measures the always-loaded set and flags drift.

Two budget classes:
  * HARD  — a ceiling the project has committed to. Enforcing a stated
            contract is not a judgement call, so `--strict` exits 2 when a
            HARD budget is exceeded.
  * SOFT  — advisory; WARNs but never fails, even under --strict. No entry is
            SOFT today; the class is kept for content whose ceiling is a
            genuine judgement call rather than a committed limit.

Usage:
  python scripts/check_context_budget.py            # report table, exit 0
  python scripts/check_context_budget.py --strict    # exit 2 if a HARD budget is busted
  python scripts/check_context_budget.py --json       # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Budget:
    path: str
    kind: str  # "hard" | "soft"
    max_bytes: int
    max_lines: int
    note: str

# Always-loaded set: CLAUDE.md imports @AGENTS.md, so both load every session.
# PLAN.md is intentionally NOT imported (pointer-loaded), so it is not budgeted.
# STATUS.md was retired 2026-08-25 and left this set entirely.
#
# These are HARD, and set just above what the 2026-08-25 harness reset actually
# achieved (AGENTS 18,487 B / 312 lines; CLAUDE 6,429 B / 115 lines; combined
# 24,916 B). That is the point: a ceiling set at the achieved value is a
# ratchet; one set at a comfortable round number is a wish. This set grew from
# ~17.6 KB (2026-04-28) to 62,082 B under SOFT budgets that only warned, with
# the invariant registered and VIOLATED the whole time. Loosening a number here
# is now a deliberate, reviewable edit -- that mechanism was what was missing,
# not the measurement.
CONFIG: tuple[Budget, ...] = (
    Budget("AGENTS.md", "hard", 20000, 340,
           "Cross-provider canonical. Move procedure to docs/reference/, not into here."),
    Budget("CLAUDE.md", "hard", 8000, 140,
           "Claude Code router; harness quirks only, a thin layer over AGENTS.md."),
)

# HARD ceiling for the combined always-loaded payload (~7K tokens).
COMBINED_HARD_BYTES = 28000


@dataclass
class Result:
    path: str
    kind: str
    exists: bool
    bytes: int
    lines: int
    max_bytes: int
    max_lines: int
    over_bytes: bool
    over_lines: bool
    note: str

    @property
    def over(self) -> bool:
        return self.over_bytes or self.over_lines

    @property
    def status(self) -> str:
        if not self.exists:
            return "MISSING"
        if not self.over:
            return "OK"
        return "OVER-HARD" if self.kind == "hard" else "OVER-soft"


def measure(budget: Budget, root: Path) -> Result:
    fp = root / budget.path
    if not fp.is_file():
        return Result(budget.path, budget.kind, False, 0, 0,
                      budget.max_bytes, budget.max_lines, False, False, budget.note)
    data = fp.read_bytes()
    nbytes = len(data)
    nlines = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)
    return Result(
        budget.path, budget.kind, True, nbytes, nlines,
        budget.max_bytes, budget.max_lines,
        nbytes > budget.max_bytes, nlines > budget.max_lines, budget.note,
    )


IMPORT_RE = re.compile(r"^@([A-Za-z0-9_./-]+\.md)\s*$", re.MULTILINE)


def imported_files(root: Path, seeds: list[str]) -> list[str]:
    """Every `@file.md` reachable from the seeds, transitively.

    Claude Code loads `@import` targets into the same always-loaded context as
    the file importing them, so a budget that measures only the seeds is
    trivially evaded: move the bulk into `@HUGE.md` and the ceiling never
    notices. Codex proved exactly that against this script on 2026-08-26 --
    a 1 MB import reported combined=14 and passed --strict.

    Cycles are handled by the seen-set; a missing target is simply not walked
    (its absence is reported by `measure`, which is where absence belongs).
    """
    seen: set[str] = set()
    order: list[str] = []
    queue = list(seeds)
    while queue:
        rel = queue.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        if rel not in seeds:
            order.append(rel)
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in IMPORT_RE.finditer(text):
            target = match.group(1).strip()
            if target and target not in seen:
                queue.append(target)
    return order


def run(root: Path) -> tuple[list[Result], int, bool]:
    results = [measure(b, root) for b in CONFIG]

    # Anything reachable by @import is always-loaded too, so it counts toward
    # the combined ceiling even though it has no budget line of its own.
    seeds = [b.path for b in CONFIG]
    extra_bytes = 0
    extra: list[str] = []
    for rel in imported_files(root, seeds):
        path = root / rel
        try:
            extra_bytes += len(path.read_bytes())
            extra.append(rel)
        except OSError:
            continue

    combined = sum(r.bytes for r in results if r.exists) + extra_bytes

    # A configured always-loaded file that has VANISHED is a violation, not a
    # quiet pass. Deleting AGENTS.md must never be the cheapest way to satisfy
    # its own budget.
    missing = [r.path for r in results if not r.exists]

    hard_busted = (
        any(r.kind == "hard" and r.over for r in results)
        or combined > COMBINED_HARD_BYTES
        or bool(missing)
    )
    return results, combined, hard_busted, extra, missing


def _fmt_table(results: list[Result], combined: int) -> str:
    rows = [
        f"{'file':<12} {'kind':<5} {'lines':>6}/{'max':<5} {'bytes':>7}/{'max':<6} status",
        "-" * 62,
    ]
    for r in results:
        rows.append(
            f"{r.path:<12} {r.kind:<5} {r.lines:>6}/{r.max_lines:<5} "
            f"{r.bytes:>7}/{r.max_bytes:<6} {r.status}"
        )
    rows.append("-" * 62)
    combined_flag = "  (!) OVER-HARD" if combined > COMBINED_HARD_BYTES else ""
    rows.append(
        f"{'COMBINED':<12} {'hard':<5} {'':>6} {'':<5} "
        f"{combined:>7}/{COMBINED_HARD_BYTES:<6} always-loaded{combined_flag}"
    )
    for r in results:
        if r.over:
            rows.append(f"  - {r.path}: {r.note}")
    return "\n".join(rows)


def _fmt_extras(imported: list[str], missing: list[str]) -> str:
    lines: list[str] = []
    if imported:
        lines.append("  @imports counted toward COMBINED: " + ", ".join(imported))
    for path in missing:
        lines.append(f"  - {path}: MISSING -- a configured always-loaded file is gone")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Guard the always-loaded agent-context budget.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 2 if a HARD budget is exceeded (for CI / PostToolUse hook).")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    ap.add_argument("--root", default=str(REPO_ROOT), help="Repo root to scan.")
    args = ap.parse_args(argv)

    results, combined, hard_busted, imported, missing = run(Path(args.root))

    if args.json:
        print(json.dumps({
            "results": [asdict(r) | {"status": r.status} for r in results],
            "combined_bytes": combined,
            "combined_hard_bytes": COMBINED_HARD_BYTES,
            "imported": imported,
            "missing": missing,
            "hard_busted": hard_busted,
        }, indent=2))
    else:
        print(_fmt_table(results, combined))
        extras = _fmt_extras(imported, missing)
        if extras:
            print(extras)
        if hard_busted:
            print("\nHARD budget exceeded -- a file is over the ceiling it declares for itself.")
        soft_over = [r.path for r in results if r.over and r.kind == "soft"]
        if soft_over:
            print(f"\nSoft target exceeded (advisory): {', '.join(soft_over)} -- "
                  "consider moving content to a pointer-loaded file or a skill.")

    if args.strict and hard_busted:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
