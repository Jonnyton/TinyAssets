# Design — reach the wait that is already there

## The mechanism, as built

`workspace_pool.admit()` ends in:

```python
while True:
    try:
        return _attempt()
    except WorkspacePoolRefused as refusal:
        remaining = deadline - float(now())
        if refusal.code != REFUSED_BUSY or remaining <= 0:
            raise
        sleep(min(LOCK_POLL_S, remaining))
```

Three properties matter and are already correct:

1. **The whole admission is retried**, not just the lock acquisition — so the
   rolling-hour ledger, the pool total and the quota are re-read after the wait.
   A cheaper "wait on the lock, then proceed" would admit against stale numbers.
2. **Only `REFUSED_BUSY` waits.** Quota and pool-full raise straight out. The
   comment in the source states the reason: those will not clear inside a node's
   timeout, and sleeping on them turns a clear refusal into a hang.
3. **The deadline is computed once**, before the first attempt, so retries
   cannot extend it.

Nothing here needs changing. The change is that a caller passes `wait_s`.

## Why the default is 0 and why that was right once

`wait_s=0.0` makes admission total and immediate, which is the correct default
for a primitive: a caller that cannot afford to block must not be made to. The
defect is that the ONLY caller is a caller that CAN afford to block, and it
takes the default.

## What the bound should be

The node's remaining budget, minus a margin for the checkout itself. Two
constraints:

- It must be the platform's number, not the packet's. A packet-chosen wait lets
  a user hold a slot for as long as they like, which is a cross-user effect and
  therefore over the floor.
- It must be shorter than the run timeout, or the wait consumes the budget the
  job needed to do its work, and a "queued" job dies of timeout instead of
  `workspace_busy` — the same failure wearing a different name.

## What this does NOT fix

The host slot. `HOST_SLOT = "slot-0"` is one row for the whole daemon, so with
this change user B's job *waits* on user A instead of failing on them. Better,
and still a cross-user coupling: B's latency is a function of A's work. The
concern file carries the real fix (N slots, sized by host capacity). Do not let
"row 6 passed" be read as "the host slot is fixed".
