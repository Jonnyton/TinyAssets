## Context

PR #1844 made OpenSpec WIP measurable and bounded, but the host still had to
start a fresh session after every merged slice. The existing
`scripts/fleet_supervisor.py` keeps a configurable provider floor alive from a
static brief queue; its default four Codex plus four Claude lanes optimizes
utilization, not queue contraction. It does not re-audit OpenSpec, enforce one
PR per worker, interpret terminal outcomes, or stop on repeated failure.

The correction is a persistent controller with disposable workers. The
controller retains only compact run state. Each worker gets fresh context and
owns exactly one delivery attempt.

## Goals / Non-Goals

**Goals:**

- Run unattended for a bounded workday using subscription-authenticated Codex
  or Claude CLI workers.
- Keep exactly one drain worker active at a time in v1.
- Make one merged and archived slice the only success that advances immediately
  to another worker.
- Persist enough state to monitor, stop, resume, and avoid immediate repeats of
  blocked targets.
- Fail closed on malformed results, repeated failures, missing CLIs, or
  unverified completion.
- Give the host one command to start and separate status/stop commands.

**Non-Goals:**

- Maintain a provider utilization floor or parallel fleet.
- Automatically edit STATUS, reap claims, merge PRs, archive changes, or decide
  PLAN/P0 priority inside the controller process.
- Bypass repository review, CI, permissions, or opposite-provider gates.
- Guarantee useful work exists; an honest idle state is preferable to invented
  work.
- Replace `peer_agent.py`, `openspec_flow.py`, or `fleet_supervisor.py`.

## Decisions

### 1. Sequential fresh workers, not one long implementation context

`openspec_drain_supervisor.py run` invokes one blocking `peer_agent.py` process,
parses its final result, persists state, then decides whether to dispatch again.
Default concurrency is permanently one in v1.

Alternative: give one Codex goal “finish everything.” Rejected because its
context and task scope grow across slices, reproducing the reported multi-day
stall.

Alternative: reuse the fleet supervisor's provider floors. Rejected because a
floor optimizes occupancy and can burn both subscriptions while all useful work
is blocked.

### 2. Fixed terminal result contract

The last non-empty worker line must be:

`DRAIN_RESULT: <MERGED|PARTIAL|BLOCKED|NO_CANDIDATE|FAILED> <target-or-dash> <PR-or-dash>`

The marker must be the one final non-empty line. Template/placeholder lines,
lines containing `|`, multiple markers, and `[peer_agent] ERROR` blocks are
invalid. Only controller-verified `MERGED` increments the completed-slice count
and triggers an immediate next worker. `PARTIAL` means the PR merged but
sync/archive or STATUS foldback remains. The first `PARTIAL` records the resume
target and triggers one fresh worker without counting a slice. Every repeated
same-target `PARTIAL` consumes a failure strike and waits the idle interval, so
persistent foldback debt cannot consume workers until the runtime deadline.
`BLOCKED` and `NO_CANDIDATE` wait the configured idle interval. `FAILED` or a
malformed/missing marker increments consecutive failures; the controller stops
at the configured failure limit.

The worker prompt requires evidence that the PR merged, the OpenSpec delta was
synced/archived when complete, and the STATUS row was retired. The controller
does not trust prose as success: for `MERGED` or `PARTIAL`, it calls
`gh pr view <PR> --json state,mergedAt` and accepts progress only when GitHub
reports `MERGED`, the PR belongs to the controller repo's origin, and its merge
time is not older than the run.

Alternative: infer success from arbitrary final text. Rejected as too fragile
for unattended operation.

### 3. Persistent untracked run directory

Each run owns `state.json`, `supervisor.log`, worker prompts/results, a lock
file, and a `supervisor.stop` file under a configurable output directory. State
writes use atomic replacement. A second controller refuses a live lock. Explicit
recovery checks the recorded PID and refuses to replace a lock whose controller
is still live.

The state records start/deadline, one fixed provider/model, one exact
`drain-<run-id>` claim identity, slice/failure counters, last/resume target, and
a bounded recent-block list that is included in subsequent prompts so a
workday does not retry one blocker endlessly. Every replacement worker must
resume and finish a claim held by that exact run identity before selecting a
different target. This is not stale-claim reaping: `openspec_flow.py` already
allows the same identity to re-check its own target.

### 4. Budgets are terminal safety controls

Required finite controls are `--hours`, `--max-slices`, `--worker-timeout`,
`--max-failures`, and `--idle-minutes`. Provider and optional model are fixed
for the entire run rather than alternated. Defaults target an eight-hour day,
eight merged slices, ninety minutes per worker, two consecutive failures, and a
thirty-minute blocked/idle wait. A stop file ends the loop between workers.

