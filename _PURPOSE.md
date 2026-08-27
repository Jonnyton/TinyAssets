# Active lane: safe stale-fleet reconciler Slice 1

- Purpose: build only the on-demand, dry-run-default stale epoch-2 task and cloud-worker runtime reconciler from `.fleet_plan.txt` §3.
- Provider/session: `codex-fleet-slice1`.
- Branch: `claude/fleet-slice1-reconciler`.
- Base ref: `origin/main` at `2edecdd2`.
- Worktree: `C:/Users/Jonathan/Projects/wf-fleet-slice1`.
- STATUS row: `Build safe stale-fleet reconciler Slice 1`.
- OpenSpec: `openspec/changes/reconcile-stale-retired-fleet-artifacts/`.
- PLAN refs: `Module: Daemon Platform`.
- Memory refs: `.fleet_plan.txt`, especially §3 and Slice 1/4 boundaries.
- Related implications: epoch-2 task integrity, retired cloud-executor classification, runtime claim/lease ownership, existing cancellation/retirement lifecycle events.
- Ship condition: requested focused tests and Ruff pass; plugin mirror rebuilt; independent diff review has no blocking findings.
- Abandon condition: current storage/lifecycle invariants cannot support an all-or-nothing guarded apply without changing execution, scheduling, compose, or background authority.
- Pickup hints: never run against real data; no SQL DELETE; default to dry-run; reuse `request_v2_cancel` and `retire_runtime_instance`.
- PR expectation: no commit, push, PR, deploy, or production apply per host instruction.

## Idea feed refs

- None; incidental findings stay outside this slice.
