---
incident_date: 2026-06-25
short_name: dispatcher-double-claim-wedge
severity: p1
time_to_recovery_minutes: 30
applied_by: claude-code-opus-4.8 (session c160dea2)
---

# Incident: dispatcher wedged — blanket startup recovery double-claims tasks; dead provider auth

The community patch loop had produced **zero terminal successes since ~Jun 3**
(~3 weeks). Discovered during a post-deploy connector sweep, not by an alarm.

## Symptoms

`read_graph target=status` against live `https://tinyassets.io/mcp`:

- `supervisor_liveness.queue_state`: `depth=5623, pending=19, running=0,
  succeeded=2476, failed=3128, stuck_pending_max_age_s=851`
- warning: `stuck_pending: oldest pending task is 851s old (threshold 120s)`
- 4 worker containers all `Up (healthy)` — so NOT idle workers
- worker logs: the **same** task (`bt_…d7502b5a`) claimed + executed by
  `workflow-worker`, `worker-claude-1`, `worker-claude-2`, AND `worker-codex-2`
  in sequence; repeated `Invalid transition failed -> succeeded` /
  `failed -> failed` exceptions in `_finalize_claimed_task`; `crashes=5 consec=3`.

## Evidence snapshot

```
00:09:13 worker        dispatcher_pick: claimed bt_…d7502b5a
00:11:38 worker-claude-2 dispatcher_pick: claimed bt_…d7502b5a   ← same task
00:11:43 worker-claude-1 dispatcher_pick: claimed bt_…d7502b5a   ← same task
CompilerError: Pinned writer provider 'claude-code' exhausted. WORKFLOW_PIN_WRITER disables fallback
00:11:48 worker-claude-2 executed … status=failed
ValueError: Invalid transition failed -> succeeded for task bt_…d7502b5a   ← codex success LOST
…
daemon-watchdog.service: failed — "required variable WORKFLOW_IMAGE is missing a value"
/data/.codex/auth.json → codex login status: "Logged in using ChatGPT"   (codex OK)
/data/.claude → claude -p: "Not logged in · Please run /login"            (claude DEAD)
```

## Immediate fix applied

Collapsed the fleet to a **single authenticated codex worker** (reversible,
no file edits, the failed watchdog won't auto-restart them):

```
docker stop workflow-worker-claude-1 workflow-worker-claude-2 workflow-worker
# leaves only workflow-worker-codex-2 (codex authed)
```

This removes the cross-worker claim race and the dead-claude poison.

## Verification

Watched the single codex worker drive a task clean through to terminal
success **after** the break (the required canary advance):

```
00:18:06 dispatcher_pick: claimed bt_1782345536900_f7094917
00:24:32 executed branch task … run=c751d637f075415a status=completed
00:24:33 dispatcher_pick: finalized bt_1782345536900_f7094917 -> succeeded
00:24:40 cloud_worker: subprocess exited rc=0 (clean)
```

Canary record: **request `bt_1782345536900_f7094917` → succeeded** (run
`c751d637f075415a`), 2026-06-25 00:24:33 UTC, no Invalid-transition crash.

## Question 1 — How did the loop break this time?

`_dispatcher_startup` (runs at *every* fantasy_daemon subprocess start) called
the blanket `recover_claimed_tasks`, which resets **every** `running` row to
`pending` — lease-blind. With 4 workers sharing `/data`, each worker restart
re-queued tasks a live peer was mid-execution on. The task got re-claimed by a
second worker; when both finalized, the second `mark_status` hit
`Invalid transition` and threw, **losing genuine successes**. Amplifiers: (a)
the restart-on-pending producer poll SIGTERMs in-flight tasks, multiplying
restarts; (b) **claude provider auth on the droplet is dead** ("Not logged
in"), so the 2 claude workers failed every claim instantly and marked tasks
`failed` before the codex worker's success could land. Net: 0 successes,
failed (3128) > succeeded (2476).

## Question 2 — How can the loop notice this break next time, automatically?

The `stuck_pending` warning fired but did not escalate. Add to
`supervisor_liveness` / `get_status`: (a) a **succeeded-rate-over-window**
signal — `0 terminal successes in N min while pending>0 and workers healthy`
is the precise shape; (b) a **duplicate-finalize counter** (count
Invalid-transition events — non-zero means double-claim); (c) **provider-auth
health** — surface `claude-code: not logged in` as a provider-down warning so
"all writers dead" is visible in status, not buried in worker logs.

## Question 3 — How can the loop fix this break next time, automatically?

`daemon-watchdog.service` is the intended auto-recovery layer but is itself
**failed** (`WORKFLOW_IMAGE` missing) — fixing separately so it can act. A
periodic stuck-claim reaper (`reclaim_expired_leases` already exists; ensure it
runs on a timer, not only on claim attempts). Auto-quarantine a provider whose
auth check fails so dead-auth workers stop poisoning the queue and work routes
to healthy providers.

## Question 4 — How can the loop avoid this break in the first place next time?

Shipped (PR #1339): startup recovery is now lease-aware (`reclaim_expired_leases`,
never steals a live peer's fresh-lease task) and `mark_status` is terminal-
idempotent (first-writer-wins, never crashes on a duplicate finalize). This
makes the multi-worker fleet structurally immune to the double-claim corruption.
Deeper, still open: (1) **provider-auth must be monitored + auto-healed** — the
true root was dead claude auth with no working-provider guarantee; (2) the
**restart-on-pending producer poll** is a churn amplifier and should be replaced
by the daemon claiming in a loop (not only at startup), removing the need to
restart a live subprocess at all.

## Substrate improvement filed

- **PR #1339** — lease-aware startup recovery + idempotent finalize (the cure).
- Follow-ups (not yet filed as PRs): daemon-watchdog `WORKFLOW_IMAGE` fix
  (host-side, in progress); claude-auth re-seed on the droplet (host decision —
  needs their subscription creds, or run a codex-only fleet); restart-on-pending
  hardening; provider-auth health surfaced in `get_status`.

## PLAN.md update

None required for this incident — the fix restores documented invariant §4.3 #7
(claimed→pending recovery) with the safer lease-aware mechanism already specified
under BUG-011 Phase C. The provider-auth-monitoring + restart-on-pending items
above are candidates for the next loop-uptime design pass if they recur.
