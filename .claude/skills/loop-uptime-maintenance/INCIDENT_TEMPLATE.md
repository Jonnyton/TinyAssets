---
incident_date: YYYY-MM-DD
short_name: <few-word slug>
severity: <p0 | p1 | p2>
time_to_recovery_minutes: <int>
applied_by: <session-id or human name>
---

# Incident: <short title>

## Symptoms

What was observed. Be specific — error messages, queue numbers, log lines. The reader should be able to recognize this exact failure shape if they see it again.

## Evidence snapshot

The signals at the moment of break. Paste raw output where possible.

```
<mcp_probe.py status output, supervisor_liveness, queue_state, recent activity_log_tail, etc>
```

## Immediate fix applied

What was done to unwedge. Step by step. If host-side actions, name them. If a code patch, link the commit.

## Verification

How recovery was confirmed. Re-run of mcp_probe, queue draining, canary green, etc.

## Question 1 — How did the loop break this time?

Proximate cause. What chain of events. Be specific.

## Question 2 — How can the loop notice this break next time, automatically?

What signal would have flagged earlier? Existing warning that didn't fire? New warning to add?

## Question 3 — How can the loop fix this break next time, automatically?

Smallest autonomous response that would unwedge without external intervention.

## Question 4 — How can the loop avoid this break in the first place next time?

Architectural change that makes this break-class structurally impossible.

## Substrate improvement filed

Link to PR / wiki entry / file_bug. If nothing filed yet, name the gap and why it isn't filed yet.

## PLAN.md update

Section + what was added. If no update needed, say so + why.
