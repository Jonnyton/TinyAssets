## Context

Drain attempt 1 on 2026-07-28 returned `NO_CANDIDATE` after
`claim_check.py` reported zero claimable rows, 11 in-flight rows, and eight
stale-claim candidates. The worker brief permitted policy-compliant reaping but
did not require it, and the supervisor accepted the terminal marker without
checking current coordination state. Separately, the host confirmed that all 11
foreign claim owners were closed sessions, so the live STATUS board was stale.

The safety boundary remains the STATUS claim table: an autonomous drain must
not steal a live claim, but stale coordination metadata must not become an
unbounded utilization lock.

## Goals / Non-Goals

**Goals:**

- Turn policy-qualified stale claims into mandatory recovery candidates.
- Reject a worker's `NO_CANDIDATE` result when the claim checker still exposes
  claimable or stale work.
- Require blocker freshness checks and safe cross-cutting promotion before
  genuine idle.
- Release the exact claims the host identified as belonging to closed sessions.

**Non-Goals:**

- Inferring the liveness of arbitrary remote provider sessions from local
  process state.
- Bypassing host-owned actions, unresolved design decisions, file collisions,
  or independent-review gates.
- Running more than one drain worker concurrently.

## Decisions

### Use `claim_check.py --json` as the controller gate

The supervisor will invoke the existing read-only JSON interface after a worker
returns `NO_CANDIDATE`. A nonzero `claimable` or `stale` count, or an in-flight
row whose claimer equals the exact drain identity, makes the result semantically
invalid, consumes a bounded failure strike, and triggers a fresh worker unless
the failure budget is exhausted.

This keeps claim classification in one implementation rather than duplicating
STATUS parsing inside the supervisor. Merely strengthening the prompt was
rejected because the observed worker already ignored a softer version of the
rule.

### Make exhaustion order explicit in every worker brief

The brief will require this order before idle:

1. resume the drain identity's existing claim;
2. take a claimable finish-first row;
3. reap and claim a policy-qualified stale row;
4. freshness-check blocker/dependency labels and remove only those disproved by
   current evidence;
5. promote one safe non-overlapping cross-cutting recovery task under the
   existing AGENTS rule.

Live claims and host-owned rows remain unavailable.

### Preselect from canonical coordination state

Immediately before each dispatch, the controller will read the same
`claim_check.py --json` payload and inject at most five ordered hints: an exact
drain-owned row first, then claimable rows in STATUS order, then
policy-qualified stale rows. Controller admission reruns the checker on current
main, claims the first hint that remains valid, and commits that claim before
dispatch. The worker verifies the prepared claim before broad OpenSpec audit.

The snapshot is advisory until revalidated, so it cannot override a claim that
became live between dispatch and worker startup. Bounded injection was chosen
over feeding the complete backlog because the live recovery worker spent more
than 14 minutes scanning without creating a claim, worktree, or result despite
six canonical claimable rows.

### Use balanced reasoning for disposable Codex workers

The host Codex configuration uses `high` reasoning for interactive frontier
sessions. A drain worker has a narrower contract, a preselected lane, mandatory
tests/review, and a fresh replacement on every slice. The supervisor therefore
passes `--effort medium` to Codex peer workers. This preserves substantive
reasoning while avoiding an unbounded high-effort admission phase. Claude
workers retain their provider-native model setting.

### Separate admission from paid implementation reasoning

Both high- and medium-effort workers remained claim-free for more than five
minutes after receiving a concrete ordered candidate list. Candidate selection
and lane setup are deterministic coordination operations, so the controller
will perform them before dispatch:

1. fetch current `origin/main`;
2. create one deterministic clean sibling worktree and branch;
3. run the bounded claim-phase context feed and canonical checker there;
4. reject the admission if the candidate is no longer admissible;
5. write `_PURPOSE.md`;
6. commit the exact STATUS claim with the drain identity and heartbeat;
7. launch the worker with that worktree as its cwd.

A policy-qualified stale row gets a separate reaping commit before the claim
commit. The worker may verify but not repeat admission or choose another lane.
The admission record is persisted in supervisor state and reused by replacement
workers. Existing branches/worktrees are never overwritten or deleted; a
collision makes admission visibly fail within the normal failure budget.

A `BLOCKED` result releases the active admission and records its target in the
bounded recent-block list, so the next snapshot skips it and admits a different
candidate. The preserved worktree remains visible for later recovery. A
`PARTIAL` result retains admission but requires current-main restacking before
foldback publication. Worker results must name the assigned target; admission
timeouts and file/process errors become bounded `admission-failed` state rather
than escaping the controller.

### Treat closed-session release as coordination repair

The host's statement that no other sessions are open is direct authority to
change the 11 named foreign statuses back to `pending`. Their worktrees,
branches, OpenSpec artifacts, and histories remain intact; only exclusive
ownership is released.

## Risks / Trade-offs

- **A candidate can change after snapshot** — The worker reruns the canonical
  checker and claims only a hint that remains admissible.
- **A crash can strand a prepared lane** — The deterministic admission path
  persists the lane before dispatch, refuses pre-existing paths/branches, and
  replacement workers reuse the persisted worktree.

- **A stale claim could belong to slow uncommitted work** → The existing
  24-hour/no-heartbeat policy remains the autonomous threshold; same-day claims
  are released only on explicit host confirmation.
- **A malformed claim-check response could cause retry churn** → Inspection
  failure is bounded by the supervisor failure budget and becomes visible as a
  down state rather than false idle.
- **A worker could repeatedly ignore the recovery order** → Each rejected
  result consumes a strike, so the controller fails visibly instead of burning
  subscription indefinitely.
- **Pending rows can still carry obsolete dependency prose** → The brief
  requires evidence-backed freshness correction, not blind dependency removal.
