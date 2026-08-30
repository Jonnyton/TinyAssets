# Codex review — last_activity_at derived from the runs ledger (branch `claude/activity-signal`)

Dispatched 2026-08-30 via `python scripts/peer_agent.py codex --prompt-file <brief>` on Codex's own budget. Round 1 pinned to 5eab19b1 (ADAPT); the fold is bda62f73; round 2 appended below when it lands.

## Round 1 (5eab19b1): ADAPT

Review pinned to requested base `0ac34796` and HEAD `5eab19b1`. `origin/main` advanced during review, so I did not use its later value. No worktree files were modified.

All verification: 2026-08-29 America/Los_Angeles, Windows NT 10.0.26200, Python 3.14.3.

### 1. Correctness — DISAGREE_EVIDENCE

The exact actor predicate prevents ordinary cross-universe and user-principal leakage: [`runs.py:1489`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:1489) filters `actor = "universe:<udir.name>"`, constructed at [`universe.py:932`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:932). My temporary-DB matrix returned `None` for `universe:u2` and `user:p1` while inspecting `u1`.

But there are three false-positive paths:

- `actor` and authoritative execution scope `queue_universe_id` are independent arguments at [`runs.py:786`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:786) and [`runs.py:793`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:793), inserted without an equality invariant at [`runs.py:813`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:813). A completed row with `actor="universe:u1", queue_universe_id="u2"` raised `u1`’s activity timestamp in my reproduction.
- Every new run is stored as `queued` with `started_at=_now()` at [`runs.py:815`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:815). The new unqualified `COALESCE(finished_at, started_at)` therefore counts queued-but-never-started runs. Reproduced: a bare `create_run` made a previously untouched universe fresh.
- Numeric future epochs are accepted and returned. `_staleness_bucket` treats negative age as fresh at [`universe.py:1037`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:1037). Reproduced with `finished_at=now+86400`.

What I ran: `python -` temporary-DB adversarial matrices covering other actor, user actor, mismatched `queue_universe_id`, queued, future, garbage, and huge timestamps.

### 2. Failure modes — DISAGREE_EVIDENCE

- Missing DBs are safe and do not create files: [`runs.py:1484`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:1484) and [`automations.py:363`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/automations.py:363). The committed test confirms this.
- The known `initialize_runs_db` race is avoided directly: the new run reader deliberately does not call it. However, its “read” connection still executes `PRAGMA journal_mode=WAL` with a 30-second timeout at [`runs.py:91`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:91).
- Worse, every automation read executes schema DDL and migrations at [`automations.py:370`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/automations.py:370), despite being a status read.
- Under exclusive locks, both lookups took **33.004 seconds** locally. The runs lookup returned `None`; automation raised `OperationalError`, later swallowed at [`universe.py:963`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:963). Because `_last_activity_at` invokes them sequentially at [`universe.py:1009`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:1009) and [`universe.py:1013`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:1013), the inferred worst case is roughly 66 seconds—well beyond the canary’s 20-second request timeout.
- Malformed run text becomes silently absent: `float(row["ts"])` at [`runs.py:1498`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:1498) escapes its local SQLite-only catch, then is swallowed by [`universe.py:935`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:935).
- A huge numeric epoch reaches `datetime.fromtimestamp` outside that catch at [`universe.py:942`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:942). Reproduced: `1e300` raised `OverflowError`, turning the public read into an error.
- Malformed automation ISO strings are skipped; timezone-naive strings are silently interpreted as UTC at [`universe.py:975`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:975).

What I ran: `python -` with exclusive SQLite locks against both real stores; adversarial timestamp matrix. The lock run measured 33.004 seconds per lookup.

### 3. Cost — DISAGREE_EVIDENCE

The runs query scans all runs on every universe status read. It filters by `actor` and aggregates an expression at [`runs.py:1489`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:1489), but the schema only indexes branch and status at [`runs.py:279`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:279). There is no actor, universe, finished-time, or expression index.

SQLite bytecode showed `Rewind` followed by `Next`, confirming a complete table walk. With 100,000 rows, ten local reads had a median of **10.58 ms**. `read_graph target=graphs` calls this once per universe at [`universe.py:1760`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:1760), so its work is `universes × total runs`.

The automation lookup is indexed by universe, but materializes every historical—including retired—automation in Python.

The new query does **not** affect canonical `get_status`: dispatch sends `target=status` to `_get_status_impl`, while only `target=graph` enters universe inspect at [`universe_server.py:505`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/universe_server.py:505).

What I ran: `python -` using the real initialized schema, `EXPLAIN`/`EXPLAIN QUERY PLAN`, and a 100,000-row benchmark.

### 4. Tests — DISAGREE_EVIDENCE

Running the four new tests against the exact base function from `0ac34796` produced:

