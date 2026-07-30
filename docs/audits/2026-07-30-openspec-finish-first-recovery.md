# OpenSpec finish-first recovery map

Freshness: 2026-07-30 10:54 PDT, Windows, `origin/main`
`3b3b0a0991159c71a297b1f8fe841d36a3605c6c`.

## Result

There is no safe archive-only delivery to admit. The canonical audit reports
0 complete-unarchived changes, 18 untracked changes, 29 oversized changes, and
one delivery-WIP owner. That owner is `codex-cloud-drain-20260730` on
`harden-background-branch-execution-authority`; this lane did not edit or retire
that claim.

The current queue is therefore constrained by active ownership and explicit
dependency gates, not by hidden complete-but-unarchived debt. A replacement
worker should resume the exact current owner before selecting another change.
After that claim retires, it must rerun `claim_check.py` and
`openspec_flow.py audit`; this report is evidence, not admission authority.

## Bounded finish-first map

| Order | Change | Current evidence | Safe next action |
|---|---|---|---|
| 1 | `harden-background-branch-execution-authority` | 2/77 tasks; exact live owner `codex-cloud-drain-20260730`; PR #1918 merged at `3b3b0a09` | Current owner folds back task 1.3, then the controller rechecks admission. Do not steal the claim. |
| 2 | `test-identity-and-reset` | 6/9 tasks; STATUS requires healthy public `/mcp`, production fingerprint key, two test identities, and rendered sessions | Keep blocked until those host/runtime proofs exist. |
| 3 | `reconcile-universe-personification-relay` | 28/33 tasks; STATUS deliberately leaves 6.4/6.5/6.9/6.10 unchecked | Keep blocked on outbound speaking, non-founder conversation, design, and connector evidence. |
| 4 | `harden-branch-access-authority` | 31/41 tasks; implementation row depends on test identity and retire-legacy 4.2/4.4 | Recheck only after those named dependencies land. |

All four changes have complete planning artifacts according to
`openspec status --change <name> --json`. In that command, `isComplete: true`
means the proposal/design/spec/tasks artifacts exist; it does not mean their
implementation task checkboxes are complete.

## Evidence

- `python scripts/claim_check.py --provider
  drain-20260730-104801-7e8f53 --json` before claim: `claimable=0`, `stale=0`,
  and no row owned by this identity.
- `python scripts/openspec_flow.py audit`: 33 active changes, 360 completed
  tasks, 831 remaining tasks, one delivery WIP, and 0 complete-unarchived.
- `openspec list --json`: confirmed the active-change task counts.
- `openspec status --change <name> --json`: confirmed repo-local planning
  roots and complete planning artifacts for the four mapped changes.
- `gh pr view 1918`: merged 2026-07-30 at
  `3b3b0a0991159c71a297b1f8fe841d36a3605c6c`.
- `gh pr view 1924`: merged 2026-07-30 at
  `0462315031195916f848b6cd0388c99a944ea828`; its prior blocker-refresh work
  is already present on current main and was not repeated here.
- `PLAN.md`, Module: Harness & Coordination: STATUS claims and the
  GitHub/worktree spine remain the admission authority.

## Scope boundary

This recovery slice changes coordination evidence only. It does not modify
OpenSpec task state, product code, production state, dependency labels, or any
other provider's claim.
