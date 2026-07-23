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

Two enforcement modes:
  * ABSOLUTE  — `--strict` alone: exit 2 if any HARD budget is busted, full stop.
  * RATCHET   — `--strict --baseline <json>`: exit 2 only if a HARD breach is NEW
                (a file crossed its ceiling in this change) or WORSE (a file that
                was already over grew further). A pre-existing breach that is
                unchanged or shrinking is reported as WAIVED and does not fail.

Why the ratchet exists: on 2026-07-22 STATUS.md sat at 7485 bytes against its own
declared 4096-byte ceiling, and 16 open PRs touched it. An absolute gate would
have gone red on every one of them — and a check that is red no matter what you
do is a check people route around, which is how this guard ended up unwired in
the first place. The ratchet is red the moment *your* change makes the
always-loaded set worse, green otherwise, and the only way to earn permission to
grow a file is to first bring it under its ceiling. The ceilings themselves are
never relaxed to make a run pass.

Usage:
  python scripts/check_context_budget.py            # report table, exit 0
  python scripts/check_context_budget.py --strict    # exit 2 if a HARD budget is busted
  python scripts/check_context_budget.py --json       # machine-readable
  python scripts/check_context_budget.py --list-paths # one budgeted path per line
  python scripts/check_context_budget.py --strict --baseline base.json   # ratchet
"""

from __future__ import annotations

import argparse
import json
import sys
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


@dataclass
class Delta:
    """How one budgeted file moved between a baseline and the current tree."""

    path: str
    kind: str
    base_bytes: int
    base_lines: int
    base_over: bool
    now_bytes: int
    now_lines: int
    now_over: bool

    @property
    def grew(self) -> bool:
        return self.now_bytes > self.base_bytes or self.now_lines > self.base_lines

    @property
    def newly_over(self) -> bool:
        """This change pushed a compliant file past its ceiling."""
        return self.now_over and not self.base_over

    @property
    def worsened(self) -> bool:
        """Already over its ceiling, and this change made it bigger."""
        return self.now_over and self.base_over and self.grew

    @property
    def regressed(self) -> bool:
        return self.newly_over or self.worsened

    @property
    def waived(self) -> bool:
        """Over budget, but not this change's doing — pre-existing debt."""
        return self.now_over and self.base_over and not self.grew

    @property
    def verdict(self) -> str:
        if self.newly_over:
            return "REGRESSED-new"
        if self.worsened:
            return "REGRESSED-worse"
        if self.waived:
            return "waived-preexisting"
        if self.now_over:
            return "OVER"
        return "ok"


