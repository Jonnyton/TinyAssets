---
incident_date: 2026-05-03
short_name: stuck-pending-after-bug-054
severity: p1
time_to_recovery_minutes: TBD
applied_by: cowork-busyclever
---

# Incident: Dispatcher stuck-pending after BUG-054 + BUG-053 filed via chatbot

## Symptoms

Two file_bug calls were made through a real user-sim chatbot conversation (BUG-053 wiki-lint backlog + BUG-054 live-wiki-refactoring feature request). One processed (queue succeeded count went 19→20). The other got stuck in pending. supervisor_liveness fired the documented stuck_pending warning at 312 seconds (threshold 120s). No running tasks. No stale running tasks. Dispatcher is not picking up the pending bug.

This is a **scale-1 failure** — only two filings made and the loop already wedged. The "dozens of users" scale problem the prep filing was about is actually present at scale=1 today.

Concurrent context: production `evidence.activity_log_tail` shows the universe cycle wrapper completing repeatedly with `stopped=True, reason=worldbuild_stuck, words=0, chapters=0` for hours (different lane from the patch loop dispatcher, but suggests broader unhealthy state).

## Evidence snapshot

```
queue depth=22 pending=1 running=0 succeeded=20 failed=1 cancelled=0
stuck_pending_max_age_s=312 stuck_running_max_age_s=0
running_tasks_lease=[]
stale_running_tasks=[]
warnings=['stuck_pending: oldest pending task is 312s old (threshold 120s). Likely supervisor restart loop, dispatcher disabled, or daemon subprocess wedged. See PR #206 spec for incident pattern.']
auto_ship_health: recent=0 opened=0
last_request_id=None last_run_id=None

evidence.activity_log_tail:
  [2026-05-03 06:00:14] Universe cycle wrapper: completed (stopped=True, reason=worldbuild_stuck, words=0, chapters=0)
  [2026-05-03 06:50:38] Universe cycle wrapper: completed (stopped=True, reason=worldbuild_stuck, words=0, chapters=0)
  [2026-05-03 07:09:35] Universe cycle wrapper: completed (stopped=True, reason=worldbuild_stuck, words=0, chapters=0)
```

Filing details:
- BUG-053: `dispatcher_request_id=8699982f-6e3c-4cd1-...` — wiki lint single-page backlog
- BUG-054: `dispatcher_request_id=65bb5e87-b8ae-4c8b-a513-7f3a3d13ccbe` — live wiki refactoring + multi-generation attribution feature request

One of these (likely BUG-053 filed first, succeeded fast) accounts for the +1 succeeded; the other is the +1 stuck pending.

## Immediate fix applied

