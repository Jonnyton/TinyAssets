# Structural caps become usage limits

## Why

Plan item 6 of the approved primitives plan (founder, 2026-09-27; "limit
USAGE, not shape", 2026-08-30). Several limits bound what a user may build
rather than how much they spend:
- invoke_branch depth 5 (`TINYASSETS_INVOCATION_MAX_DEPTH`);
- 200 automations per universe;
- a 300s floor on interval and cron cadence, for both automations and
  schedules;
- 20 schedules and 20 subscriptions per owner;
- 64 components per agent definition.

Meanwhile a branch that `run_graph`s itself, paced just under the hourly run
caps, ran indefinitely (concern 2026-09-28, deleted by this change).

## What Changes

- **A rolling-day run meter.** Every run admission (`_engine_run_admit`, and
  therefore run_graph, automations and triggered runs) also counts the
  universe's runs over the last 24h against `RUN_DAY_LIMIT` (2000). Write and
  read rows both count; engine edits do not. The ledger keeps a day of rows,
  indexed by universe and time. The refusal names the day limit.
- **invoke_branch has no depth cap.** Each child run is charged to the
  universe's admission, whether blocking, async or by version, and bound to
  its run so it settles like any run. A run with no universe (the local
  daemon) is not metered. A blocking chain of live definitions runs in one
  thread, so before the next blocking child it checks that a quarter of the
  interpreter's recursion limit is still free, and stops by name if not
  (about 70 levels deep in practice). A RecursionError deeper down would be
  caught and reported by whichever layer it hit. The one depth bound left is
  physical: a BLOCKING version invoke waits on the child pool every universe
  shares while holding one of its threads, so it may nest only as deep as that
  pool has threads. `MAX_INVOKE_BRANCH_DEPTH` now only sizes the pool, and
  `TINYASSETS_INVOCATION_MAX_DEPTH` is retired.
- **Automations:** no 200-row ceiling, and no 300s interval or cron floor.
  Registering one (including a node's wake and an event wake) is charged as an
  engine edit. Every fire is charged as a run.
- **Schedules and subscriptions:** no per-owner count. The cadence floor is
  the tick loop's own period (10s). Registration through `schedule_branch` is
  charged as an engine edit, and every fire through
  `enqueue_universe_branch_run` is charged as a run. That path fails closed.
- **Agent definitions:** no count of components. The 256KB canonical-bytes
  bound stays. `MAX_LINEAGE_DEPTH` stays: it is a CHECK constraint of the
  stored lineage table, so lifting it means rebuilding an attribution table.
- The unused `NodeEnqueueBudget` threading in `graph_compiler.py` is removed.

## Impact

- Code: `engine_admissions.py`, `engine_mcp_server.py`, `graph_compiler.py`,
  `runs.py`, `automations.py`, `api/automations.py`, `api/runs.py`,
  `api/runtime_ops.py`, `scheduler.py`, `custom_agents.py`, `agent_runtime.py`.
- Storage: one new index on the admissions ledger. No migrations.
- Surface: refusal reasons `usage_limited`, `run_usage_limited:<cap>`, and the
  day refusal text. Cadences and depths that were refused are now accepted.
