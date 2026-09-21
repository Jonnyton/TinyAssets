# Shape assessment — fresh-database startup race (CI 35650830517)

Reviewer: Claude Opus 5, 2026-09-21. Worktree `wf-startup-db-order`, base
`89b47e00f26deec4e707f97dbfac381687e39e69` (clean).

## Verdict: AGREE

The diagnosis — background scheduling starts before its run database is
initialized — is supported by source inspection and by a measured SQLite
reproduction of the exact failure signature. Two serving entrypoints have the
defect, not one.

## Evidence

**1. The HTTP lifespan starts the scheduler before initializing storage.**
`tinyassets/universe_server.py:3943` calls `start_scheduler_for_serving()`;
`tinyassets/universe_server.py:3948` calls `initialize_consumer(data_dir())`
afterwards, inside the `try:` whose `finally:` stops the scheduler and releases
the writer barrier (`universe_server.py:3955-3958`).

**2. `start_scheduler_for_serving` reaches a DB-opening thread synchronously.**
`universe_server.py:1554-1560` → `scheduler.get_or_create_scheduler`
(`scheduler.py:1436-1447`) constructs `Scheduler` and calls `.start()` in the
same call. `Scheduler.start` (`scheduler.py:871-883`) starts `scheduler-tick`
and `scheduler-event` daemon threads immediately. `_tick_loop`
(`scheduler.py:907-913`) calls `_fire_due_schedules` with no initial delay, and
`_fire_due_schedules` (`scheduler.py:926-931`) opens `.runs.db` via
`scheduler._connect` (`scheduler.py:1426-1433`), which runs
`PRAGMA journal_mode = WAL` and then `migrate_scheduler_schema(conn)` — a
write transaction (`CREATE TABLE` / `ALTER TABLE` + `commit`,
`scheduler.py:1405-1423`).

**3. The loser of that race fails instantly, not after the busy timeout.**
`runs._connect` (`tinyassets/runs.py:93-105`) opens with `timeout=30.0` and then
runs `PRAGMA journal_mode = WAL` as its first statement. Measured on this host,
SQLite 3.50.4:

| Contending state on a fresh (rollback-journal) `.runs.db` | `PRAGMA journal_mode=WAL` result |
|---|---|
| other connection holds a read transaction | `database is locked` after **32.8 s** |
| other connection holds `BEGIN IMMEDIATE` (RESERVED) | `database is locked` in **0.000 s** |
| 4 threads racing the first switch | `database is locked` in **0.0003 s** (3 of 4) |

The last two rows match the CI signature: `database is locked` on a connection
carrying a 30 s timeout, in a test whose junit `time` was 0.024 s. SQLite does
not invoke the busy handler when a lock upgrade would deadlock, so a concurrent
first-time WAL switch — or a writer already holding RESERVED, which is exactly
what `migrate_scheduler_schema` holds — fails the other side immediately. Once
the file is already WAL the pragma is a no-op and the race cannot occur, which
is why only fresh data dirs (per-test `tmp_path`, first boot) are affected.

This is the reported traceback: `universe_server.py:3948 initialize_consumer` →
`consumer_runtime.py:248-251 canonical.initialize` → `initialize_runs_db` →
`runs.py:98 PRAGMA journal_mode=WAL`.

**4. A second serving entrypoint has the same ordering defect.**
`universe_server.py:4223-4229`: `AssignedQueueConsumer(data_dir()).start()` —
which spawns a polling thread (`runtime/assigned_queue_consumer.py:230-245`) —
runs before `initialize_consumer(data_dir())` on the sse/stdio path. Fixing the
HTTP lifespan alone would leave this one.

**5. The third call site is already correct.** `universe_server.py:4129` runs
`initialize_consumer(_sb_data_dir())` in the boot-maintenance block, on the main
thread, before the `_served_budget_lease_loop` thread is defined and started
(`universe_server.py:4139+`). No change needed there. It also explains why
production rarely shows this: `run_server` reaches line 4129 before the app
lifespan runs, so the DB is usually already WAL by the time line 3943 fires. The
lifespan is nevertheless not self-sufficient, and `TestClient` entering it on a
fresh `tmp_path` — the CI failure — takes the uninitialized path.

## Scope of the correction

Initialize storage before starting background work in both affected entrypoints.
Nothing else: no SQLite retry wrapper (it would mask ordering, and the failure is
instant, not contended), no busy-timeout reordering inside `runs._connect` (it
would not help — the busy handler is skipped), no scheduler change, no schema or
migration change.

Preserved: fail-closed initialization (a raising `initialize_consumer` still
aborts boot), writer-barrier release via the existing `finally`, scheduler and
consumer shutdown cleanup, and existing scheduler authority.

## Limits

The 0.024 s CI failure is consistent with both instant-fail rows above; this
assessment does not distinguish which of the two lock states the CI run hit,
because the correction is identical either way. The measurement is Windows /
SQLite 3.50.4; the Linux oracle run on the regression test is the cross-platform
check.