| New test | On base | Does it fake its evidence? |
|---|---:|---|
| `uses_run_ledger_when_newer_than_files` ([line 226](/C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:226)) | RED | No stub; real runs DB APIs, though it directly supplies the expected terminal timestamp. |
| `ignores_run_for_different_universe_actor` ([line 251](/C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:251)) | GREEN | No stub, but regression-vacuous: base ignores every run. |
| `uses_automation_last_finished_at` ([line 278](/C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:278)) | RED | Effectively yes: it constructs the exact `last_finished_at` roll-up value at [line 305](/C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:305), bypassing the real claim/finish/refusal lifecycle. |
| `file_based_value_survives_missing_dbs` ([line 316](/C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:316)) | GREEN | No stub, but regression-vacuous. |

No test covers queued rows, mismatched `queue_universe_id`, user actors, future/huge timestamps, malformed values, lock latency, refused attempts, query plan, or the public `read_graph` path.

What I ran:

- `python -m pytest tests/test_universe_server_telemetry.py -q` → `26 passed`.
- A `python -` harness extracted `_last_activity_at` from `git show 0ac34796:tinyassets/api/universe.py` and ran each new test → `RED, GREEN, RED, GREEN`.

### 5. Semantics — DISAGREE_CONCERN

Successful automation/schedule execution should count. Queuing and refusal should not.

The canary explicitly claims to prove “actual work” at [`last_activity_canary.py:9`](/C:/Users/Jonathan/Projects/wf-activity-signal/scripts/last_activity_canary.py:9), while the worker docstring distinguishes “last did something” from process heartbeat at [`universe.py:1314`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:1314). Supervisor heartbeat has its own signal in the watchdog spec at [`daemon-liveness-watchdog.md:69`](/C:/Users/Jonathan/Projects/wf-activity-signal/docs/specs/daemon-liveness-watchdog.md:69).

A refused automation updates `last_finished_at` through [`automations.py:538`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/automations.py:538); rate-limit and authority refusals call that path at [`automations.py:1291`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/automations.py:1291) and [`automations.py:1315`](/C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/automations.py:1315). My real `claim_attempt` → `finish_attempt(status="refused")` reproduction made the universe fresh despite no run existing.

That is control-plane activity, not node execution. Counting it can keep the uptime canary green indefinitely while every requested automation is refused.

ADAPT — remove the automation-row fallback; query authoritative `queue_universe_id` for actually-started/non-refused runs; reject non-finite, non-positive, and future timestamps; use a short-timeout read-only SQLite connection; add an indexed `(queue_universe_id, status, finished_at)` access path; and add queued, scope-mismatch, refused, corrupt/future, locked-DB, query-plan, and public-surface tests.
## Round 2 (bda62f73): ADAPT — three items

Verification environment: 2026-08-29, Windows 11 build 26200, PowerShell, Python 3.14.3, SQLite 3.50.4. `HEAD=bda62f737fab...`; merge-base `0ac34796ea97...`; worktree remained clean.

1. **AGREE**

The automations-store source is gone. `_last_activity_at` combines only legacy heartbeat files and the runs ledger; there is no executable `AutomationStore`/`last_finished_at` reference in either canonical or packaged `universe.py` ([universe.py:981](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:981)). Canonical and packaged mirrors are byte-identical.

The refusal test uses the real store methods: `claim_attempt`, followed by `finish_attempt(status="refused")` ([test:351](C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:351)). The latter genuinely updates `automations.last_finished_at` regardless of outcome ([automations.py:524](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/automations.py:524)). It goes RED on 5eab19b1 because that revision reads the resulting fresh automation timestamp.

Commands:

```powershell
rg -n "latest_automation_activity|AutomationStore|last_finished_at" tinyassets/api/universe.py packaging/.../api/universe.py
python -m pytest -q tests/test_universe_server_telemetry.py
```

Result: `33 passed`.

2. **DISAGREE_EVIDENCE**

The scope predicate is exactly `queue_universe_id = ? AND status != ?` ([runs.py:1533](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:1533)). SQLite equality does not match the 1,729 supplied `NULL` rows. I treated the 2026-08-30 production counts as supplied evidence; they could not be independently queried from this 2026-08-29 environment.

The `interrupted` edge is not acceptable for an “actual work” signal. `recover_in_flight_runs` changes both `queued` and `running` directly to `interrupted` and stamps `finished_at=now` ([runs.py:3993](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:3993)). Therefore an enqueue that never reached a worker becomes fresh on server restart.

`runs.started_at` is creation time ([runs.py:794](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:794)); the table has no dequeue/execution-start timestamp or transition history. Merely having `run_events` is not authoritative because pending events are written synchronously before worker submission ([runs.py:2157](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:2157)).

The conservative, current-schema predicate is:

```sql
queue_universe_id = ?
AND status NOT IN ('queued', 'interrupted')
```

