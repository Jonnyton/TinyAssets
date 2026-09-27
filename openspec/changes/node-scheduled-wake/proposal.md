# A node can wake any of its owner's branches, now or not before a time

## Why

Founder, 2026-09-27: "a user could build a node agent with really any wake
behavior, its just another agent, or just another node". Plan item 3 of the
approved primitives plan.

A node can already ask for a run: `invoke_mcp_action('enqueue_branch_run')`. In
practice it cannot use that to build any wake behaviour:

- **It is off.** `TINYASSETS_NODE_ENQUEUE_ENABLED` is unset in every compose
  and deploy file in the repo.
- **It refuses the owner's own branches.** It accepts public targets only, and
  since 2026-09-26 everything is private by default.
- **It is structurally capped:** spawn depth 2, 50 enqueues per run, 500
  active queue rows, and 200 per lineage. A branch that reschedules itself
  stops on its third hop.
- **It has no delay.** "Wake me in ten minutes" is not expressible.
- **Nothing runs what it enqueues.** It appends `branch_run` rows to the
  epoch-1 file queue. The cloud daemon's only executor,
  `AssignedQueueConsumer`, skips every task without an `automation_id`
  (`_consumer_skip_reason`: `consumer_not_applicable`).

## What Changes

- `enqueue_branch_run(branch_def_id, inputs, not_before=<ISO> | delay_seconds=<int>)`
  stores a **one-shot automation** in the run's own universe, owned by the
  run's owner. The row uses the new trigger kind `once` and a stored
  `not_before`.
- The existing automation pump fires it once `not_before` has passed. Every
  run-time check an automation already has applies: owner admin, own home,
  authored branch, current serving provider, per-universe run admission, and
  the lease fence. After a run starts, the row retires itself. The row is
  in SQLite, so it survives a deploy. A run killed mid-flight is retried
  under a fresh key, and retries are bounded.
- **On by default.** The flag and the depth, per-run, queue and lineage caps
  are retired. What limits usage instead:
  - the per-universe run admission, which applies at fire time;
  - the existing per-universe count of pending automations, which applies at
    enqueue time.
  A branch that reschedules itself holds one pending row, so it is legitimate
  and metered.
- **The owner's own private branches are allowed.** The floor stays
  cross-user:
  - the universe comes from the run's trusted context only;
  - the owner is the bound principal, and that principal must be an admin
    whose home is this universe;
  - the branch must be one that owner authored.
- Owners see pending wakes in `read_graph target=automations` (kind `once`,
  with `not_before`), and can cancel one with the existing `delete`.

## Impact

Code:
- `tinyassets/graph_compiler.py`: the enqueue verb.
- `tinyassets/automations.py`: the `once` kind, the `not_before` column, and
  retire-after-run.
- `tinyassets/api/automations.py`: the projection.

Storage shape: the `trigger_kind` CHECK is rebuilt and a `not_before` column
is added.

The epoch-1 `branch_tasks` helpers stay for their other readers.
`invoke_branch`'s synchronous depth bound is untouched; it belongs to plan
item 6.
