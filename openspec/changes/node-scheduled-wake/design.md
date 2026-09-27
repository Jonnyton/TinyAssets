# Design: node-scheduled wake

## D1. A wake is a one-shot automation, not a queue row

The automation store already has everything a delayed run needs:
- durable rows and a pump that survives restarts;
- a `(automation_id, due_at)` claim fence and the universe lease;
- run-time re-derivation of owner authority;
- per-universe admission;
- an owner-visible list and a `delete` control.

So the node verb calls `register_automation(..., not_before=...)`. That is the
same function the owner's `write_graph target=automation create` uses, with
the same checks. This adds no second scheduler and no second authority path.

**Rejected:** fixing the epoch-1 queue. It has no cloud runner. Giving it one
would build a parallel executor beside the pump.

## D2. Due instant and retries

A `once` row is due at `not_before + 60 s * attempts`, where `attempts` is the
number of `automation_attempts` rows for it. Every input is stored, so a
restart derives the same key.

- A run that started, whether it completed or failed, retires the row. What the
  graph did is its own outcome, and the graph can wake itself again.
- An attempt that never reached a run is retried under the next key 60 s later.
  That covers rate-limited, context unavailable, and a process killed
  mid-claim.
- A process killed mid-run leaves its claim. The next key is claimable only
  once the universe lease is free. #4065 frees it the moment the holder is
  provably dead; before #4065 it frees at the TTL. So the killed run is
  retried rather than lost.
- After `MAX_ONCE_ATTEMPTS` (5) the row retires with the reason `gave_up`.
- An authority refusal pauses the row, as it does for any automation. The owner
  sees it and can resume or delete it.

## D3. Usage, not structure

The retired limits are all shape limits: depth, fan-out per run, queue size,
and lineage size. In their place:

- **Pending wakes per universe:** `MAX_ACTIVE_PER_UNIVERSE`, counted over
  non-retired rows. This bounds outstanding work, not graph shape. A
  self-rescheduling chain holds one row.
- **Runs per universe per window:** `_engine_run_admit` at fire time, which is
  the same budget a foreground `run_graph` pays.
- **`not_before` bounds:** a time in the past means now, and anything later
  than 366 days is refused, so a row cannot be parked forever.

## D4. The cross-user floor

- **Universe:** the run's trusted `NodeEnqueueContext.universe_id` only. A
  caller-supplied `universe_id` must equal it.
- **Owner:** the bound principal inside the run. That is the request actor for
  a foreground run, or the owner bound by `owner_run_identity` (#4060) for a
  background run. An actor that is not a named principal is refused.
- **Checks:** `register_automation` then requires `admin`,
  `get_founder_home(owner) == universe`, and that the owner authored the
  branch. It re-checks all of them at fire time.

A node in Alice's universe therefore cannot store a row in Bob's universe,
cannot store a row owned by Bob, and cannot run Bob's branch.

## D5. Storage

`trigger_kind` gains `once` through an idempotent CHECK rebuild in one
`BEGIN IMMEDIATE`: create a successor table, copy the shared columns, drop the
old table, rename, and re-index. The new column is
`not_before TEXT NOT NULL DEFAULT ''`.
