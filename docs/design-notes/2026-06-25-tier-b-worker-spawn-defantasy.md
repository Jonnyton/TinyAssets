# Tier B worker-spawn de-fantasy scaffold

Date: 2026-06-25
Status: flag-gated scaffold; default-off
Branch: `claude/defantasy-tierb-soulloop`

## Context

Tier B of `docs/audits/2026-06-24-fantasy-architecture-residue-audit.md`
identified two production spawn paths that still privileged the fantasy daemon:

- `workflow/__main__.py` allowed only `--domain fantasy_author` to execute.
- `workflow/cloud_worker.py` default-spawned `python -m fantasy_daemon` for
  every universe.

`docs/design-notes/2026-06-03-soul-loop-dispatch-activation-plan.md` identified
the intended execution path: a universe with `soul.md` and a declared
`loop_branch_def_id` should run that branch through `workflow.runs.execute_branch`
instead of building a second runner. The existing implementation in
`fantasy_daemon/__main__.py::_try_execute_soul_loop` is gated by
`WORKFLOW_SOUL_LOOP_DISPATCH`, so this branch wires production spawning to that
dark path without changing the default.

This PR does not flip `WORKFLOW_SOUL_LOOP_DISPATCH` on.

## Assessment Of The Existing Dark Path

What is already correct:

- The flag defaults off via `_soul_loop_dispatch_enabled()`.
- The branch id is resolved through `_universe_loop_dispatch`, the same resolver
  used by the MCP submit path.
- A declared non-legacy loop runs through `execute_branch`, so run status,
  provider pumping inside the graph, in-node enqueue context, run records, and
  run-level completion/failure semantics come from the normal branch executor.
- Claimed child `BranchTask` rows still get first chance to run before the
  root soul loop, preventing the driver from starving its own queued children.
- Missing or invalid declared loop branches are handled as "cycle handled";
  the daemon logs loudly and does not silently fall back to the fantasy cycle.

What is not production-ready yet:

- There is no BranchTask lease or BranchTask finalization for the root soul
  loop because it is a root activation, not a claimed queue row. The relevant
  finalization is run-level `execute_branch` status.
- There is no claimed-task heartbeat/cancel observer for the root activation.
  The cloud supervisor heartbeat still exists, but node-level heartbeat/cancel
  semantics apply only to claimed BranchTasks.
- A souled universe with no loop declaration currently falls through to the
  legacy fantasy cycle in the daemon path. That is compatible with this
  scaffold's "declared loop only" routing, but it is a default-on blocker
  because the MCP path refuses `universe_loop_not_declared`.
- Loop-dispatch resolver exceptions currently return `False` from the daemon's
  `_try_execute_soul_loop`, which also falls through to the fantasy cycle. A
  default-on rollout needs fail-closed behavior for malformed or unreadable
  souled universes.
- `workflow/__main__.py` still delegates to `fantasy_daemon.DaemonController`;
  the runtime is not fully extracted. This branch only relaxes the non-fantasy
  gate when the flag is on and the universe resolves to a declared non-legacy
  soul loop.

## Activation Approach

The scaffold adds routing, not a new executor:

- `workflow/cloud_worker.py` now chooses `python -m workflow` only when
  `WORKFLOW_SOUL_LOOP_DISPATCH` is truthy and `_universe_loop_dispatch(universe)`
  returns a real non-legacy branch id.
- Flag off, no soul, no loop declaration, or the legacy fantasy loop all keep the
  existing `python -m fantasy_daemon` subprocess path and call shape.
- `workflow/__main__.py` accepts `--provider` so cloud-worker provider pinning
  remains valid when the generic module route is selected.
- `workflow/__main__.py` keeps rejecting non-fantasy domains unless the same
  flag-on declared-soul-loop condition is true.

The selected `python -m workflow` process still delegates into
`DaemonController`, so the existing dark `_try_execute_soul_loop` path is the
only soul-loop executor used by this branch.

## Staged Rollout Plan

1. Land this flag-gated scaffold with `WORKFLOW_SOUL_LOOP_DISPATCH` off in all
   production environments.
2. Run a local dry-run universe with `soul.md`, a declared `loop_branch_def_id`,
   and empty `effect_authority`.
3. Run the AGENTS.md Section 14 concurrency/load proof against cloud-worker and
   host-worker overlap, including pending child BranchTasks, producer pumping,
   restart/backoff behavior, and failure paths. This proof MUST cover signal
   handling for the `python -m workflow` subprocess: unlike the legacy
   `fantasy_daemon` entrypoint (which installs a SIGTERM handler that sets
   `_stop_event` for a graceful checkpoint flush — `fantasy_daemon/__main__.py`),
   `workflow/__main__.py` installs no SIGINT/SIGTERM handler. The supervisor
   stops subprocesses with `proc.terminate()` (SIGTERM) before `proc.kill()`
   (`cloud_worker.py`), so without a handler a supervisor-initiated restart
   exits rc=-15. The always-true consequence is that the graceful checkpoint
   flush is skipped — no handler runs before exit. The crash-accounting impact
   is path-dependent: on a supervisor *queue* restart `cloud_worker.py` forces
   `returncode = 0`, so `SupervisorState.record_exit` does not count it as a
   crash there; but on other supervisor-initiated SIGTERM paths the raw rc=-15
   is recorded as a crash and inflates backoff. Add a SIGTERM handler to the
   soul-loop entrypoint as part of this gate.
4. Get opposite-provider review of the code, tests, and the hardening assessment.
5. Enable the flag for one fresh dry-run universe only.
6. Run a post-rollout public canary through the real chatbot connector surface
   and record the rendered transcript/screenshot path.
7. Check post-fix real-user or canary evidence before broadening. If no real
   clean use is visible, leave a watch item instead of claiming default-on
   readiness.
8. Only after the above, consider changing the production default.

## Required Gates Before Default-On

- AGENTS.md Section 14 concurrency/load proof for worker overlap and restart
  safety.
- Post-rollout public canary through the live connector path.
- Opposite-provider review.
- Explicit reconciliation of the souled-but-no-loop behavior so daemon and MCP
  semantics do not diverge.

Until those gates are satisfied, `WORKFLOW_SOUL_LOOP_DISPATCH` remains an
opt-in flag and fantasy/soulless universes keep the current production default.
