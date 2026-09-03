# One workspace slot for the whole host

**Found 2026-09-03**, in the founder's live conversation with their universe.
Tiny, reviewing what it can and cannot do:

> The platform still appears to have a single-workspace bottleneck. A recent
> workspace run on `2026-09-01 UTC` failed with `workspace_busy`, meaning one
> active workspace job blocked another. That is a real limitation for
> concurrent or multi-user complex workflow execution.

It is right, and it is worse than a limitation: it is a cross-user one.

## The cause

`tinyassets/workspace_pool.py`:

```python
HOST_SLOT = "slot-0"
```

`admit()` takes two durable locks — one scoped to the universe, one scoped to
the host:

```python
_acquire_lock(conn, scope=SCOPE_UNIVERSE, key=universe_id, ...)
_acquire_lock(conn, scope=SCOPE_HOST,     key=host_slot,   ...)
```

`host_slot` defaults to `HOST_SLOT` for every caller, so the host lock is one
row: `scope='host', key='slot-0'`. The per-universe lock is correct — a
universe should not split one job across parallel branches. The host lock is
not: it serialises **every universe on the daemon through one slot**, so any
user's checkout blocks every other user's.

The refusal even says so out loud, and has all along:

> "Another workspace job of this universe (or the host's single slot) is
> running."

## Why it matters more than throughput

The founder's floor (2026-08-30) is that the ONLY platform-wide invariant is
not affecting other users; inside their own universe the owner is god. A
global mutex is the plainest possible violation of it: user B's job fails
because user A is working, with no relationship between them.

It also caps the platform at one concurrent workspace user, which the "first
1000 paid users" target in the same conversation cannot survive.

## What a fix looks like

The host lock exists to bound concurrent disk and CPU on a 1 vCPU / 2 GB box
(see `capacity-is-memory-not-cpu`), which is a real constraint. The bound
should be a COUNT, not a single named slot: N slots, `slot-0..slot-N-1`, a run
taking the first free one, N sized by host capacity and configurable. That
keeps the capacity bound and removes the cross-user coupling.

Not yet done. Filed here rather than fixed inline because it is a storage and
admission change and the concurrency semantics deserve their own lane and a
cross-family review.
