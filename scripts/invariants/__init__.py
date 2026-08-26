"""Unified framework for zero-token mechanical invariants.

An invariant is a property of the repository / running system that
should always hold — canonical↔mirror byte-parity, exactly one Chrome
tab, STATUS.md Concerns kept fresh, no CP-1252 mojibake in tracked text.
Each is cheaper to enforce mechanically than to re-derive by hand each
session. See `CLAUDE_LEAD_OPS.md §Code Before Agents`.

## Contract

Every invariant subclasses `Invariant` and implements two methods:

    check() -> CheckResult
        Pure observation. Never mutates state. Returns a verdict:
          `Status.OK`      — invariant holds.
          `Status.VIOLATED` — invariant broken. `.message` explains.
          `Status.SKIPPED`  — precondition missing (e.g. no git repo);
                              not an error, just inapplicable.

    heal() -> HealResult
        Attempts repair. Invariants that are propose-only (e.g.
        concerns-staleness) override `auto_heal = False` and `heal()`
        becomes a no-op surfacing a human action. Default runner
        respects that flag.

## Lifecycle shape

- **Pre-commit invariants** (`pre_commit_scope = True`) run in the
  `.git/hooks/pre-commit` path. A single violation fails the commit.
- **Continuous invariants** (`poll_interval_s > 0`) poll in the
  background via `scripts/invariants_run.py --continuous`.
- **On-demand invariants** (`poll_interval_s = None`, `pre_commit_scope = False`)
  only run when an operator or cron explicitly invokes them.

Invariant classes must be pure-Python with zero third-party deps — the
framework is loaded from the pre-commit hook and the tray launcher on
a cold Python where heavy packages may not be available.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    OK = "ok"
    VIOLATED = "violated"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    status: Status
    message: str = ""
    evidence: dict = field(default_factory=dict)
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == Status.OK


@dataclass
class HealResult:
    healed: bool
    message: str = ""
    actions_taken: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class Invariant:
    """Base class for a repo/system invariant.

    Subclasses set class attributes to declare lifecycle + scope, and
    implement `_check` (plus `_heal` if auto-healable).

    Class attributes (subclass-configurable):
        name                — short id, e.g. "tab-single".
        description         — one-line purpose.
        pre_commit_scope    — run under .git/hooks/pre-commit if True.
        poll_interval_s     — poll cadence for continuous mode; None = on-demand only.
        auto_heal           — heal() is safe to auto-run? False means
                              propose-only (concerns-staleness).
    """

    name: str = "unnamed"
    description: str = ""
    pre_commit_scope: bool = False
    poll_interval_s: float | None = None
    auto_heal: bool = False

    def check(self) -> CheckResult:
        start = time.monotonic()
        try:
            result = self._check()
        except Exception as exc:
            # VIOLATED, not SKIPPED. A check that raises is a broken check, and
            # a broken check that reports "skipped" keeps --check-all green --
            # which is how a constant rename silently disarmed the
            # context-budget gate on 2026-08-25. SKIPPED is for a deliberate,
            # explicit skip (target absent, Chrome not running), never for a
            # crash. Fail loudly; see AGENTS.md Hard Rule 8.
            result = CheckResult(
                status=Status.VIOLATED,
                message=f"check raised {type(exc).__name__}: {exc}",
            )
        result.duration_seconds = time.monotonic() - start
        return result

    def heal(self) -> HealResult:
        start = time.monotonic()
        if not self.auto_heal:
            return HealResult(
                healed=False,
                message=(
                    f"{self.name}: auto_heal is disabled; invariant surfaces "
                    f"proposals but does not self-repair."
                ),
                duration_seconds=time.monotonic() - start,
            )
        try:
            result = self._heal()
        except Exception as exc:
            result = HealResult(
                healed=False,
                message=f"heal raised {type(exc).__name__}: {exc}",
            )
        result.duration_seconds = time.monotonic() - start
        return result

    # Subclass hooks — implement these, not the public wrappers.

    def _check(self) -> CheckResult:
        raise NotImplementedError

    def _heal(self) -> HealResult:
        raise NotImplementedError(
            f"{self.name}: auto_heal=True requires _heal() to be implemented"
        )


__all__ = ["Invariant", "CheckResult", "HealResult", "Status"]
