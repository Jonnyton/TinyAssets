## Context

The drain currently asks `claim_check.py` for owned, claimable, and stale STATUS
rows. When all three counts are zero it dispatches a no-hint worker and later
accepts that worker's `NO_CANDIDATE` after repeating only the same narrow check.
The separate `openspec_flow.py audit` already proves whether active changes,
unchecked tasks, queued delivery, or untracked coordination debt remain, but
the controller never consumes that evidence. The worker brief also prohibits a
broad audit before claiming while requiring backlog promotion before idle, so a
no-hint worker has no deterministic authority-producing path.

In the 2026-07-31 incident, exact current main contained 37 active changes and
832 unchecked tasks. Thirty provider-owned Work rows were dependency-blocked,
19 changes were untracked, and one unrelated OAuth row was live. Ten consecutive
workers returned `NO_CANDIDATE` while the supervisor remained healthy but idle.

`STATUS.md` also appears in many Files cells even though editing the exact row is
required to claim and retire every lane. Treating that shared coordination file
as an ordinary whole-file collision atom can serialize otherwise disjoint work.

## Goals / Non-Goals

**Goals:**

- Make candidate exhaustion include exact-current-main OpenSpec flow evidence.
- Give a no-row worker one existing, bounded change to refine before idle.
- Preserve ordinary product-file collision, dependency, host, and review gates.
- Make STATUS row lifecycle edits row-scoped rather than a global write lock.
- Keep the selection path finite, deterministic, stdlib-only, and observable.

**Non-Goals:**

- Automatically implement an untracked or blocked change.
- Bypass host actions, live claims, design approval, or independent review.
- Introduce dependency-wave scheduling for product execution.
- Change public MCP behavior or the cloud activation/claim authority.

## Decisions

### 1. Inspect OpenSpec flow from the same exact Git ref as STATUS

`openspec_flow.py audit` gains a read-only ref mode. It reads `STATUS.md` and
active change artifacts from one validated Git tree snapshot rather than the
controller's detached working tree. The supervisor fetches origin once, then
uses `origin/main` for both claim and flow classification.

The ref snapshot uses one `git archive` subprocess and Python's standard-library
tar reader. This avoids moving the controller checkout and avoids one `git show`
process per task file. Working-tree audit remains the default for interactive
providers.

### 2. Distinguish refinable backlog from implementation authority

The flow snapshot yields bounded `REFINERY` hints only when there is no owned,
claimable, or stale STATUS candidate. It orders existing changes as:

1. complete-but-unarchived;
2. untracked, smallest remaining task count first;
3. queued, smallest remaining task count first.

In-flight, invalid-artifact, and host-owned changes are excluded. A refinery
hint authorizes coordination reconciliation only. The disposable worker may
fold back already-landed work or land one exact pending/blocked STATUS row. It
must not edit product files until a normal claim is visible on current main.
Promotion returns `PARTIAL` so the next fresh worker performs ordinary
controller admission. A durable external/dependency gate returns `BLOCKED` only
after the exact refinery row lands and current main classifies it blocked.

### 3. Reject false exhaustion while a refinery hint exists

Candidate pressure carries a bounded refinable count. `NO_CANDIDATE` is invalid
when any owned, claimable, stale, or refinable target remains. The prompt names
the exact refinery target and removes the contradictory prohibition on the
scoped pre-claim audit. Recent-block and consumed-target suppression apply to
refinery hints by the same collision-resistant target identity.

This does not equate every unchecked checkbox with executable work. If all
remaining changes are live-owned, host-owned, invalid, or durably blocked, the
refinable count is zero and the existing honest waiting behavior remains.

### 4. STATUS row edits are implicit coordination operations

The exact path `STATUS.md` is ignored by file-overlap calculation. Adding,
claiming, heartbeating, and retiring one's own row is implicit in every lane;
the Files cell continues to name the product and durable artifact write set.
All other paths, including broad `tests/`, `REFLECTION.md`, and
`.agents/worktrees.md`, retain ordinary overlap behavior.

For backward compatibility, existing rows that list `STATUS.md` stop creating a
global collision without needing a migration. The process rule is updated so
new rows omit it from Files when the only STATUS edit is their own lifecycle.

## Risks / Trade-offs

- **Refinery work can consume a PR without product code.** This is intentional:
  it converts hidden or stale work into safe admission authority and prevents
  repeated speculative scans.
- **A poor triage decision could promote unsafe work.** Product edits remain
  impossible until the promoted row lands, passes collision/dependency checks,
  and is admitted by a fresh worker; review can reject the coordination PR.
- **Ignoring STATUS whole-file overlap permits concurrent textual edits.** Git
  still detects line-level merge conflicts, while row-level ownership prevents
  semantic claim theft. The alternative serializes all providers behind any
  active row and caused the observed starvation.
- **Exact-ref archive parsing adds code to the inspector.** One bounded git
  subprocess and stdlib parsing keep the hot path cheaper and more coherent than
  per-file subprocesses or a temporary worktree.

## Migration Plan

1. Land exact-ref flow inspection and STATUS overlap semantics behind tests.
2. Land supervisor refinery hints, prompt contract, and exhaustion validation.
3. Refresh the detached controller checkout and restart the existing watchdog
   without running a parallel tray.
4. Verify current main reports refinable pressure and the live supervisor no
   longer accepts idle while a refinery target exists.
5. Roll back by reverting the change; the prior conservative idle behavior is
   restored and no product/runtime data requires migration.

## Open Questions

None for this bounded repair. Dependency-wave execution and cloud-native backlog
refinery remain follow-on evolution of the ordinary user-owned drain Branch.
