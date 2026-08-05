# The drain's root cause, and three rows I destroyed finding it

`current: 2026-08-05 23:15Z`. Live sha `e8e8cf35`, `/mcp` 200, canary green.

## Verified root cause

`deploy-prod.yml:1140` sets `TINYASSETS_SOUL_LOOP_DISPATCH='on'`
unconditionally. `cloud_worker._daemon_module_for_universe` then routes any
universe declaring a non-legacy loop to `python -m workflow`.

**The `workflow` module exists nowhere** — not in the image
(`No module named workflow`), not in the repo (`find_spec('workflow') is
None`, no package under any path). The flag enables a route whose
implementation was never shipped.

Live evidence, all four workers, every cycle before the fix:

```
cloud_worker: starting supervisor universe=/data/u-01kxm1vszd8hwp7em418asq8h9
cloud_worker: runtime registered worker_id=codex-1 provider=codex ...
/opt/venv/bin/python: No module named workflow
cloud_worker: subprocess exited rc=1 (crash); spawns=1 crashes=1
```

`subprocess_alive` was never true, so `compatible_worker_count` stayed 0.

**Why it stayed hidden:** the fleet was serving a different universe.
`/data/.active_universe` did not exist, so `_resolve_universe` fell through to
"first directory with PROGRAM.md or soul.md" — a legacy universe, which routes
to `fantasy_daemon` and starts fine. Pointing the fleet at the founder universe
is what exposed a crash that had presumably always been there.

## Three rows destroyed

PR #2355 stopped the crash-loop by falling back to `fantasy_daemon`.
`compatible_worker_count` went 0 -> 3 and `awaiting_compatible_capacity` 4 -> 0,
which read as success. In the same payload, `failed` went 0 -> 3.

`failed` is in `_TERMINAL_STATUSES` (`branch_tasks_v2.py:105`); `finish()`
terminalizes it (`:415-433`); selection requires `status == "pending"`
(`dispatcher.py:395-397`); recovery only handles expired leases (`:436-457`).
**Shipping `workflow` later will not revive them.**

Cross-family review (reject) also found:

- **Compatibility was falsely asserted.** The descriptor advertises generic
  `operator_request_v1` (`cloud_worker.py:363-391`); claim validation never
  checks legacy-versus-soul-loop semantics (`branch_tasks_v2.py:841-910`). The
  worker told the queue it could do work it could not do.
- **State contamination risk.** The legacy child runs against the same universe
  and is coupled to SqliteSaver, dashboard events, knowledge graph, heartbeat.
  `checkpoints.db` 0 -> 20480 bytes is durable mutation a later correct
  executor can inherit.

**Not established:** *why* those three failed. I claimed the legacy daemon
cannot execute soul-loop slices; I never verified it, and the rows are not
route-typed. Treat the cause as unknown.

## Current posture (#2356, deployed)

Workers self-quarantine when their universe declares a non-legacy loop and
`workflow` is absent — same shape as the dead-auth gate. No claim, loud reason,
lifts by itself when the module ships. Live now:

```
awaiting_compatible_capacity = 2   reason no_live_compatible_worker
compatible_worker_count = 0        (correctly zero)
diagnostics = both rows listed
```

A visible stall, with the two survivors recoverable.

## Next, in order

1. Ship the `workflow` module, or decide the soul-loop route is abandoned and
   remove the flag from `deploy-prod.yml:1140`.
2. Only afterwards, requeue the three lost rows. Requeuing before a correct
   executor exists would destroy them again.
3. Determine why the three actually failed before assuming route mismatch.

## The lesson

Twice in one session I shipped a change that made a metric move and called it
progress. The second time destroyed user work, twenty lines from a comment in
the same file explaining why a visible stall is safer than terminalizing
admissible work — and hours after I had refused this exact pattern, correctly,
in another lane.

A capacity number going up is not the system working. The lifecycle counts in
the same payload are the check, and they were right there.
