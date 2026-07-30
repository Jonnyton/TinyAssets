# OpenSpec finish-first recovery map

Freshness: 2026-07-30 11:03 PDT, Windows, `origin/main`
`af6315bf16a4818b2814b3df081eade2d55d0b7b`.

## Result

There is no safe archive-only delivery to admit. The canonical audit reports
0 complete-unarchived changes, 18 untracked changes, 29 oversized changes,
`Delivery WIP: 0`, and `Provider WIP: none`. PR #1926 retired the task 1.4
store-contract claim before this freshness pass.

The current queue is therefore constrained by explicit dependency gates, not by
active ownership or hidden complete-but-unarchived debt. The exact claim check
also reports `claimable=0`, `stale=0`, and no in-flight row. A replacement
worker must rerun `claim_check.py` and `openspec_flow.py audit`, freshness-check
blockers, and consider one safe promotion; this report is evidence, not
admission authority.

## Bounded finish-first map

| Order | Change | Current evidence | Safe next action |
|---|---|---|---|
| 1 | `test-identity-and-reset` | 6/9 tasks; STATUS requires healthy public `/mcp`, production fingerprint key, two test identities, and rendered sessions | Keep blocked until those host/runtime proofs exist. |
| 2 | `reconcile-universe-personification-relay` | 28/33 tasks; STATUS deliberately leaves 6.4/6.5/6.9/6.10 unchecked | Keep blocked on outbound speaking, non-founder conversation, design, and connector evidence. |
| 3 | `harden-branch-access-authority` | 31/41 tasks; implementation row depends on test identity and retire-legacy 4.2/4.4 | Recheck only after those named dependencies land. |
| 4 | `build-forward-platform-capabilities` | 5/19 tasks; STATUS routes implementation through gated successor rows rather than the umbrella | Select only a concrete successor slice after its named gate clears. |

All four changes have complete planning artifacts according to
`openspec status --change <name> --json`. In that command, `isComplete: true`
means the proposal/design/spec/tasks artifacts exist; it does not mean their
implementation task checkboxes are complete.

## Evidence

- `python scripts/claim_check.py --provider
  drain-20260730-104801-7e8f53 --json` before claim and after PR #1926:
  `claimable=0`, `stale=0`, and no in-flight row.
- `python scripts/openspec_flow.py audit`: 33 active changes, 361 completed
  tasks, 830 remaining tasks, zero delivery WIP, and 0 complete-unarchived.
- `openspec list --json`: confirmed the active-change task counts.
- `openspec status --change <name> --json`: confirmed repo-local planning
  roots and complete planning artifacts for the four mapped changes.
- `gh pr view 1918`: merged 2026-07-30 at
  `3b3b0a0991159c71a297b1f8fe841d36a3605c6c`.
- `gh pr view 1924`: merged 2026-07-30 at
  `0462315031195916f848b6cd0388c99a944ea828`; its prior blocker-refresh work
  is already present on current main and was not repeated here.
- `origin/main` commit `d59a6e14` / PR #1925 advanced the dark store contract
  to task 1.4; commit `af6315bf` / PR #1926 then retired that exact claim.
- `PLAN.md`, Module: Harness & Coordination: STATUS claims and the
  GitHub/worktree spine remain the admission authority.

## Scope boundary

This recovery slice changes coordination evidence only. It does not modify
OpenSpec task state, product code, production state, dependency labels, or any
other provider's claim.
