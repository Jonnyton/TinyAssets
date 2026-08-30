# `initialize_runs_db()` is not safe under concurrent callers

**Filed:** 2026-08-29 (found by the schedules lane while proving its migration) · **Severity:** P2 —
a restarting multi-process daemon, or tests that share a data root, can fail boot with
`database is locked`

## The finding

`tinyassets/runs.py:initialize_runs_db` runs the schema via `executescript`, which upgrades the
connection's deferred transaction to a write transaction outside `busy_timeout`'s protection.
Four threads racing the production entry point on an OLD schema fail 2/4 with
`sqlite3.OperationalError: database is locked`; on a FRESH database — where the new scheduler
migration is a complete no-op — they still fail 3/4. So the race predates
`migrate_scheduler_schema` (`tinyassets/scheduler.py`), whose own `BEGIN IMMEDIATE` if anything
reduces it.

The lane's test (`tests/test_scheduler_owner.py`, the four-thread migration race) retries on a lock
the way a real caller would and asserts what the lane owns — no `no such column`, no
`duplicate column`, the correct final schema — rather than asserting the boot path is lock-free.

## Why it was not fixed in that lane

Changing how `initialize_runs_db` opens its schema transaction touches every daemon boot and
every test in the repo; it is its own task with its own set-comparison, not a fold inside a
scheduler PR.

## Resolving

Make schema initialisation take an `IMMEDIATE` transaction (or serialise callers on a file
lock) and prove it with the same four-thread race against a fresh database; delete this file
when that lands.
