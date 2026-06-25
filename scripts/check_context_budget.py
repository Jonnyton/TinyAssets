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
  * HARD  — the file declares its own ceiling (STATUS.md says "4 KB / 60 lines").
            Enforcing a file's own stated contract is not a judgement call, so
            `--strict` exits 2 when a HARD budget is exceeded.
  * SOFT  — an advisory target (AGENTS.md / CLAUDE.md). The exact ceiling is a
            host call, so SOFT overages only WARN, never fail — even under
            --strict. Tune the numbers in CONFIG below; the point is that drift
            becomes visible in a PR/hook instead of silent.

Usage:
  python scripts/check_context_budget.py            # report table, exit 0
  python scripts/check_context_budget.py --strict    # exit 2 if a HARD budget is busted
  python scripts/check_context_budget.py --json       # machine-readable
"""

from __future__ import annotations

import argparse
import json
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


# Always-loaded set: CLAUDE.md imports @AGENTS.md + @STATUS.md, so all three
# load every session. PLAN.md is intentionally NOT imported (pointer-loaded),
# so it is not budgeted here.
CONFIG: tuple[Budget, ...] = (
    Budget("STATUS.md", "hard", 4096, 60,
           "File declares its own 4 KB / 60-line budget in its header."),
    Budget("AGENTS.md", "soft", 30000, 450,
           "Cross-provider canonical; soft target -- was ~17.6 KB on 2026-04-28."),
    Budget("CLAUDE.md", "soft", 12000, 200,
           "Claude Code router; should stay a thin pointer layer."),
)

# Soft ceiling for the combined always-loaded payload (~10K tokens ≈ 40 KB).
COMBINED_SOFT_BYTES = 40000


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


def run(root: Path) -> tuple[list[Result], int, bool]:
    results = [measure(b, root) for b in CONFIG]
    combined = sum(r.bytes for r in results if r.exists)
    hard_busted = any(r.kind == "hard" and r.over for r in results)
    return results, combined, hard_busted


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
    combined_flag = "  (!) over soft" if combined > COMBINED_SOFT_BYTES else ""
    rows.append(
        f"{'COMBINED':<12} {'soft':<5} {'':>6} {'':<5} "
        f"{combined:>7}/{COMBINED_SOFT_BYTES:<6} always-loaded{combined_flag}"
    )
    for r in results:
        if r.over:
            rows.append(f"  - {r.path}: {r.note}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Guard the always-loaded agent-context budget.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 2 if a HARD budget is exceeded (for CI / PostToolUse hook).")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    ap.add_argument("--root", default=str(REPO_ROOT), help="Repo root to scan.")
    args = ap.parse_args(argv)

    results, combined, hard_busted = run(Path(args.root))

    if args.json:
        print(json.dumps({
            "results": [asdict(r) | {"status": r.status} for r in results],
            "combined_bytes": combined,
            "combined_soft_bytes": COMBINED_SOFT_BYTES,
            "hard_busted": hard_busted,
        }, indent=2))
    else:
        print(_fmt_table(results, combined))
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
