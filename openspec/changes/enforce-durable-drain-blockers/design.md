## Context

`scripts/openspec_drain_supervisor.py` currently accepts `BLOCKED` after syntax
and admission-target validation. `apply_result` stores only the target slug in
the run-local `recent_blocked` list. It does not prove the reason became shared
coordination truth.

Run `openspec-drain-auto-20260729-145600` exposed the consequence:

- results 001 and 002 correctly found external/dependency blockers;
- neither result changed current-main STATUS classification;
- the controller suppressed them only inside that run;
- attempts 4 and 5 then spent a repair PR and foldback slice making the blocker
  truth durable.

The canonical claim checker already returns a full `blocked` collection with
the same row payload used for claimable/stale hints, so no second blocker store
is needed.

## Goals / Non-Goals

**Goals:**

- Accept `BLOCKED` only when exact current main classifies that target blocked.
- Keep the prepared admission available when the worker failed to persist the
  blocker.
- Prevent a full no-hint write worker when the only visible pressure consists
  of this run's just-blocked candidates.
- Preserve fail-closed current-main refresh and existing budgets.

**Non-Goals:**

- Inferring blockers from prose in worker output.
- Adding a controller-private long-lived blocker database.
- Changing STATUS dependency semantics or automatically editing STATUS.
- Changing cloud-drain activation, provider selection, review, or merge policy.
- Stopping or replacing the currently running controller before it is safe.

## Decisions

### 1. Current-main claim classification is the blocker oracle

`CandidateSnapshot` will carry the canonical target slugs found in the complete
`blocked` payload returned by `claim_check.py --json`. This collection is not
bounded by the candidate-hint display limit.

After parsing a `BLOCKED` marker, the supervisor fetches origin and inspects
exact `origin/main`. It accepts the result only when the reported target slug
is in `snapshot.blocked_targets`.

Alternatives considered:

- **Trust result prose:** rejected because prose is neither shared nor
  machine-authoritative.
- **Persist a controller blocker ledger:** rejected because it creates a second
  truth system and still cannot tell when an external blocker cleared.
- **Treat a missing row as blocked:** rejected because deletion could hide
  unfinished work; the worker must leave an explicit blocked row.

### 2. A non-durable block is an invalid result, not a durable task blocker

When current main still offers the target, omits it, or cannot be refreshed,
the supervisor records `INVALID_BLOCKED_RESULT`, consumes one finite failure
strike, retains the prepared admission, and dispatches the next fresh worker
back to the same lane. It does not add the target to `recent_blocked`.

The worker brief explicitly requires a sanitized STATUS dependency/blocker to
land through the normal PR path before returning `BLOCKED`. This keeps secrets
out of coordination while making the existence and class of the gate durable.

### 3. Recent-block filtering can cause a bounded cooldown, not broad rediscovery

If current-main pressure reports claimable/stale work but all concrete hints
were removed because they match `recent_blocked`, and there is no prepared
admission, the supervisor records `blocked-cooldown`, waits the configured idle
interval, and refreshes again. It does not launch a write-capable no-hint
worker.

Before filtering, the supervisor intersects `recent_blocked` with the fresh
snapshot's complete blocked-target set. A target becomes eligible immediately
when shared coordination truth no longer classifies it as blocked. The
watchdog maps live cooldown and invalid-blocker retry states to waiting, while
an ended invalid-blocker diagnostic remains a failure.

This rule does not apply when:

- an owned/prepared admission exists;
- a different concrete candidate remains; or
- canonical pressure is truly zero, where the existing exhaustion/promotion
  worker contract remains unchanged.

### 4. Deployment is an explicit post-merge step

The implementation is merged and reviewed without touching the live controller
worktree. After its active attempt reaches terminal, the controller deployment
is refreshed to the exact merged commit and restarted once. State and logs
remain available for before/after comparison.

## Risks / Trade-offs

- **[A worker cannot publish blocker truth]** → It returns `FAILED`, or its
  non-durable `BLOCKED` is rejected under the existing finite failure budget.
- **[A blocker clears without a STATUS edit]** → The row must be updated to
  become claimable; shared coordination truth, not controller memory, controls
  retry.
- **[Target labels collide after slugification]** → Preserve the existing
  canonical target contract and add duplicate-slug test coverage; do not invent
  a second identifier in this slice.
- **[Current-main fetch is unavailable]** → Fail closed and retain admission
  rather than suppressing work on stale evidence.

## Migration Plan

1. Land the delta and tests with no live-controller mutation.
2. Wait for the current attempt to produce a terminal result.
3. Refresh the controller worktree to the exact merged commit.
4. Restart the watchdog once and verify health plus a controlled invalid/durable
   blocker probe.
5. Roll back by restoring the prior merged controller commit and restarting;
   run artifacts remain compatible because the added snapshot field is derived,
   not persisted.

## Open Questions

None for this slice. Cross-run scheduling and the cloud-owned drain remain
separate changes.
