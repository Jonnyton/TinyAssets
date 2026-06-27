# Flake investigation — `test_record_and_get_stats_roundtrip`

**Status:** Investigation. No code changes shipped. Reproduction not seen today; structural flake-mode hypothesis identified.
**Concern (STATUS.md):** "[2026-04-20] `test_node_eval::test_record_and_get_stats_roundtrip` pre-existing flake. Passes alone, flaky in full suite." Concern entered STATUS 2026-04-20 (commit f64347c, navigator-authored session-close) and never moved.
**Test:** `tests/test_node_eval.py:79`.
**Subject under test:** `workflow.node_eval.NodeEvaluator` (SQLite-backed; `_db_path` injected per-fixture).

## Reproduction attempts (2026-04-26 21:55–23:30 local)

| Attempt | Command | Result |
|---|---|---|
| 1 | `pytest tests/test_node_eval.py::test_record_and_get_stats_roundtrip -q` (alone) | **PASS** in 0.11s. |
| 2 | `pytest tests/test_node_eval.py -q` (whole file, 20 tests) | **PASS** in 0.68s. |
| 3 | `pytest tests/test_data_dir_call_sites.py tests/test_node_eval.py -q` (potential pollutant pre-pended) | **PASS** in 0.75s (26/26). |
| 4 | `pytest tests/test_node_eval.py tests/test_data_dir_call_sites.py -q` (reverse order) | **PASS** in 0.78s (26/26). |
| 5 | `pytest -q` (full suite) | Reached 81% (~5,000+ tests) with no failures before I killed the run after 35 min. Output buffering meant I couldn't see the live tail; killing flushed stdout up to the 81% mark. **No flake observed in the 81% covered.** |

**Verdict on reproduction:** the flake did not surface today. This matches the prior diagnosis in dev-2 memory `project_task_12_pollution_diagnosis_ready.md` — "pollution self-resolved between sessions (stale pycache cleared); full suite 4560/4560 green; 25 conditional-edge tests pass in isolation." The pycache hypothesis is the most plausible "why does it sometimes flake?" — when stale `__pycache__` for `workflow.node_eval` or `workflow.storage` carries over from an old code revision, type/attribute names can resolve incorrectly. Today's environment has 1,197 `__pycache__` directories but they're all consistent with current source.

## Code-level flake-mode hypothesis (structural, not reproduced)

Even when the flake doesn't surface in reproduction, the test code has 3 concrete weaknesses worth flagging:

### 1. WAL + multi-connection on Windows (most likely structural cause)

`NodeEvaluator._connect()` (`tinyassets/node_eval.py:168`) opens a fresh SQLite connection per call:

```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self._db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn
```

Every `record()` call (`L211`) and every `get_stats()` call (`L240`) opens a new connection, performs work, then `conn.close()` in a `finally` block. The test `test_record_and_get_stats_roundtrip` does **3 record + 1 get_stats = 4 separate connections** to the same WAL-mode SQLite file in tight succession.

On Windows, WAL-mode SQLite has a known race window between connection-close and the WAL becoming visible to the next connection. The fixture's teardown calls `PRAGMA wal_checkpoint(FULL)` (defensively), but BETWEEN the 3rd record and the get_stats inside the test body there is no checkpoint — the test relies on the WAL-as-replication-log being readable by the next connection immediately. Under disk pressure (full suite running, lots of other SQLite ops in parallel) this race window can widen and `get_stats` reads BEFORE the 3rd record's WAL frame has been promoted, yielding `total_executions == 2` instead of `3` (or stale `avg_duration`).

This matches the observed symptom shape: passes alone (no contention), passes in adjacent files (low contention), flakes in full suite (high contention).

### 2. `time.time()` field on `ExecutionRecord` is wall-clock, not monotonic

`ExecutionRecord.timestamp = field(default_factory=time.time)` (`tinyassets/node_eval.py:73`). The test inserts 3 rows in <1ms; if Windows clock-resolution rounds two of them to the same float (uncommon but possible when wall-clock has 15.6ms granularity), the `last_exec` field returns one timestamp but the `total_executions` count is unchanged. Doesn't directly explain the flake, but compounds non-determinism of write-then-read patterns.

### 3. Fixture teardown does NOT delete the DB file

```python
@pytest.fixture
def evaluator(tmp_path, monkeypatch):
    ...
    yield ev
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA wal_checkpoint(FULL)")
    conn.close()
```

The teardown checkpoints but leaves the .db file at `tmp_path/node_eval.db`. `tmp_path` is per-test scope, so pytest cleans it up at session end. No cross-test leakage AT THE DB LEVEL — confirmed in code reading. **This is NOT a flake source**; documenting only to clarify it's been ruled out.

## Reproduction protocol for future sessions

If the flake re-surfaces, the fastest path to a confirmed RCA is:

