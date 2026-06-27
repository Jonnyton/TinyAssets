"""Unified runner for TinyAssets invariants.

Loads every invariant registered in `scripts/invariants/` and drives
them through three operating modes:

    --list             Show registered invariants + their scope.
    --check-all        Run every invariant's check() once; exit 0 if
                       all pass or skip, 1 if any VIOLATED.
    --check NAME       Run a single invariant by name.
    --pre-commit       Run only invariants with pre_commit_scope=True.
                       Used by .git/hooks/pre-commit as the authoritative
                       invariant gate (supersedes ad-hoc checks).
    --continuous       Run every invariant with poll_interval_s > 0 in
                       a daemon loop. Auto-heal on violation when the
                       invariant allows it; log otherwise.
    --heal-all         One-shot: run every invariant with auto_heal=True
                       and trigger heal() unconditionally. For manual
                       recovery runs.

Output is line-oriented so logs, trays, and CI all parse it the same.
Exit code 0 on all-pass, 1 on any violation (or any --check run that
VIOLATED). Continuous mode doesn't exit unless interrupted.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
# Ensure the `scripts.` package imports work when run as a script.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.invariants import Invariant, Status  # noqa: E402
from scripts.invariants.concerns_staleness import (  # noqa: E402
    ConcernsStalenessInvariant,
)
from scripts.invariants.context_budget import (  # noqa: E402
    ContextBudgetInvariant,
)
from scripts.invariants.cross_provider_drift import (  # noqa: E402
    CrossProviderDriftInvariant,
)
from scripts.invariants.mirror_parity import MirrorParityInvariant  # noqa: E402
from scripts.invariants.mojibake import MojibakeInvariant  # noqa: E402
from scripts.invariants.skills_valid import SkillsValidInvariant  # noqa: E402
from scripts.invariants.tab_single import TabSingleInvariant  # noqa: E402


def _all_invariants() -> list[Invariant]:
    return [
        CrossProviderDriftInvariant(),
        MirrorParityInvariant(),
        MojibakeInvariant(),
        SkillsValidInvariant(),
        TabSingleInvariant(),
        ConcernsStalenessInvariant(),
        ContextBudgetInvariant(),
    ]


def _by_name(name: str) -> Invariant | None:
    for inv in _all_invariants():
        if inv.name == name:
            return inv
    return None


def _format_check(inv: Invariant, result) -> str:
    tag = {
        Status.OK: "OK      ",
        Status.VIOLATED: "VIOLATED",
        Status.SKIPPED: "SKIPPED ",
    }[result.status]
    return f"[{tag}] {inv.name:20s} {result.duration_seconds:6.2f}s {result.message}"


def cmd_list() -> int:
    for inv in _all_invariants():
        scope_tags = []
        if inv.pre_commit_scope:
            scope_tags.append("pre-commit")
        if inv.poll_interval_s is not None:
            scope_tags.append(f"poll={inv.poll_interval_s}s")
        if not scope_tags:
            scope_tags.append("on-demand")
        heal_tag = "auto-heal" if inv.auto_heal else "propose-only"
        print(
            f"{inv.name:20s} {heal_tag:14s} "
            f"[{', '.join(scope_tags)}]  {inv.description}"
        )
    return 0


def cmd_check_all(invariants: Iterable[Invariant] | None = None) -> int:
    invs = list(invariants) if invariants is not None else _all_invariants()
    any_violated = False
    for inv in invs:
        result = inv.check()
        print(_format_check(inv, result))
        if result.status == Status.VIOLATED:
            any_violated = True
            if result.evidence:
                for k, v in result.evidence.items():
                    if isinstance(v, list) and len(v) > 10:
                        preview = v[:5] + [f"...(+{len(v)-5} more)"]
                    else:
                        preview = v
                    print(f"  evidence.{k}: {preview}")
    return 1 if any_violated else 0


def cmd_check(name: str) -> int:
    inv = _by_name(name)
    if inv is None:
        print(f"ERROR: no invariant named {name!r}", file=sys.stderr)
        print("Available:", ", ".join(i.name for i in _all_invariants()), file=sys.stderr)
        return 2
    return cmd_check_all([inv])


def cmd_pre_commit() -> int:
    invs = [inv for inv in _all_invariants() if inv.pre_commit_scope]
    return cmd_check_all(invs)


def cmd_heal_all() -> int:
    any_failure = False
    for inv in _all_invariants():
        if not inv.auto_heal:
            print(f"[skip    ] {inv.name:20s} auto_heal disabled")
            continue
        check_result = inv.check()
        if check_result.status != Status.VIOLATED:
            print(f"[no-op   ] {inv.name:20s} {check_result.status.value}")
            continue
        heal_result = inv.heal()
        tag = "healed  " if heal_result.healed else "FAILED  "
        print(f"[{tag}] {inv.name:20s} {heal_result.message}")
        if not heal_result.healed:
            any_failure = True
    return 1 if any_failure else 0


def cmd_continuous() -> int:
    """Poll loop. Invariants with poll_interval_s > 0 each track their own
    next-run monotonic timestamp; the loop sleeps to the earliest upcoming
    tick. Ctrl-C exits cleanly."""
    scheduled = [inv for inv in _all_invariants() if inv.poll_interval_s]
    if not scheduled:
        print("No continuous-scope invariants registered; exiting.", file=sys.stderr)
        return 0
    print(f"Starting continuous invariants: {[i.name for i in scheduled]}")
    next_run: dict[str, float] = {inv.name: 0.0 for inv in scheduled}
    try:
        while True:
            now = time.monotonic()
            next_wait = min(
                max(0.0, next_run[inv.name] - now) for inv in scheduled
            )
            if next_wait > 0:
                time.sleep(next_wait)
            now = time.monotonic()
            for inv in scheduled:
                if next_run[inv.name] > now:
                    continue
                result = inv.check()
                if result.status == Status.VIOLATED:
                    print(_format_check(inv, result), flush=True)
                    if inv.auto_heal:
                        heal_result = inv.heal()
                        print(
                            f"  heal: {'OK' if heal_result.healed else 'FAILED'} "
                            f"{heal_result.message}",
                            flush=True,
                        )
                next_run[inv.name] = (
                    time.monotonic() + (inv.poll_interval_s or 0)
                )
    except KeyboardInterrupt:
        print("\ninvariants runner interrupted; exiting.", flush=True)
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run TinyAssets invariants.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="List registered invariants.")
    mode.add_argument("--check-all", action="store_true", help="Run every check() once.")
    mode.add_argument("--check", metavar="NAME", help="Run a single invariant.")
    mode.add_argument(
        "--pre-commit",
        action="store_true",
        help="Run only pre-commit-scope invariants (hook mode).",
    )
    mode.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuous-scope invariants in a daemon loop.",
    )
    mode.add_argument(
        "--heal-all",
        action="store_true",
        help="One-shot: heal every violated, auto-healable invariant.",
    )
    args = parser.parse_args(argv)

    if args.list:
        return cmd_list()
    if args.check_all:
        return cmd_check_all()
    if args.check:
        return cmd_check(args.check)
    if args.pre_commit:
        return cmd_pre_commit()
    if args.continuous:
        return cmd_continuous()
    if args.heal_all:
        return cmd_heal_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
