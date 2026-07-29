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
returns `NO_CANDIDATE`. A nonzero `claimable` or `stale` count makes the result
semantically invalid, consumes a bounded failure strike, and triggers a fresh
worker unless the failure budget is exhausted.

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

### Treat closed-session release as coordination repair

The host's statement that no other sessions are open is direct authority to
change the 11 named foreign statuses back to `pending`. Their worktrees,
branches, OpenSpec artifacts, and histories remain intact; only exclusive
ownership is released.

## Risks / Trade-offs

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
