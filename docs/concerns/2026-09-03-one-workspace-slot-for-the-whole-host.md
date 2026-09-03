# One workspace slot for the whole host

> **INVERTED 2026-09-03, same day.** The measurement below is real; the
> conclusion drawn from it is **false**. The host lock is NOT host-wide, so it
> does not couple users at all. Kept rather than deleted because the correction
> is the useful part, and because two lanes were already built on the wrong
> premise before it was caught.
>
> `_pool_db(base_path)` is `runs.runs_db_path(base_path)` = `<base_path>/.runs.db`,
> and `base_path` for the workspace effector **is the universe directory** —
> `_universe_id` derives the universe id from `Path(base_path).name`
> (`tinyassets/effectors/workspace.py`, `tinyassets/runs.py::runs_db_path`).
> So every universe has its OWN pool database, and the `scope='host',
> key='slot-0'` row exists once **per universe**. User B never waits on user A's
> host row. Found by cross-family review of the row-6 attempt.
>
> **The real defect is the inverse.** A host-scoped lock living in a
> per-universe database provides **no host-wide capacity bound at all** — it is
> a second per-universe lock wearing a host-shaped name. The 1 vCPU / 2 GB box
> it was meant to protect is unprotected. Whether the platform wants a genuine
> host bound is a live question; "N slots instead of one" is NOT the fix,
> because the slots were never shared.
>
> **The genuine cross-user coupling is elsewhere:** `runs.py` executes every
> universe's branches on a process-wide `ThreadPoolExecutor` with
> `_DEFAULT_MAX_WORKERS = 4`. Anything that makes a run BLOCK rather than fail
> fast — as the reverted row-6 wait did — lets one universe occupy the whole
> pool and stall every other user. That is where to look.

---

## The original filing, unedited

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
