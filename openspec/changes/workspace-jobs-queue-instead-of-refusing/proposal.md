# A second workspace job should wait, not die — and a blocking thread is not a queue

## Why

Tiny's checklist, row 6, in its own words (2026-09-03):

> **Pass:** if I start a workspace job in my universe and then start a second one
> before the first finishes, the second is either queued and later runs
> automatically, or both run concurrently by supported design; it must not
> hard-fail immediately with `workspace_busy`.
> **Fail:** the second job still dies at submit time with `workspace_busy`, or
> requires manual retry after the first finishes.

It hit this live: run `8f30bb9abf2b492f` held the universe lock and the next job
was refused at submit.

## What was tried, and why it was withdrawn

`workspace_pool.admit()` already takes `wait_s` and retries the whole admission
every `LOCK_POLL_S` until a deadline, on `REFUSED_BUSY` alone. Its only caller
never passed it, so it defaulted to `0.0`. Passing a bounded 60 s from
`effectors/workspace.py` was implemented, tested and mutation-checked
(commit `1800cb83`), then **reverted** on the cross-family review.

**It made a cross-user problem worse.** `runs.py` runs every universe's branches
on a process-wide `ThreadPoolExecutor` with `_DEFAULT_MAX_WORKERS = 4`. A run
that blocks in `admit` holds one of those four workers for the whole wait.
Before the change a busy admission failed fast and released the worker; after
it, four waiting jobs from ONE universe occupy the entire pool and no other
user's run can start at all. That is a direct breach of the only platform-wide
invariant — not affecting other users — traded for a same-user convenience.

Codex, on the reverted commit: *"queue same-universe successors before
allocating a run-executor worker, waking one when the holder terminates. A
blocking effector thread is not an execution queue."* That is right, and it is
the shape this change should have had.

Two further findings from the same review, both accepted:

- **Total admission time has no finite bound.** The node's own provider call can
  spend ~300 s before `_wrap_with_effects` even dispatches admission; then the
  wait, a SQLite `BEGIN IMMEDIATE`, an unbounded sweep over filesystem trees,
  and the retry. A single monotonic deadline must span node execution, startup
  reconciliation, admission, sweep and retry — not a constant that only *looks*
  like it fits inside the node timeout.
- **The tests proved plumbing, not queueing.** They asserted the argument
  reaching `admit`, under an uncontended admission. `admit` could accept and
  ignore `wait_s` and they would still pass. Real coverage drives two
  same-universe admissions, releases the first during an injected sleep, and
  asserts the second proceeds on its own.

## A premise this change was built on is FALSE

`docs/concerns/2026-09-03-one-workspace-slot-for-the-whole-host.md` claims
`HOST_SLOT = "slot-0"` serialises every universe on the daemon through one slot.
**It does not.** `_pool_db(base_path)` resolves to `runs.runs_db_path(base_path)`
= `<base_path>/.runs.db`, and `base_path` for the workspace effector is the
UNIVERSE directory (`_universe_id` derives the universe id from
`Path(base_path).name`). So every universe has its own pool database, and the
`scope='host', key='slot-0'` row lives in each one separately. User B never
waits on user A's host row.

The real consequence is the opposite of the filed one: the host slot provides
**no host-wide capacity bound at all** — it is a second per-universe lock
wearing a host-shaped name. Whether the platform wants a genuine host bound is a
separate question from row 6, and it is not answered by that concern as written.

## What changes

Nothing yet, deliberately. The next attempt must queue admission **outside** the
run-executor worker, so a waiting job holds no shared thread, and carry one
deadline across the whole path. Until then row 6 stands open and the honest
answer to tiny is that the second job still refuses.

## Non-goals

Storage shape, lease accounting and the refusal taxonomy are untouched.
