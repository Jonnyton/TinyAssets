## Why

A universe's workspace is held by one run at a time: the universe job lock is
held from the holder's first checkout until its terminal outbox entry. Today a
second run that needs it either fails `workspace_busy` or parks inside a
bounded, in-memory wait on an executor thread. PR #3927 made that wait
cancellable. The wait is lost on a daemon restart or deploy (the run becomes
`interrupted`). It has no arrival order, because whichever poller wakes first
wins. It is bounded by one node's timeout, and it occupies one of the host's
four run workers for as long as it waits. The app agent's workflow checklist
keeps reporting "durable workspace waiting/queuing" as OPEN.

## What Changes

- A root run whose admitted graph declares a `workspace` effect takes a
  durable **wait ticket** in its universe's workspace database when it is
  admitted. Tickets are served strictly in arrival order.
- Such a run **starts only on its turn**: when its ticket is first in line
  and no other run holds the universe's workspace. Until then it stays
  `queued`, runs no node, holds no worker thread, and reports a visible
  `workspace_wait` (state, position, waiting since).
- Job-lock acquisition honours the queue. While tickets exist, only the run
  holding the first ticket, or a run already holding the lock, may acquire
  it. Acquisition consumes the ticket in the same transaction.
- Hand-off is event-driven. Every lock release, terminal status,
  cancellation and periodic sweep nominates the first waiting run. That run
  is dispatched from its durable admission envelope, with provider authority
  freshly bound for its owner.
- Restart: a waiting run is not interrupted. It resumes waiting, or starts,
  after the restart. A run that had already started is never re-dispatched
  and keeps today's `interrupted` settlement.
- Cancelling a waiting run settles it `cancelled` at once and removes its
  ticket. The holder is untouched (PR #3927 semantics preserved).

## Impact

- Storage: one new table, `workspace_waiters`, in the existing workspace pool
  database (same file and transaction domain as `workspace_locks`).
- Code: `tinyassets/workspace_pool.py`, `tinyassets/runs.py`, the run
  snapshot in `tinyassets/api/runs.py`, and the plugin mirror.
- Specs: `scratch-storage` (ADDED requirement).
- Not changed: the bounded in-node wait for runs that are not queued this way
  (children, and runs without an owner or universe), quotas, the hourly
  ledger, the lease/generation protocol, cloud admission and
  provider-authority rules.
