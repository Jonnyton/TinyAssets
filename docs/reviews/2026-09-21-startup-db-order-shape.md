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

The last two rows are consistent with the short CI failure at the WAL pragma.
Correction by integrating reviewer Codex, September 21: the actual scheduler
switches WAL BEFORE its migration transaction. The controlled RESERVED-lock
test intentionally keeps rollback-journal mode and is not the scheduler's
literal migration state. It proves the storage-before-workers invariant under
real contention, not which competing connection or lock state caused CI.
Already-WAL files avoid this first-switch conflict; this does not guarantee
that all subsequent initialization or unordered multi-process calls are safe.

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

Initialize storage before starting scheduler/assigned workers. The HTTP main
entrypoint also needs initialization before its assigned worker: the app's
lifespan has not run when that worker starts. Early best-effort maintenance
catches initialization failures and cannot be the authoritative ordering gate.
Nothing else: no SQLite retry wrapper (it would mask ordering, and the failure is
instant, not contended), no busy-timeout reordering inside `runs._connect` (it
would not help — the busy handler is skipped), no scheduler change, no schema or
migration change.

Preserved: fail-closed initialization (a raising `initialize_consumer` still
aborts boot), writer-barrier release via the existing `finally`, scheduler and
consumer shutdown cleanup, and existing scheduler authority.

## Limits

The CI traceback does not identify the competing connection or its lock state.
The measurements above are Opus's Windows / SQLite 3.50.4 observations.
Codex independently ran the frozen red commit405687df on Linux3.11.15:
`python scripts/linux_oracle.py -- -q tests/test_startup_db_order.py --tb=short`
returned3failed/1passed in2.26s (session48695, exit1, September21). Failures
demonstrated actual HTTP WAL contention, reversed HTTP ordering, and reversed
stdio assigned-worker ordering. This is controlled regression evidence, not
an exact replay of historical CI. Integration tests additionally isolate the
unrelated maintenance thread and check initialization refusal/cleanup.
