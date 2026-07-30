# OpenSpec finish-first recovery map

Freshness: 2026-07-30 11:17 PDT, Windows, `origin/main`
`3df9b9d49eb2cd07bb8d0b01290a829899368b24`.

## Result

There is no safe archive-only delivery to admit. The canonical audit reports
0 complete-unarchived changes, 18 untracked changes, 29 oversized changes, and
one delivery-WIP owner. PR #1928 completed task 1.5 but its exact
`codex-cloud-drain-logical-keys-20260730` foldback claim remains in STATUS at
this snapshot.

The current queue is constrained first by that exact ownership, then by explicit
dependency gates—not by hidden complete-but-unarchived debt. A replacement
worker must resume that owner before selecting another change, then rerun
`claim_check.py` and `openspec_flow.py audit`; this report is evidence, not
admission authority.

## Bounded finish-first map

| Order | Change | Current evidence | Safe next action |
|---|---|---|---|
| 1 | `harden-background-branch-execution-authority` | 4/77 tasks; exact live foldback owner `codex-cloud-drain-logical-keys-20260730`; task 1.5 landed in PR #1928 | Resume and retire the exact owner before new admission. Do not steal the claim. |
| 2 | `test-identity-and-reset` | 6/9 tasks; STATUS requires healthy public `/mcp`, production fingerprint key, two test identities, and rendered sessions | Keep blocked until those host/runtime proofs exist. |
| 3 | `reconcile-universe-personification-relay` | 28/33 tasks; STATUS deliberately leaves 6.4/6.5/6.9/6.10 unchecked | Keep blocked on outbound speaking, non-founder conversation, design, and connector evidence. |
| 4 | `harden-branch-access-authority` | 31/41 tasks; implementation row depends on test identity and retire-legacy 4.2/4.4 | Recheck only after those named dependencies land. |

All four changes have complete planning artifacts according to
`openspec status --change <name> --json`. In that command, `isComplete: true`
means the proposal/design/spec/tasks artifacts exist; it does not mean their
implementation task checkboxes are complete.

## Evidence

- `python scripts/claim_check.py --provider
  drain-20260730-104801-7e8f53 --json` after PR #1928: `claimable=0`,
  `stale=0`, and one in-flight row owned by
  `codex-cloud-drain-logical-keys-20260730`.
- `python scripts/openspec_flow.py audit`: 33 active changes, 362 completed
  tasks, 829 remaining tasks, one delivery WIP, and 0 complete-unarchived.
- `openspec list --json`: confirmed the active-change task counts.
- `openspec status --change <name> --json`: confirmed repo-local planning
  roots and complete planning artifacts for the four mapped changes.
- `gh pr view 1918`: merged 2026-07-30 at
  `3b3b0a0991159c71a297b1f8fe841d36a3605c6c`.
- `gh pr view 1924`: merged 2026-07-30 at
  `0462315031195916f848b6cd0388c99a944ea828`; its prior blocker-refresh work
  is already present on current main and was not repeated here.
- `origin/main` commit `d59a6e14` / PR #1925 advanced the dark store contract
  to task 1.4; `af6315bf` / PR #1926 retired it; `3df9b9d4` / PR #1928 landed
  task 1.5 and left its exact foldback claim visible.
- `PLAN.md`, Module: Harness & Coordination: STATUS claims and the
  GitHub/worktree spine remain the admission authority.

## Scope boundary

This recovery slice changes coordination evidence only. It does not modify
OpenSpec task state, product code, production state, dependency labels, or any
other provider's claim.
