# Drain coordination churn: 24 attempts, zero delivery slices

**Freshness:** 2026-08-01, Windows local drain
`output/openspec-drain-auto-20260801-113628`, inspected from the detached
controller plus exact `origin/main` coordination state.

## Observed failure

At attempt 24, `state.json` reported:

- `status=running`
- `attempts=24`
- `completed_slices=0`
- `claimable=0`
- `refinable=41`

The watchdog and tray were process-green because the worker and controller were
alive. The supervisor log showed repeated refinery PRs and `BLOCKED` results,
not implementation delivery. Attempt 24's generated brief explicitly limited
the worker to coordination and prohibited product tests or implementation.

Exact-current-main `claim_check.py` classified 41 rows blocked and one row
in-flight (the separately claimed cloud-drain critical path). Several refinery
rows placed legacy-change size, final review, deployment, section-14 load,
rendered-chat, and organic-use evidence together in `Depends`. The checker
correctly interpreted that non-empty cell as "cannot start," even when those
gates occur after an earlier implementation slice.

## Root cause

The scheduler's safety model was not the defect: it correctly refused to steal
the cloud lane or bypass dependencies. The coordination producer violated the
row schema by describing whole-change completion instead of the exact next
slice. The refinery therefore increased blocker precision without opening a
claimable implementation lane. Because any refinable candidate counted as work,
the controller could stay active indefinitely while delivery throughput stayed
at zero.

## Corrective contract

1. A refinery row represents one next slice, at most 12 unchecked tasks and
   preferably fewer.
2. `Depends` lists only prerequisites that must land before that slice begins.
3. Downstream test/review/deploy/rendered/organic gates remain acceptance work,
   not current admission blockers.
4. If the direct slice is blocked, refinery searches for the shortest concrete
   autonomous prerequisite-removal slice before returning `BLOCKED`.
5. After a refinery `PARTIAL` PR merges, current main must contain claimable
   work overlapping the assigned change boundary. The controller rejects a
   continuation that only created more coordination.

This keeps the two-stage safety boundary: refinery still cannot edit product
code, and a fresh worker still receives an ordinary current-main claim before
implementation.

## Regression evidence

The focused tests cover both halves: generated briefs carry the immediate-slice
semantics, and a structural continuation validator accepts only a claimable row
with symmetric file-boundary overlap. The local controller must be restarted on
the merged main head and observed through the first refinery-to-implementation
handoff before the incident is considered operationally closed.
