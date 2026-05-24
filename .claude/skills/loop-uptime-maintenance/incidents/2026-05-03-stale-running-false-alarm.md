---
incident_date: 2026-05-03
short_name: stale-running-false-alarm-canary
severity: p2
time_to_recovery_minutes: <5 (self-recovered)
applied_by: cowork-busyclever
---

# Incident: stale_running warning fired during legitimate long-LLM-call (false alarm)

## Symptoms

Canary BUG-055 was being processed by daemon::workflow-developer-daemon. After ~3 min of healthy heartbeating, daemon went silent for ~167 seconds. supervisor_liveness fired the `stale_running` warning citing PR #212 Phase C reclaim as not-yet-shipped. **Then daemon resumed** — heartbeat caught back up, progress_age dropped to 2s, warning cleared, lease refreshed.

## Evidence snapshot

```
[silence period]
running: 59484520 progress_age=167s lease_remaining=132s heartbeat_age=167s
warnings=['1 stale running task(s) (heartbeat past threshold or lease expired). BUG-011 Phase C reclaim would reclaim these once shipped.']

[after resume, ~40s later]
running: progress_age=2s lease_remaining=275s
stale_running_tasks=[]
warnings=[]
```

## Immediate fix applied

None. Self-recovered.

## Verification

Self-verified by daemon resuming heartbeat. Canary BUG-055 still in flight at session wrap, terminal not yet reached.

## Question 1 — How did the loop break this time?

It didn't break. The daemon was likely making a long-running LLM call without intermediate heartbeat ticks. The supervisor's stale-detection threshold treated a normal slow operation as a wedge candidate.

## Question 2 — How can the loop notice this break next time, automatically?

The stale-detection IS noticing — too eagerly. The signal is correct but the threshold or the interpretation is too tight. Two improvements:
- Daemon emits intra-LLM-call progress heartbeats (ping the supervisor every N seconds during a long call so the heartbeat doesn't stall).
- Supervisor distinguishes "no heartbeat AND lease about to expire" (real stale) from "no heartbeat but lease has plenty of headroom" (probably legitimate slow op).

## Question 3 — How can the loop fix this break next time, automatically?

Don't fire the warning when lease has substantial remaining time AND last_progress is recent. Today the warning fires on heartbeat_age threshold alone; pairing it with lease_remaining > X minimizes false positives.

## Question 4 — How can the loop avoid this break in the first place next time?

Daemon design: every long-running primitive (LLM call, web fetch, filesystem operation) should have an internal progress emitter that ticks the daemon's heartbeat at sub-call granularity. The current design only updates heartbeat between phases, which means a single long call appears as a stall.

Architectural: the heartbeat protocol should be "I am alive AND making progress on operation X" with operation-level granularity, not "I returned from the last phase." This is a small refactor to daemon harness code.

## Substrate improvement filed

Not yet — captured here for follow-up. Small enough to file as a normal patch request once the loop is healthy.

## PLAN.md update

None required — this is a tuning issue within the existing § Uptime And Alarm Path framework, not a new failure class. The skill's incident log captures the specifics for future reference.
