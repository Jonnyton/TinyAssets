"""Context-budget invariant: always-loaded instruction files stay within budget.

Wraps `scripts/check_context_budget.py` under the Invariant contract.

Propose-only and NOT pre-commit-scoped: the always-loaded set includes
host-managed files (STATUS.md, and the cross-provider canonical AGENTS.md),
so a budget bust surfaces drift for a human to curate — it must not block
commits. This mirrors the `concerns-staleness` stance exactly. The HARD
budget is a file's own declared ceiling (STATUS.md says "4 KB / 60 lines");
soft targets for AGENTS.md / CLAUDE.md are advisory. Basis:
`docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from . import CheckResult, Invariant, Status

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BUDGET_SCRIPT = REPO_ROOT / "scripts" / "check_context_budget.py"


def _load_budget_module():
    spec = importlib.util.spec_from_file_location(
        "check_context_budget_for_invariant", BUDGET_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class ContextBudgetInvariant(Invariant):
    name = "context-budget"
    description = "Always-loaded instruction files stay within their budgets."
    pre_commit_scope = False  # host-managed content; surface, don't block (cf. concerns-staleness)
    poll_interval_s = None  # on-demand
    auto_heal = False  # propose-only; splitting content is editorial

    def _check(self) -> CheckResult:
        if not BUDGET_SCRIPT.exists():
            return CheckResult(
                status=Status.SKIPPED,
                message=f"check_context_budget.py not found at {BUDGET_SCRIPT}",
            )
        mod = _load_budget_module()
        results, combined, hard_busted = mod.run(REPO_ROOT)
        hard_over = [r.path for r in results if r.kind == "hard" and r.over]
        soft_over = [r.path for r in results if r.kind == "soft" and r.over]
        evidence = {
            "combined_bytes": combined,
            "combined_soft_bytes": mod.COMBINED_SOFT_BYTES,
            "hard_over": hard_over,
            "soft_over": soft_over,
        }
        if hard_busted:
            return CheckResult(
                status=Status.VIOLATED,
                message=(
                    f"{', '.join(hard_over)} over declared HARD budget; "
                    f"always-loaded total {combined} bytes "
                    f"(soft over: {', '.join(soft_over) or 'none'}). "
                    f"Run: python scripts/check_context_budget.py"
                ),
                evidence=evidence,
            )
        msg = f"always-loaded {combined} bytes; no HARD budget exceeded"
        if soft_over:
            msg += f" (soft target over: {', '.join(soft_over)})"
        return CheckResult(status=Status.OK, message=msg, evidence=evidence)
