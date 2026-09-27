---
severity: P2
title: Worker heartbeat files accumulate per boot
filed: '2026-09-27'
summary: each boot writes `.worker_supervisor.worker_assigned_<uuid>.json` into every universe and never removes old ones (125 in a third user's private home since 09-10); the writer also `mkdir`s a missing universe
---

# Every boot leaves a worker heartbeat file in every universe, forever

**Severity:** P2 · **Filed:** 2026-09-27 · **Verified:** 2026-09-27 against `origin/main` 61c434d3
and the live droplet (deployed c8f66c6a)

## What is wrong

`AssignedQueueConsumer.__init__` (`tinyassets/runtime/assigned_queue_consumer.py:213`) mints a
fresh `boot = uuid.uuid4().hex` for each process. It then publishes its beat as
`.worker_supervisor.worker_assigned_<boot>.json` into each universe it serves (`:1014`, via
`supervisor_heartbeat_filename`). Nothing removes the previous boot's file. Every deploy or
restart therefore adds one file to every universe directory.

## Evidence (live, 2026-09-27 02:10Z)

| Universe | Heartbeat files |
|---|---|
| `u-01kxm1vszd8hwp7em418asq8h9` (founder) | 287 |
| `u-01m26ac5ds3t48mktxykvgnvwg` (a third user's private home) | 125, the oldest from 2026-09-10 |
| `u-01ky3zh1arr8qth8jee7zx63pq` (free test account) | 55 |

## Why it matters

- **A platform process writes clutter into a user's private folder.** Each file is roughly
  720 bytes of operator state (pid, boot id, capabilities) that the user never asked for.
- **Worker liveness reads get slower with every boot.** `tinyassets/api/universe.py:1372` globs
  `.worker_supervisor.*.json` and parses every match on each read, so the cost grows with the
  number of files.
- **The writer can recreate deleted universes.** It calls `universe.mkdir(parents=True,
  exist_ok=True)` (`:1013`), so a beat for a universe that was just deleted brings its directory
  back. This did not happen during the 2026-09-27 cleanup, because the serving bindings went in
  the same transaction, but the delete path has to keep it that way.

## Fix shape

- On start, the consumer removes `.worker_supervisor.worker_assigned_*.json` files whose beat is
  older than the liveness window. Alternatively it keys the file by a stable per-host worker id
  rather than a per-boot uuid.
- The beat should not `mkdir` a universe directory. It should skip a universe whose directory
  is absent.
