# `initialize_runs_db()` is not safe under concurrent callers

**Filed:** 2026-08-29 (found by the schedules lane while proving its migration) · **Severity:** P2 —
a restarting multi-process daemon, or tests that share a data root, can fail boot with
`database is locked`

## The finding

Four threads racing the production entry point fail with
`sqlite3.OperationalError: database is locked` — reproduced again 2026-09-21 at
`89b47e00`, 2 of 4. The race predates `migrate_scheduler_schema`
(`tinyassets/scheduler.py`), whose own `BEGIN IMMEDIATE` if anything reduces it.

**Citation corrected 2026-09-21.** This file originally blamed `executescript` upgrading a
deferred transaction outside `busy_timeout`'s protection. On a FRESH database it never reaches
any schema statement: every captured traceback ends at `tinyassets/runs.py:98`,
`conn.execute("PRAGMA journal_mode = WAL")` in `runs._connect` — the line before
`PRAGMA busy_timeout` is even set. SQLite answers a first-time journal-mode switch that
collides with another switcher by returning SQLITE_BUSY *without* invoking the busy handler, so
the `timeout=30.0` on the connect never engages and the loser fails in ~0.0003 s. Once the file
is already WAL the pragma is a no-op and this particular race disappears, so the fresh-database
case and the old-schema case may not share a mechanism; only the fresh one is measured here.

The lane's test (`tests/test_scheduler_owner.py`, the four-thread migration race) retries on a lock
the way a real caller would and asserts what the lane owns — no `no such column`, no
`duplicate column`, the correct final schema — rather than asserting the boot path is lock-free.

## Why it was not fixed in that lane

Changing how `initialize_runs_db` opens its schema transaction touches every daemon boot and
every test in the repo; it is its own task with its own set-comparison, not a fold inside a
scheduler PR.

## Not the same defect as the startup ordering race

The unshipped `codex/startup-db-order` candidate (2026-09-21) addresses a related
single-process ordering defect: serving entrypoints started scheduler/assigned
workers before `initialize_consumer`. CI35650830517 failed at the first WAL
switch, but its competing connection is not identified. Controlled real-lock
and ordering regressions are in `tests/test_startup_db_order.py`. This concern
remains for N callers with no
ordering relationship at all: a multi-process daemon restart, or tests sharing a data root.
It stays open.

## Resolving

Serialise the first journal-mode switch, not the schema transaction — an `IMMEDIATE`
transaction around `executescript` does not help on a fresh database, because the failure
happens before any schema statement runs. Candidates: a file lock around `initialize_runs_db`,
or creating-and-switching the database once under a lock so every later `_connect` finds it
already WAL. Prove it with the four-thread race against a FRESH database (the reproducer is
five lines; `tests/test_startup_db_order.py` documents the lock semantics it depends on).
Delete this file when that lands.