def load_baseline(path: Path) -> dict[str, dict]:
    """Read a prior `--json` snapshot, keyed by file path.

    Only `bytes`, `lines` and over-flags are consumed, so an older snapshot
    that lacks newer fields still works.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {r["path"]: r for r in payload.get("results", [])}


def diff_against_baseline(
    results: list[Result], baseline: dict[str, dict]
) -> list[Delta]:
    """Compare current measurements to a baseline snapshot.

    A budgeted file absent from the baseline is treated as newly introduced
    (0 bytes, not over), so adding an already-over-budget always-loaded file
    counts as a regression rather than sliding in unmeasured.
    """
    deltas = []
    for r in results:
        base = baseline.get(r.path)
        if base is None:
            base_bytes, base_lines, base_over = 0, 0, False
        else:
            base_bytes = int(base.get("bytes", 0))
            base_lines = int(base.get("lines", 0))
            base_over = bool(base.get("over_bytes")) or bool(base.get("over_lines"))
        deltas.append(
            Delta(
                path=r.path,
                kind=r.kind,
                base_bytes=base_bytes,
                base_lines=base_lines,
                base_over=base_over,
                now_bytes=r.bytes,
                now_lines=r.lines,
                now_over=r.over,
            )
        )
    return deltas


def config_integrity(results: list[Result], baseline: dict[str, dict]) -> list[str]:
    """Detect loosening of the *gate* rather than of the *content*.

    The ceilings live in this file's CONFIG, so without this check a PR could
    raise `max_bytes`, flip STATUS.md from HARD to SOFT, or delete its entry
    outright, and the ratchet would report green on a strictly worse tree. Those
    are gate edits masquerading as compliance — they fail closed.

    This only works because the baseline is generated by the BASE ref's copy of
    this script (see .github/workflows/context-budget.yml), so `max_bytes` in the
    snapshot is the ceiling as it stood before the PR. Raising a ceiling remains
    possible on purpose; it just cannot be done by the same PR that benefits.
    """
    now = {r.path: r for r in results}
    problems: list[str] = []
    for path, base in sorted(baseline.items()):
        cur = now.get(path)
        if cur is None:
            problems.append(
                f"{path}: dropped from CONFIG (was {base.get('kind', '?')}-budgeted) "
                "-- the file stops being measured entirely"
            )
            continue
        if base.get("kind") == "hard" and cur.kind != "hard":
            problems.append(
                f"{path}: HARD budget downgraded to {cur.kind} -- a self-declared "
                "ceiling is not a judgement call"
            )
        base_max_bytes = int(base.get("max_bytes", cur.max_bytes))
        if cur.max_bytes > base_max_bytes:
            problems.append(
                f"{path}: byte ceiling raised {base_max_bytes} -> {cur.max_bytes}"
            )
        base_max_lines = int(base.get("max_lines", cur.max_lines))
        if cur.max_lines > base_max_lines:
            problems.append(
                f"{path}: line ceiling raised {base_max_lines} -> {cur.max_lines}"
            )
    return problems


def hard_regressions(deltas: list[Delta]) -> list[Delta]:
    """Only HARD-class regressions are failable.

    SOFT ceilings are explicitly a host call (see the module docstring), so a
    soft-class regression is surfaced as a warning and never fails a run — the
    same stance the non-baseline path already takes.
    """
    return [d for d in deltas if d.kind == "hard" and d.regressed]


def _fmt_deltas(deltas: list[Delta]) -> str:
    rows = [
        "",
        f"{'file':<12} {'kind':<5} {'base bytes':>11} {'now bytes':>10} "
        f"{'delta':>8}  verdict",
        "-" * 62,
    ]
    for d in deltas:
        change = d.now_bytes - d.base_bytes
        rows.append(
            f"{d.path:<12} {d.kind:<5} {d.base_bytes:>11} {d.now_bytes:>10} "
            f"{change:>+8}  {d.verdict}"
        )
    return "\n".join(rows)


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
    ap.add_argument("--list-paths", action="store_true",
                    help="Print one budgeted path per line and exit (for baseline builders).")
    ap.add_argument("--baseline", metavar="JSON",
                    help="A prior --json snapshot. Switches --strict to RATCHET mode: "
                         "fail only on a HARD breach that is new or worse than the baseline.")
    args = ap.parse_args(argv)

    if args.list_paths:
        # LF-only, deliberately. This feeds a `while read` loop in
        # .github/workflows/context-budget.yml; on Windows `print()` emits CRLF
        # and the trailing \r becomes part of the path, so every `git show
        # <sha>:<path>\r` misses and the baseline silently reads as all-zeros —
        # which makes every file look newly-over-budget. Caught by dry-running
        # the workflow logic on Windows 2026-07-22.
        try:
            sys.stdout.reconfigure(newline="\n")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass  # pytest's capsys stream isn't reconfigurable; harmless there.
        sys.stdout.write("".join(f"{b.path}\n" for b in CONFIG))
        return 0

    results, combined, hard_busted = run(Path(args.root))

    deltas: list[Delta] = []
    regressions: list[Delta] = []
    loosened: list[str] = []
    if args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_file():
            # Fail loudly: a missing baseline silently downgrading the ratchet to
            # "always green" is exactly the wired-to-nothing failure this guards.
            print(f"ERROR: --baseline file not found: {baseline_path}", file=sys.stderr)
            return 2
        baseline = load_baseline(baseline_path)
        deltas = diff_against_baseline(results, baseline)
        regressions = hard_regressions(deltas)
        loosened = config_integrity(results, baseline)

    if args.json:
        print(json.dumps({
            "results": [asdict(r) | {"status": r.status} for r in results],
            "combined_bytes": combined,
            "combined_soft_bytes": COMBINED_SOFT_BYTES,
            "hard_busted": hard_busted,
            "deltas": [asdict(d) | {"verdict": d.verdict} for d in deltas],
            "hard_regressions": [d.path for d in regressions],
            "config_loosened": loosened,
        }, indent=2))
    else:
        print(_fmt_table(results, combined))
        if hard_busted:
            print("\nHARD budget exceeded -- a file is over the ceiling it declares for itself.")
        soft_over = [r.path for r in results if r.over and r.kind == "soft"]
        if soft_over:
            print(f"\nSoft target exceeded (advisory): {', '.join(soft_over)} -- "
                  "consider moving content to a pointer-loaded file or a skill.")
        if args.baseline:
            print(_fmt_deltas(deltas))
            soft_grew = [d.path for d in deltas
                         if d.kind == "soft" and d.now_over and d.grew]
            if soft_grew:
                print(f"\nSoft target grew (advisory, does not fail): {', '.join(soft_grew)}")
            if regressions:
                print("\nRATCHET FAILED -- this change makes the always-loaded set worse:")
                for d in regressions:
                    why = ("crossed its ceiling" if d.newly_over
                           else "was already over and grew further")
                    budget = next(b for b in CONFIG if b.path == d.path)
                    print(f"  - {d.path}: {why} "
                          f"({d.base_bytes} -> {d.now_bytes} bytes, "
                          f"{d.base_lines} -> {d.now_lines} lines; "
                          f"ceiling {budget.max_bytes} bytes / {budget.max_lines} lines)")
                print("\nTrim the file, or move content to a pointer-loaded doc or skill. "
                      "Do NOT raise the ceiling in CONFIG to make this pass.")
            if loosened:
                print("\nGATE LOOSENED -- this change relaxes the budget definition itself:")
                for problem in loosened:
                    print(f"  - {problem}")
                print("\nA ceiling change is a host decision and belongs in its own PR "
                      "(and in ADR-002), not in the change that benefits from it.")
            if not regressions and not loosened:
                waived = [d.path for d in deltas if d.waived]
                print("\nRatchet OK -- no HARD budget got new or worse in this change.")
                if waived:
                    # Never let a green ratchet read as absolute compliance.
                    print(f"NOTE: still OVER budget (pre-existing, waived): {', '.join(waived)}. "
                          "Green here means 'not made worse', NOT 'within budget'.")

    if args.strict:
        # With a baseline the ratchet is authoritative: pre-existing debt is
        # waived, only new/worse breaches fail. Without one, absolute semantics.
        if args.baseline:
            return 2 if (regressions or loosened) else 0
        if hard_busted:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
