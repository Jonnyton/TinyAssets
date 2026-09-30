---
severity: P2
title: A cancelled universe-tool call keeps its place in the queue
filed: 2026-09-30
summary: Cancelling the async tool await leaves its worker thread waiting for a host slot and running the abandoned call.
---

# A cancelled universe-tool call keeps its place in the queue

**Found:** Codex `gpt-6-astra` refute of PR #4134, 2026-09-30 (finding 5, P2).
**Area:** `tinyassets/universe_tools.py:_slot`, `tinyassets/engine_mcp_server.py:_universe_tool`.

## What

A busy host now makes a universe tool call **wait** for one of `_HOST_SLOTS`
instead of refusing it after 30 seconds. The wait is not interruptible:

- `_universe_tool` reaches the jail through `asyncio.to_thread`.
- Cancelling that await cancels only the await. The worker thread goes on
  polling for a slot, takes one, runs the jail, and discards the answer.

So a client that disconnects mid-call still consumes a slot when its turn comes,
and its thread is unavailable until then.

## Why it is P2 and not P1

- The waiter holds **no lock and no jail** — one pipe descriptor (the seccomp
  filter, opened before the wait so a host that cannot jail at all refuses
  immediately rather than after queueing). Bounded by the transport thread pool,
  that is ~40 descriptors against a 1024 `nofile` limit.
- The queue's depth is the **transport's own thread pool**, not something a
  universe chooses. A waiter costs a parked thread where the bound it is waiting
  on exists to stop 189 MB subprocesses.
- Work is never lost: the call completes, just later than the client cared.

## Why it was not fixed in that PR

Making the wait interruptible means admitting **asynchronously** — an
`async` acquire in `_universe_tool` that a cancelled task can abandon, with the
sync `_slot` kept for callers already on a thread. That is the same split
`provider_admission` has (`provider_slot` / `provider_slot_async`), and it is a
design change to the tool path rather than a limit removal.

## What would resolve this

An async admission path for the engine tool wrappers: acquire the host slot with
a cancellable `await` before `asyncio.to_thread`, so a cancelled request leaves
the queue. Delete this file when that lands.

## What would NOT resolve it

Restoring the 30-second refusal. Over the concurrency line, work waits and is
never refused (founder, 2026-09-30). A refusal bounded the queue by discarding
the user's work, which is the behaviour the directive removes.
