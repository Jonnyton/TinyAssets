# A second workspace job should wait, not die

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

**The waiting machinery already exists and is unreachable.**
`workspace_pool.admit()` takes `wait_s` and `sleep`, and its loop
(`workspace_pool.py`, the `while True` around `_attempt()`) retries the WHOLE
admission every `LOCK_POLL_S` (0.5s) until a deadline, on exactly one refusal
code — `REFUSED_BUSY`, which is `workspace_busy`. It deliberately does not wait
on quota or a full pool, because those will not clear inside a node's timeout.
That is precisely the semantic row 6 asks for.

Its only caller never passes it. `effectors/workspace.py::_admit()` (both call
sites) omits `wait_s`, so it defaults to `0.0` and refuses immediately. The
sweep-once-retry-once around it is for locks held by *finished* runs, not for
real contention.

So the platform already has the primitive, tested and documented, and the
surface never offers it — the same shape as the connect picker that could bind
any provider while showing two.

## What changes

The workspace effector passes a bounded `wait_s` derived from the time the node
can actually afford, so a second same-universe job waits for the first instead
of dying at submit. The bound is the caller's, never the packet's: a
packet-chosen wait is a packet choosing how long to occupy a slot.

## Non-goals

- **The host slot stays a separate lane.** `HOST_SLOT = "slot-0"` is a single
  global mutex defaulted for every caller (`workspace_pool.py:44,519,649`,
  re-verified 2026-09-03), so any user's job blocks every other user's. That is
  a cross-user violation of the one platform-wide floor and is filed at
  `docs/concerns/2026-09-03-one-workspace-slot-for-the-whole-host.md`. Waiting
  makes it *degrade* rather than fail, which is strictly better but is not the
  fix — the fix is N slots. Row 6 does not pass on the host lock alone, and this
  change does not close that concern.
- Durable cross-process queueing that survives past a node's timeout. A bounded
  wait satisfies "queued and later runs automatically" for contention shorter
  than the wait; a job longer than the bound still refuses. If tiny judges that
  insufficient, the follow-on is a real queue, and its verdict decides.
- Storage shape, lease accounting and the refusal taxonomy are untouched.

## Open question for the reviewer

Whether a bounded wait meets row 6 or only softens it. Tiny wrote "queued and
later runs automatically"; a wait is not a queue. This change is proposed as the
smallest honest step, and the row is NOT claimed passed until tiny says so.