Idle waiting polls the stop file at least every five seconds and never sleeps
beyond the remaining deadline. The supervisor exposes a single-pass `--once`
mode for acceptance tests and cautious first use.

`peer_agent.py` exit 127 (CLI unavailable) stops immediately. Timeout or a
malformed worker result consumes the normal failure budget. A provider
rate-limit/authentication-shaped error waits the idle interval; after three
consecutive free transient retries, each additional transient consumes a
failure strike. Bare words such as `authority` do not qualify as authentication
errors. A repeated same-target `PARTIAL` also consumes a strike and idles.

### 5. Worker selection remains repository-governed

The generated worker brief requires current-main orientation, OpenSpec audit,
claim/admission checks, STATUS/worktree discipline, one concrete acceptance
contract, tests, independent review when required, PR merge, spec sync/archive,
and foldback. It forbids new umbrella changes and more than one PR.

The brief includes the run's fixed claim identity. If STATUS already contains a
claim owned by that identity, the worker must resume that target before
selecting another. A timed-out worker therefore hands its lane to the next
fresh context instead of wedging the rest of the workday.

Legacy oversized changes may be drained only as a concrete recovery slice of at
most 12 unchecked tasks. The worker must not mechanically fan out child changes
or silently steal a live claim. It may reap only a claim that satisfies the
existing stale-claim policy.

The worker receives recent blocked targets and must select another candidate
when possible. If none is safe, it returns `NO_CANDIDATE` or `BLOCKED` rather
than inventing work.

### 6. Drain workers get a bounded coordination preflight

The worker still follows the project session ritual, but the global
`worktree_status.py` scan is capped at 90 seconds for this controller-launched
role. A timeout is logged and the worker proceeds only by creating a clean
current-main worktree with `_PURPOSE.md`, running exact claim/collision checks,
and making no edits in the stale/dirty primary checkout.

This exception is narrow: it prevents the observed three-minute inspector hang
from wedging every disposable worker without weakening file-claim authority.

### 7. Safety is governance plus CI, not a local sandbox

On this Windows host the Codex shim injects approval/sandbox bypass and Claude
write workers use `--dangerously-skip-permissions`. V1 safety therefore rests
on a clean purpose-named worktree, exact claims, one-PR scope, finite budgets,
independent review, required CI, GitHub auto-merge, controller-side merge
verification, preserved artifacts, and stop/failure controls. The runbook must
state this plainly.

Alternative: claim the peer CLI sandbox contains writes. Rejected because it is
false in the deployed host configuration and would create a misleading safety
argument.

## Risks / Trade-offs

- **Workers can return a false `MERGED` marker.** → Require the brief to verify
  GitHub merged state, then independently verify PR state in the controller and
  preserve the result artifact; exact-diff review remains part of each lane.
- **A timeout leaves a live same-day claim.** → One exact identity per run; the
  next fresh worker resumes that identity's claim before selecting new work.
- **A merged PR can leave foldback debt.** → `PARTIAL` preserves progress and
  routes one next worker to finish the same target; each repeated same-target
  `PARTIAL` consumes a failure strike and idles.
- **Blocked polling can still spend subscription calls.** → Default to a
  30-minute idle interval, include a recent-block list, and expose stop/status.
- **Legacy oversized recovery can become hidden scope growth.** → Limit one
  worker to at most 12 unchecked tasks and one PR; no mechanical child fan-out.
- **A CLI process can hang.** → `peer_agent.py` enforces the finite worker
  timeout; the controller kills the launcher process tree on its outer timeout,
  bounds post-kill pipe collection, counts timeout as failure, and stops at the
  limit.
- **A controller crash can leave a lock.** → Persist PID/start metadata and
  require explicit stale-lock recovery with a Windows process-handle liveness
  check rather than console-signal probing or silently starting twice.
- **One worker underuses available subscriptions.** → Intentional v1 trade-off;
  raise throughput by shorter verified slices before considering concurrency.
- **Write workers are not OS-sandboxed on this host.** → Make that explicit;
  constrain authority through worktree/claim/PR/CI/budget controls instead.

## Migration Plan

1. Land the supervisor, tests, policy, and runbook disabled by default.
2. Run `--once` with Codex and inspect the preserved worker result.
3. Run a bounded two-hour/two-slice session.
4. If clean, use the eight-hour defaults and compare merged slices, failures,
   active WIP, and unchecked tasks before/after.
5. Rollback is stopping the controller and reverting the tooling commit; it has
   no product data migration.

## Open Questions

- Whether two-provider concurrency is justified after two weeks of sequential
  cycle-time evidence.
- Whether a future controller should prepare and garbage-collect worktrees
  itself instead of delegating lane setup to each worker.
