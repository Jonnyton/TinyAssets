# OpenSpec drain blocker freshness audit

Date: 2026-07-30 America/Los_Angeles
Provider: `drain-20260730-095018-67aecc`
Base: `origin/main` at `d02589134d9e89b75bd90f83715d0b1f447e8961`

## Scope

Freshness-check every blocked OpenSpec delivery row against current-main
coordination state, GitHub pull requests, OpenSpec progress, and registered
worktrees. Remove only dependency labels disproved by current evidence. A
merged proposal, partial implementation, or recovery does not satisfy a
separately named runtime, deployment, host, review, or acceptance gate.

## Evidence

- Before this lane was claimed, exact
  `claim_check.py --provider drain-20260730-095018-67aecc --status-ref
  origin/main --json` reported `claimable=0`, `in_flight=0`, and `stale=0`.
  Therefore ten dependency phrases requiring release of broad test/runtime
  claims were contradicted by the canonical current-main claim surface.
- `openspec_flow.py audit` at this base reported 33 active changes, 359
  completed tasks, 832 remaining tasks, and no delivery WIP. The finish-first
  changes named by STATUS remain incomplete: test identity 6/9, relay 28/33,
  branch access 31/41, build-forward 5/19, provider receipts 1/15, universe
  creation 11/32, retire legacy 2/27, public read 5/35, retire cheat 9/39,
  connector manifests 18/49, PostgreSQL 7/43, secret custody 5/42,
  demand-side 0/49, plan-gated targets 8/58, and background authority 1/77.
- GitHub still reports #1792 and #1819 as open drafts. Merged #1753 and #1784
  are qualified in STATUS by their remaining runtime or handoff work, so those
  labels remain valid. Draft #1918 confirms the dark background-authority core
  has not landed.
- Current main includes the #1843 recovery and the later #1900 blocker audit,
  while STATUS still records rendered/organic retirement proof, rollback,
  live-receipt, packaging, and sync/archive gates. No merged PR inspected
  discharges those surviving requirements.
- The 90-second global `worktree_status.py` diagnostic timed out on this
  Windows host. Per the drain contract, the audit continued only from this
  clean current-main worktree; exact claim, OpenSpec, provider-context, GitHub,
  and registered-worktree evidence remained mandatory.

## Correction

Removed ten obsolete cross-cutting qualifiers:

- seven `release broad tests claims` variants from branch/run/version,
  branch-adjacent/outcome, universe-integration, and migration rows;
- `outbound broad-test release` from background authority;
- `release active broad tests claims` from retire 4.2;
- `runtime/test claim release` from R2-1a.

Every row retains at least one independently verified substantive dependency,
so the correction does not create a claimable implementation lane. No product
code, OpenSpec task state, architecture, production state, or host gate changed.

## Test-first verification

The initial stale-qualifier scan failed before the edit, finding the obsolete
phrases. After the correction, the same scan must return no matches, the exact
claim check must report `claimable=0`, `in_flight=0`, and `stale=0`, and
`git diff --check` must pass.
