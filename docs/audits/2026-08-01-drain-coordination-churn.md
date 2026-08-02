# Drain coordination churn: 32 attempts, zero delivery slices

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

## Live recovery evidence

**Freshness:** 2026-08-01 16:54 PDT, Windows local drain identity
`drain-20260801-113628-6deab6`.

PR #2099 merged the corrective contract at `815776e5`. The watchdog restarted
the existing run on that merged controller without minting a new identity.
Attempt 33 selected `bind-host-principal-to-account`, inspected its unchecked
tasks, and merged reviewed refinery PR #2103. Fresh `origin/main` then reported
exactly one claimable row overlapping that change boundary. At 16:54:21 PDT,
attempt 34 admitted that row into isolated worktree
`wf-drain-20260801-113628-6deab6-refine-openspec-bind-host-princi-a034` and
dispatched a normal implementation worker. Watchdog health returned `running`.

This proves the corrected refinery-to-implementation admission path. It does
not yet claim that attempt 34 has completed a delivery slice; completion and
merge remain observable through the continuing drain run.

## Restart identity regression

**Freshness:** 2026-08-01 17:10 PDT, Windows local watchdog.

Attempt 34 subsequently merged bounded owner-gate tasks as PR #2106 while
preserving `resume_target=refine-openspec-bind-host-principal-to-account` and
the original admission worktree. The supervisor labeled the incomplete result
`partial-stalled`; an operator restart then ended the original run through
`status=stop-requested` but the watchdog unconditionally selected a fresh run.
It minted `drain-20260801-171005-f06196`, leaving the original identity's live
STATUS claim unavailable to the replacement.

The root cause was a watchdog branch that treated both an already-terminal
explicit restart and an orderly stop of a live supervisor as `Decision("new")`.
The corrected branch resumes the same run directory when the live supervisor's
final state is `stop-requested`, while retaining a new finite run for an
already-terminal fatal or failure-budget outcome. A paired regression proves
both sides. Live restoration of the original identity remains required before
the incident can be archived.

The `partial-stalled` state had a second cause: the accepted refinery handoff
from attempt 33 incremented the same consecutive-partial counter used for
ordinary implementation workers. Attempt 34's first bounded delivery partial
therefore appeared to be a second stalled implementation attempt. The corrected
state transition resets implementation-partial accounting after an accepted
refinery continuation; two actual consecutive normal-worker partials still
consume the finite failure budget. This prevents a productive refinery ->
bounded-delivery sequence from entering the 30-minute idle wait.

Exact-head review then found one remaining identity hole: orderly stop writes
`ended_at`, but resume did not remove it. A later reboot would therefore make
the watchdog ignore the otherwise running identity and mint another run. The
resume path now removes `ended_at` after identity/provider validation and
before its first `status=running` write. A test first reproduced the stale
timestamp after a simulated abrupt post-resume exit, then passed with the fix;
the existing same-directory watchdog discovery and graceful-restart tests also
remain green. Live restoration proof is still required before archive.

Exact-head re-review at `f0fc759c` found three narrower variants of the same
identity/progress failure: the cleared timestamp was not durable until after
interruptible GitHub recovery calls; two explicit-restart paths could still
override a discovered unfinished run; and accepted refinery `PARTIAL` receipts
were replayable and could reset the failure counter. Test-first hardening now
persists the unfinished state before recovery, retains restart intent until a
supervisor process is created, preserves unfinished discovery in every restart
branch, and consumes canonical receipts for both `MERGED` and `PARTIAL` results.
The seven new regressions and full 201-test controller/watchdog suite passed on
Windows on 2026-08-01. Exact-head review and live restoration remain required.