That avoids false freshness but omits genuinely executed interrupted runs. Counting those precisely requires an authoritative `execution_started_at`/`dequeued_at` field or transition ledger. Add a regression using real `create_run → recover_in_flight_runs`.

Command:

```powershell
rg -n "recover_in_flight_runs|RUN_STATUS_INTERRUPTED|started_at" tinyassets/runs.py
```

3. **AGREE**

The helper opens `file:...?mode=ro` with `uri=True`, `timeout=2.0`, issues no WAL pragma, and returns `None` on `sqlite3.Error` ([runs.py:1530](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:1530)).

The lock test creates a genuine blocking condition using exclusive locking mode, `BEGIN IMMEDIATE`, and an uncommitted update ([test:458](C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:458)).

Commands and results:

```powershell
python -m pytest -q --durations=3 tests/test_universe_server_telemetry.py::test_last_activity_runs_lookup_bounded_under_exclusive_lock
```

Current: `2.47s call`, pass. Differential against 5eab19b1: `elapsed=32.1859s`, RED against `<5s`. Thus the test demonstrably blocks the old reader and the new bound holds.

4. **AGREE**

Placement after the column migration is correct ([runs.py:440](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:440), [runs.py:475](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:475)):

- Fresh DB: upfront schema creates the column; post-schema index succeeds.
- Pre-migration DB: `ALTER TABLE` adds the column before index creation.
- Production-like/current DB: column already exists; idempotent index creation succeeds.

A direct SQLite simulation exercised all three, including a production-like 1,849-row table with 1,729 `NULL` scopes. All initialized without raising; the legacy row survived and the index appeared. No supported migration path newly raises. Read-only, locked, corrupt, or disk-full databases may still make this writer raise, as expected.

Command: inline Python calling `initialize_runs_db` against fresh, legacy-without-column, and production-like temp databases. Results: `fresh True True`, `legacy True True`, `prodlike 1849 True`.

5. **DISAGREE_EVIDENCE**

The ledger hygiene is correct: non-finite, non-positive, more than 300 seconds future, and platform conversion failures are contained ([universe.py:922](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:922)). The runs wrapper also catches all helper exceptions before the public read ([universe.py:965](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:965)).

However, the complete derivation can still raise through the public read. The legacy `status.last_updated` path catches only `ValueError`; UTC normalization can raise `OverflowError` ([universe.py:899](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:899)).

2026-08-29 probe:

```python
_last_activity_at(udir, {"last_updated": "9999-12-31T23:59:59-23:59"})
```

Result: `OverflowError: date value out of range`. The corresponding year-1 positive-offset case also raises. This needs containment—and preferably the same future-timestamp hygiene—before claiming the public derivation cannot raise.

Separately, `float(row[0])` lies outside the helper’s `sqlite3.Error` block ([runs.py:1547](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/runs.py:1547)); malformed text can make the helper itself raise `ValueError`, although the public wrapper currently contains it.

6. **DISAGREE_EVIDENCE**

Current suite: `33 passed`. Overlaying the current tests onto an archived 5eab19b1 tree produced seven RED and four GREEN:

| New test versus 0ac34796 | On 5eab19b1 | Assessment |
|---|---:|---|
| run ledger newer than files | GREEN | Baseline feature; matching actor also works under old query. |
| different-universe scope | GREEN | Weak: actor and scope are both different, so it does not prove which column scoped the query. |
| queued never started | RED | Old query counts enqueue-time `started_at`. |
| queue scope versus actor mismatch | RED | Old actor query credits the wrong universe. |
| refused automation attempt | RED | Real claim/finish lifecycle exposes old automation fallback. |
| safe epoch bad values | RED | Helper absent. |
| huge run timestamp | RED | Old public derivation raises `OverflowError`. |
| exclusive-lock bound | RED | Old call takes 32.19 seconds. |
| indexed query plan | RED | Plan is unindexed `SEARCH runs`. |
| `read_graph` public surface | GREEN | Matching actor already returned the timestamp. It also calls `_action_inspect_universe` directly, not `read_graph`. |
| missing DB preserves files | GREEN | Baseline fail-soft behavior. |

Two tests overclaim:

- The “different universe scope” test does not discriminate queue scope from actor scope; the mismatch test does.
- The purported public-surface test ([test:533](C:/Users/Jonathan/Projects/wf-activity-signal/tests/test_universe_server_telemetry.py:533)) invokes the private action at line 557. It does not execute the actual router at [universe_server.py:462](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/universe_server.py:462).

An ad-hoc real `universe_server.read_graph(target="graph", graph_id="u1")` probe did return the ledger timestamp with sub-microsecond delta, so the implementation works; the committed test does not guard it.

Differential command: archived `5eab19b1` to a system-temp directory, overlaid the current test file, then ran the eleven node IDs. Result: `6 failed, 4 passed`; the separately run lock test supplied the seventh failure.