Skill creation itself — this is the first application of `loop-uptime-maintenance`. The actual unwedge is host-side action (Jonathan to restart supervisor / dispatcher / daemon subprocess as appropriate per the warning's named candidates). Cowork session is not running on the production host and cannot directly restart processes.

Substrate-level fix shipped in this same commit: this incident log + skill framework, so the next time this happens we have a documented pattern to follow rather than improvising.

## Verification

**Status (post-skill-update v1.1):** Recovery is NOT confirmed yet by the new canary discipline. Outside-in signals show the wedge symptom cleared (pending=0, no warnings, succeeded count went 20→21 — one of the originally-stuck tasks advanced). But per the updated SKILL.md step 4, that's necessary-not-sufficient. The "watch a NEW post-break request advance to terminal status" condition is pending: a canary filing through user-sim is being prepared as the dedicated 4th tab to verify. This incident log will be updated with the canary's request_id + final status once observed.

**Canary update (post-skill v1.1, ~08:00Z):** Canary BUG-055 was filed (worldbuild_stuck observation, dispatcher_request_id=59484520-c883-46ad-802f-5237bef55c4c) at 07:54Z. Picked up by daemon::workflow-developer-daemon within ~26s, transitioned pending → running. Daemon then went silent for ~167s mid-investigation, triggering a `stale_running` warning. **Then resumed** — progress_age dropped to 2s, lease refreshed to 275s, warning cleared. Net: the apparent stale-running was a FALSE ALARM, likely a long LLM call without intermediate heartbeat ticks. Canary still in flight at session wrap; not yet terminal. Strict v1.1 verification (terminal advance) NOT yet satisfied, but liveness signal is strong.

**Two follow-ups for next session:**
1. Check BUG-055 final status. If succeeded, this incident closes per v1.1.
2. The heartbeat-threshold tuning question: the "stale" warning fires too quickly relative to legitimate long operations. Either daemon needs to emit intra-call progress heartbeats during slow LLM calls, or the threshold needs widening, or both. Worth a separate small filing once loop is healthy.

Will be confirmed after host-side unwedge. Expected post-recovery state: pending=0 (or pending tasks all freshly queued <120s old), running=0 or small positive, no stuck_pending warning. The pending bug should advance to running, then succeeded — at which point the loop has finally seen its own bug-about-being-broken.

## Question 1 — How did the loop break this time?

Proximate cause: not directly observable from outside the host. The supervisor_liveness warning lists three candidates: (a) supervisor restart loop, (b) dispatcher disabled, (c) daemon subprocess wedged. Without journalctl or process-list access, it isn't possible to distinguish from outside.

What we know: scale=1 was enough to trigger it. Either the dispatcher has a class of failure that triggers under low load too, OR concurrent unrelated state (worldbuild cycles repeatedly bailing) is consuming/wedging shared resources, OR there's been a state accumulation since the last green run that finally tipped over.

The chain: prep filing → chatbot called file_bug → file_bug enqueued task → dispatcher should have claimed → didn't claim within 120s threshold → warning fired at 312s.

## Question 2 — How can the loop notice this break next time, automatically?

The notice layer DID work. supervisor_liveness fired the documented warning. PR #206/#212 shipped exactly this detection. The notice layer is fine.

What's missing is the notice → action wiring. The warning sits in get_status as text. No external channel is paged. No autonomous response is triggered. The PLAN.md § Uptime And Alarm Path describes alarm-sink + Pushover paging for canary REDs but stuck_pending isn't a canary RED — it's an internal queue state that probably doesn't reach the alarm path today.

Next-time improvement: stuck_pending crossing a threshold (e.g., 5min) should emit a structured alarm marker that the existing alarm-sink can consume, the same way uptime-canary does for site-down. Concretely: add a stuck-pending alarm emitter, route through alarm-sink, page out at threshold-cross.

## Question 3 — How can the loop fix this break next time, automatically?

The three named candidates (supervisor restart loop, dispatcher disabled, daemon wedged) each have a different right response. Container-restart (layer 1 self-heal) handles supervisor crash but not "supervisor running but stuck." That's the gap.

A simple autonomous response: when stuck_pending exceeds a longer threshold (e.g., 10min, well past the 5min alarm), trigger a watchdog-supervised dispatcher reset. The systemd unit + workflow-watchdog.timer pattern is already in place; this would be a new watchdog probe specifically for "queue is full and dispatcher isn't moving it" — distinct from "process exists or doesn't."

Ship: a small new probe in the watchdog timer that reads queue state via the same surface mcp_probe uses, and on stuck_pending threshold-cross, sends SIGTERM+SIGKILL to the dispatcher subprocess and lets the supervisor restart it. This is a layer-1.5 fix: between container-restart (layer 1) and GHA p0-outage-triage (layer 2).

## Question 4 — How can the loop avoid this break in the first place next time?

Architectural: the dispatcher's claim path should not be able to wedge in a way that leaves pending tasks unclaimed. Two underlying patterns to investigate:

1. **Lease-based dispatch with TTL.** A claim that doesn't make progress within a TTL is automatically released and the task returns to pending for re-claim. PR #212 (BUG-011 lease/watchdog Phase A) was exactly this work. Either the lease TTL is too long, or there's a code path that doesn't go through the lease (e.g., the dispatcher itself wedging before any claim happens).

2. **Idempotent re-enqueue on detection.** When stuck_pending fires, the task is re-enqueued (or its claim status reset) so a fresh dispatcher instance can pick it up. The current data shows pending=1 with no claim, so the task IS available — the dispatcher isn't trying. So lease TTL alone doesn't solve this; we also need active dispatcher health-check.

Bigger architectural change: the dispatcher should be MULTIPLE redundant subscribers to the queue, not a single subscriber with a lock. If one dispatcher wedges, others continue draining the queue. This is a substantial refactor but it's the architectural answer to "single point of dispatcher failure."

## Substrate improvement filed

This commit ships the skill itself + this incident log. The named substrate improvements (alarm-sink wiring for stuck_pending; watchdog probe for dispatcher-stuck; multi-subscriber queue refactor) are NOT yet PRs — they are sized as future substrate work emerging from this incident. Each one is a candidate for a separate user-sim filing once the loop is back up, framed as "the loop noticed itself stuck and here is what it learned to ask for."

The cleaner future flow: incident → log via skill → 4 questions → file the substrate improvements through user-sim once dispatcher is unstuck → loop processes them → next iteration of this skill needs to handle a different failure class because this one is now layer-1.5-handled.

## PLAN.md update

Adding to § Uptime And Alarm Path: a new note that **stuck_pending is a fourth detection channel** alongside the three self-heal layers, and that **the new `loop-uptime-maintenance` skill at `.agents/skills/loop-uptime-maintenance/SKILL.md` handles failure classes not yet graduated to layers 1-3.** Pointer-only update; the skill carries the depth.
