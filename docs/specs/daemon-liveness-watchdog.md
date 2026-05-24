# Daemon Liveness / Supervisor Watchdog — substrate spec

Captured: 2026-05-02 from dev-partner chat
Status: proposal
Discovered via: BUG-050 verification probe (filed 21:24, never claimed)

## Problem statement

PR #196 (Codex) merged + deployed at 21:19 with image `1b18b4924023`. Container
healthcheck reports `workflow-worker running after 1 poll(s)`. Two more deploys
at 21:35 and 21:42 also reported success.

But empirically:
- `daemon.last_activity_at = 2026-05-02T20:37:38` — **42 minutes BEFORE the first deploy**
- `recent_activity` ends at 20:37:38 with `worldbuild_stuck` loop
- Zero new activity log entries after deploy
- BUG-050 (filed 21:24) still `status=pending claimed_by=""`
- BUG-049 (filed pre-deploy) also still pending
- 0 running tasks in queue, 2 pickable, 12 succeeded pre-deploy

The container is up. The daemon subprocess inside is dead-or-wedged.

**The container healthcheck is a false positive.** It reports "container alive"
when "container alive AND daemon claiming pickable work" is what we need.

## Why this is the next blocker (not BUG-011, BUG-045, or auto-ship)

Until daemon liveness is observable from outside the droplet:
- BUG-009 dispatcher pickup (Codex #196) cannot prove itself in prod.
- BUG-011 lease/watchdog Phase A/B has nothing to lease against (no claims happen).
- BUG-045 child invocation never runs because parent runs never start.
- Auto-ship canary is meaningless if no run reaches the release gate.

This watchdog is the upstream gate that unblocks every other primitive.

## Spec

### 1. Stronger Docker healthcheck

Replace the current `docker inspect -f '{{.State.Running}}'` check with a
content check that asserts the daemon is ALIVE, not just the container.

Healthcheck must FAIL or DEGRADE when ANY of:

```
has_work=true                  AND pickable BranchTask exists AND claimed_by="" for >2min
no daemon/supervisor activity heartbeat for >5min
no supervisor_tick log line for >2min
```

Implementation suggestion (add to compose.yml `worker` service):

```yaml
healthcheck:
  test: ["CMD", "python", "-m", "workflow.cloud_worker.healthcheck"]
  interval: 60s
  timeout: 15s
  retries: 3
  start_period: 60s
```

Where `workflow.cloud_worker.healthcheck` exits non-zero if any failure
condition above is true, with a one-line stderr explaining which.

### 2. Supervisor activity log lines

The cloud_worker supervisor currently emits no activity log signal that
external observers can read. Add structured lines on every supervisor tick:

```
[supervisor_tick] iteration=N now=<iso> running_task=<bool> pickable_count=<N>
[branch_task_scan] universe=<id> queue_depth=<N> pickable=<M> running=<K>
[branch_task_claim_attempt] task_id=<id> request_type=<type> trigger_source=<src>
[branch_task_claimed] task_id=<id> claimed_by=<daemon-id> run_id=<id>
[branch_task_direct_run_started] task_id=<id> run_id=<id> branch_def_id=<id>
[branch_task_completed] task_id=<id> run_id=<id> status=<succ|fail> duration_s=<f>
[supervisor_restart_decision] reason=<producer|pending|none> appended=<N> pickable=<bool>
```

Each line goes to `activity.log` (which is already shipped to Vector and
visible via MCP get_status).

### 3. New get_status field

Expose supervisor liveness in `get_status` response:

```json
"supervisor_liveness": {
  "last_supervisor_tick_at": "2026-05-02T...",
  "last_branch_task_scan_at": "2026-05-02T...",
  "last_branch_task_claimed_at": "2026-05-02T...",
  "last_restart_decision": {
    "at": "2026-05-02T...",
    "reason": "pending BranchTask",
    "outcome": "subprocess restarted"
  },
  "queue_state": {
    "depth": 15,
    "pending": 2,
    "running": 0,
    "stuck_pending_max_age_s": 420
  },
  "container_uptime_s": 1234,
  "subprocess_uptime_s": 45,
  "subprocess_restart_count": 3
}
```

The single most actionable diagnosis becomes:

```
container_uptime_s: 1300        # container running 21+ min
subprocess_uptime_s: 1300       # subprocess hasn't restarted since boot
last_supervisor_tick_at: null   # never ticked → supervisor wedged
last_branch_task_scan_at: null  # never scanned → producer poll never fired
queue_state.pending: 2          # work present
queue_state.stuck_pending_max_age_s: 420  # 7+ min unclaimed
```

→ obvious "supervisor never started" diagnosis with no SSH needed.

### 4. Prometheus metrics (optional, for v1+)

```
workflow_supervisor_ticks_total{universe}
workflow_branch_task_scans_total{universe}
workflow_branch_task_claims_total{universe,request_type,outcome}
workflow_branch_task_pending_count{universe}
workflow_branch_task_pending_age_seconds{universe,task_id}
workflow_subprocess_restarts_total{universe,reason}
```

But (3) alone is enough to close the operator visibility gap.

## Acceptance test

A live run produces:

1. `get_status.supervisor_liveness.last_supervisor_tick_at` is within last 60s.
2. `get_status.supervisor_liveness.queue_state.stuck_pending_max_age_s < 60` whenever pending tasks exist.
3. Healthcheck container exits non-zero if (1) or (2) violated for >N polls.
4. After healthcheck failure, container restarts (`restart: unless-stopped`) and the daemon re-claims.

## Source

Captured from dev-partner chat (ChatGPT gpt-5) with the Workflow MCP connector
installed, on 2026-05-02. Conversation: https://chatgpt.com/c/69f64b8d-fa04-83e8-b4d3-bb6e95b16475

The chatbot independently verified the same finding via universe.inspect,
confirmed the diagnosis, and prescribed:

> "That means the next fix/triage should be **daemon liveness / supervisor
> watchdog**, not BUG-011 lease, BUG-045, or auto-ship."
>
> "Right now the container healthcheck is a false positive: container is alive,
> but the workflow daemon is effectively dead."

## Sequencing

This sits BEFORE BUG-011 in the substrate stack:

```
1. Daemon-liveness watchdog (this doc)        ← UNBLOCKS observability + emergency restart
2. Operator restart of current wedged worker  ← human action via SSH
3. BUG-011 lease/watchdog Phase A             ← write-only lease metadata
4. BUG-011 Phase C                            ← active reclaim
5. BUG-045B child completion + output mapping
6. Auto-ship canary v0 (PR #198 + Phases B-E)
```