7. **AGREE**

The plan uses `idx_runs_scope_status_finished`:

```text
SEARCH runs USING INDEX idx_runs_scope_status_finished (queue_universe_id=?)
```

The 1,729 `NULL`/other-scope rows are not scanned for a single universe lookup. However, `MAX(COALESCE(finished_at, started_at))` cannot early-exit from this index, and `status !=` only permits efficient use of the leading scope column. Cost is therefore linear in runs belonging to the requested universe, not total fleet runs.

Additionally, `read_graph target=graphs` loops over every visible universe and invokes liveness separately ([universe.py:1718](C:/Users/Jonathan/Projects/wf-activity-signal/tinyassets/api/universe.py:1718)), adding one read-only connection/query per visible universe. That list surface is O(universes + scoped runs across them); single-graph inspection remains one scoped query. This is acceptable at the supplied scale but should not be described as constant-time.

VERDICT: ADAPT bda62f73 — exclude or authoritatively distinguish queued-origin `interrupted` rows and test the real recovery lifecycle; contain legacy file/status timestamp overflow; make the public-surface test call the actual `read_graph` router.
## Round 3 (767ba9d4): ADAPT — one blocker (admission-failed runs counted), two founder notes; cap reached

Review context: 2026-08-29 20:27 PDT; Windows 11, Python 3.14.3, SQLite 3.50.4. `HEAD=767ba9d4`, merge-base `0ac34796`; worktree remained clean.

1. **DISAGREE_EVIDENCE** — The claimed predicate, guarded `float(row[0])`, and connect-failure-safe close are present at `tinyassets/runs.py:1553`. The interrupted lifecycle regression passes. However, the predicate still counts a run that fails provider admission before execution:

   - `tinyassets/runs.py:3319` transitions `queued → failed` when admission raises, before worker submission.
   - `tinyassets/runs.py:1557` admits that `failed` row as activity.
   - `scripts/last_activity_canary.py:146` consequently classifies the fresh timestamp as success.
   - Command: inline lifecycle probe patching `prepare_foreground_run_provider` to raise, then calling `execute_branch_async(..., _enqueue_universe_id="u1")`, public `read_graph(target="graph", graph_id="u1")`, and `classify_freshness(...)`.
   - Result: `run_status=failed`, `Provider authority admission failed: refused before execution`, public `staleness=fresh`, `canary_exit=0`.

   Thus “every other status means the run actually ran” is false, and the canary can still report actual work when none occurred.

2. **AGREE** — Parse and UTC normalization are jointly guarded at `tinyassets/api/universe.py:915`; future hygiene remains at line 923. Exact probes returned:

   - `9999-12-31T23:59:59-23:59 => None`
   - `0001-01-01T00:00:00+23:59 => None`

   Both regressions at `tests/test_universe_server_telemetry.py:188` and `:208` pass.

3. **AGREE** — The public-surface regression calls `tinyassets.universe_server.read_graph(target="graph", graph_id="u1")` at `tests/test_universe_server_telemetry.py:639`; router dispatch is exercised at `tinyassets/universe_server.py:510`. Test passes.

4. **AGREE** — The different-scope regression at `tests/test_universe_server_telemetry.py:294` keeps `actor="universe:u1"` and changes only `queue_universe_id`; it passes.

Verification:

- Focused regressions: `5 passed`.
- `python -m pytest -q tests/test_universe_server_telemetry.py` → `36 passed`.
- `python -m pytest -q tests/test_last_activity_canary.py` → `34 passed`.
- Exact final-query EXPLAIN → `SEARCH runs USING INDEX idx_runs_scope_status_finished (queue_universe_id=?)`.
- Malformed timestamp row and connect-time `OperationalError` probes both returned `None`.
- `python -m ruff check ...` → passed.
- No activity-signal raise-through remains in the exercised public-read paths.

Founder notes, non-blocking:

- The committed EXPLAIN test at `tests/test_universe_server_telemetry.py:601` still explains the old `status != ?` query, not the final `NOT IN (?, ?)` predicate, although the exact final query independently used the intended index.
- Legacy heartbeat-file mtimes at `tinyassets/api/universe.py:899` retain their pre-existing lack of the five-minute future guard.

VERDICT: ADAPT 767ba9d4
## Disposition: shipped as PR #2706 (head 462e8725, rebased on 9b15dd27). Rounds 1–2 folded and re-reviewed; the round-3 blocker (admission-refused runs counted as work) was folded as a positive allowlist `status IN ('running','completed')` WITHOUT a fourth review, per the three-round rule, and disclosed in the PR body. Founder notes carried: the ledger has no execution-start timestamp, so `resumed`/executed-then-failed runs are not counted either; `read_graph target=graphs` costs one scoped query per visible universe.