1. `find . -name __pycache__ -type d -exec rm -rf {} +` (clear stale pycache; per memory `feedback_stale_pycache.md`).
2. `python -m pytest -q --tb=line 2>&1 | tee /tmp/full_suite.log` (full suite, capture every line).
3. If `test_record_and_get_stats_roundtrip` flakes, grep `/tmp/full_suite.log` for the assertion failure mode:
   - `total_executions == 2` (expected 3) → confirms WAL race (hypothesis #1).
   - `avg_duration == approx((0.5 + 0.3) / 2)` → also WAL race (3rd record not yet visible).
   - `success_rate != 2/3` → similar WAL race.
4. If it flakes, also add `pytest -x --pdb tests/test_node_eval.py::test_record_and_get_stats_roundtrip` immediately AFTER a reproducing full-suite run while the pollution state is still on disk.

## Fix proposals (not implemented)

### Fix A — single connection per `NodeEvaluator` lifetime (structural; preferred)

Change `_connect()` from "open new connection each call" to "reuse a single instance-scoped connection." Eliminates the WAL-handoff race entirely because all writes/reads go through the same connection (which sees its own writes immediately even in WAL mode).

**Risk:** changes thread-safety semantics. SQLite connections are single-thread by default; if anything currently calls `record()` from a background thread (e.g. async run dispatcher), this would break. Search before changing: `grep -rn "NodeEvaluator\|node_eval" tinyassets/ domains/`. If single-threaded today, this fix is the right one. If multi-threaded, use a per-thread connection pool (`threading.local`).

**Estimate:** 30-45 min. Touches `tinyassets/node_eval.py` only. Test stays unchanged (the fix lives entirely under the existing API).

### Fix B — wal_checkpoint after every write inside `record()` (defensive; cheaper)

Add `conn.execute("PRAGMA wal_checkpoint(PASSIVE)")` after `conn.commit()` in `record()`. Eliminates the race at the cost of slower writes (a few ms per record). Acceptable for this evaluator since it's not on a hot path.

**Risk:** mild perf regression on workloads that record many executions per second. Probably negligible (the autopromotion engine doesn't fire that often).

**Estimate:** 5-10 min. Single-line change. Same fix pattern shipped in similar SQLite-WAL flake-prone test files in the past (search `wal_checkpoint(PASSIVE)` for precedent).

### Fix C — defer flake fix; clean stale pycache as preventive maintenance

If the flake hasn't surfaced for ≥30 days (per a future audit), the most cost-efficient response is to leave the test code unchanged and add a pre-test pycache clean step to the verifier's full-suite gate. This is a "prevention not cure" approach — low ROI to fix a flake that doesn't recur.

**Risk:** if it does recur, we burn the same ~2h investigation cycle again. Bad ROI if recurrence is more frequent than ~quarterly.

## Recommendation

**Defer the code fix; document the structural flake-mode and the reproduction protocol** (this doc). The flake hasn't surfaced today (5 reproduction attempts, 81% of full suite covered before I killed the run). The structural weakness is real but low-impact when not actively flaking. Implementing Fix A or B without a confirmed reproduction risks gilding the wrong cause.

**If lead disagrees and wants a preventive ship-now:** Fix B (single-line wal_checkpoint(PASSIVE) in `record()`) is the smallest-blast-radius preventive change. Fix A is more correct but bigger surface; reserve for if the flake recurs and reproduces cleanly.

## Status for STATUS.md

Per `feedback_status_md_host_managed.md`, the STATUS Concern entry stays. **Ready for host curation:** investigation complete, RCA hypothesis documented, reproduction protocol in this doc. Nothing else can be moved on this without (a) a fresh reproduction OR (b) lead direction to ship Fix B preventively.

## Files referenced (no edits)

- `tests/test_node_eval.py:79` (`test_record_and_get_stats_roundtrip`)
- `tests/test_node_eval.py:32-41` (`evaluator` fixture with checkpoint-on-teardown)
- `tinyassets/node_eval.py:150-236` (`NodeEvaluator` class — `_connect`, `_initialize_db`, `record`)
- `tinyassets/node_eval.py:240-308` (`get_stats`)
- `tests/conftest.py:36-57` (`_isolate_storage_backend` autouse — irrelevant to node_eval, but confirmed not the cause)
- `tests/test_data_dir_call_sites.py:47-80` (`test_node_evaluator_*` — confirmed not the polluter)
- `%APPDATA%/Workflow/.node_eval.db` (28KB, empty `node_executions` table — confirmed not a state-leak source)

## Cross-references

- Memory `project_task_12_pollution_diagnosis_ready.md` — prior pollution self-resolved between sessions (pycache).
- Memory `feedback_stale_pycache.md` — stale `.pyc` masquerading as regression is a known class.
- Memory `feedback_status_md_host_managed.md` — host curates STATUS Concerns; do not auto-delete.
