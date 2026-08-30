# Codex review — runs-table migrations under BEGIN IMMEDIATE (PR #2708)

Branch `claude/runs-db-race`, reviewed at a41e5c6c on 2026-08-30 via `python scripts/peer_agent.py codex --prompt-file <brief>` on Codex's own budget. Its Linux (WSL2) probe is the red→green oracle a Windows run could not give: main's unguarded check/ALTER pattern failed 25/25 four-thread trials (75 `duplicate column name: branch_version_id` errors); the patched helper 0/25. ADAPT was test-completeness only (assert thread termination; assert the migrated `runs` columns and indexes), folded in the same PR.

Review basis: 2026-08-29; clean worktree at `a41e5c6ce7be753c3f08b24bdabf72171c3c2235`, merge-base/origin-main `5c092da5`. Inspected with `git diff origin/main...HEAD -- tinyassets/runs.py`, `rg -n`, targeted pytest, and standard-library SQLite probes on Windows and WSL2 Linux.

1. **AGREE — transaction sequence is correct.**

[runs.py:87–99](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:87) uses current sqlite3 defaults, WAL, and a 30-second timeout. The custom context manager commits only after a normal return and always closes; it does not introduce another transaction.

Initialization executes the schema, performs the audit migrations, then calls the helper at [runs.py:498–523](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:498). The helper’s `commit()` at [runs.py:281](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:281) guarantees no active transaction before `BEGIN IMMEDIATE` at line 282. Thus this sequence cannot produce “cannot start a transaction within a transaction” under the current legacy/default transaction mode. `executescript()` also commits any pending transaction before running its script. [Python sqlite3 documentation](https://docs.python.org/3/library/sqlite3.html)

Commands/probes:

- Windows, Python 3.14.3/SQLite 3.50.4: `in_transaction` was false after `executescript`, `ALTER`, and `commit`; true only after `BEGIN IMMEDIATE`.
- Linux WSL2, Python 3.12.3/SQLite 3.45.1: same result.
- The outer commit at [runs.py:97](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:97) runs after the helper has already committed, so it is a no-op.

2. **AGREE — `BEGIN IMMEDIATE` serializes the check and ALTER.**

The write transaction begins before `PRAGMA table_info` at [runs.py:282–289](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:282) and remains held through all ALTERs/index creation until commit at [runs.py:334](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:334).

WAL permits concurrent readers but only one writer. A second `BEGIN IMMEDIATE` waits under the busy timeout; after the first writer commits, the waiter acquires the write transaction and its subsequent `PRAGMA table_info` sees the committed columns. If the timeout expires, it raises `database is locked`; it cannot proceed using the pre-commit schema. [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html), [SQLite WAL documentation](https://www.sqlite.org/wal.html)

Linux command: `wsl.exe -d Ubuntu -- python3 -` with a four-connection WAL probe. Observed acquisition order:

```text
0.000s: ('id',)
0.181s: ('id', 'branch_version_id')
0.231s: ('id', 'branch_version_id')
0.332s: ('id', 'branch_version_id')
errors: []
```

3. **DISAGREE_CONCERN — schema mismatches remain name-only validated.**

The catch at [runs.py:274–279](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:274) only swallows an `OperationalError` whose message contains `duplicate column`; every other `OperationalError` is re-raised.

However, [runs.py:286–309](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:286) validates only column names. An actual-helper probe created `branch_version_id INTEGER DEFAULT 42`; migration completed and preserved that incompatible declaration:

```text
{'name': 'branch_version_id', 'type': 'INTEGER',
 'notnull': 0, 'dflt_value': '42'}
```

That mismatch is skipped before the duplicate catch runs, so it is a pre-existing limitation of the name-only migration strategy rather than a new race introduced by this patch. With `BEGIN IMMEDIATE`, a normal competing SQLite writer cannot create a conflicting column between the probe and ALTER. I would not block this race fix on full schema validation.

4. **AGREE — no nested transaction control in callees.**

`migrate_contribution_events_schema` performs only `PRAGMA table_info` and conditional ALTERs at [contribution_events.py:76–84](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/contribution_events.py:76). It has no `BEGIN`, `COMMIT`, `commit()`, or `rollback()`.

Inside `_migrate_runs_table_columns`, everything else is the local `_alter` helper or direct index creation. `migrate_scheduler_schema` is called earlier at [runs.py:505](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:505), outside the new transaction. Command: `rg -n "BEGIN|COMMIT|commit\\(|rollback\\(" tinyassets/contribution_events.py`.

5. **AGREE — failures roll back and raise loudly.**

The transaction body is guarded by rollback plus bare re-raise at [runs.py:283–337](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:283). `initialize_runs_db` does not catch that exception at [runs.py:523](C:/Users/Jonathan/Projects/wf-runs-db-race/tinyassets/runs.py:523), so it propagates through `_connect`; the outer normal-path commit is skipped.

An actual-helper probe forced the unique-index creation to fail:

```text
raised IntegrityError UNIQUE constraint failed: runs.branch_task_id
in_transaction_after False
rollback_restored_schema True
connection_usable 2
```

Earlier schema-script/audit work may already be committed by line 281, but the new runs migration is atomic and failure is never silent. A failure of `BEGIN IMMEDIATE` itself occurs before a transaction exists and also propagates loudly.

6. **DISAGREE_EVIDENCE — it detects the reported race, but does not fully assert its stated final-schema claim.**

The test records every non-lock `OperationalError` and every other exception at [test_scheduler_owner.py:1504–1519](C:/Users/Jonathan/Projects/wf-runs-db-race/tests/test_scheduler_owner.py:1504). Therefore `no such column` and `duplicate column` reach the assertion at line 1526. The test is unchanged from main: `git diff --exit-code origin/main...HEAD -- tests/test_scheduler_owner.py` returned `TEST_DIFF_EMPTY`.

It would go red on main under a sufficiently parallel Linux schedule. A Linux four-thread mirror of main’s unguarded check/ALTER ran 25 trials: 25/25 had errors, totaling 75 `duplicate column name: branch_version_id` exceptions. The patch’s corresponding probe had none. Windows targeted command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider tests/test_scheduler_owner.py::test_four_concurrent_initialize_runs_db_calls_migrate_correctly
# 1 passed in 0.31s
```

Two assertion gaps remain:

- Threads are joined with a timeout at [test_scheduler_owner.py:1521–1526](C:/Users/Jonathan/Projects/wf-runs-db-race/tests/test_scheduler_owner.py:1521), but the test never asserts that every thread terminated.
- Final-schema checks at [test_scheduler_owner.py:1528–1534](C:/Users/Jonathan/Projects/wf-runs-db-race/tests/test_scheduler_owner.py:1528) inspect only `branch_schedules`; they do not verify the migrated `runs` columns or indexes that this patch owns.

The independent Claude review returned `SHIP`; my divergence is limited to these concrete test-completeness gaps. No files were modified.

VERDICT: ADAPT a41e5c6c — assert all four threads terminated, then assert the expected `runs` columns and dependent indexes in the final database.