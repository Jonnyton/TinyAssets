---
name: loop-uptime-maintenance
description: "The discipline for handling situations where the community patch loop is too broken to self-heal via its own loop. Use when, and only when, the loop cannot process its own emergency-fix request because the dispatcher itself is wedged, the supervisor is in a restart loop, or no daemon subprocess can pick up new tasks. Every use is a substrate improvement opportunity — each application teaches us how to never need this skill again. Success condition: usage trends to zero."
---

# Loop uptime maintenance

This skill exists for one situation: **the community patch loop is broken in a way it cannot fix itself through itself.** Normal substrate evolution flows through the user-driven loop (browser → chatbot → wiki/file_bug → loop investigates → ships). When that path is itself the broken thing, the loop has a chicken-and-egg problem: it can't process the bug-about-being-broken because being broken is what stops it from processing bugs.

This skill is the authorized escape hatch.

## The discipline

Three rules. Hold to all three or it's not the skill, it's just substrate work.

**1. Use this skill EVERY TIME the loop is really broken.** No skipping, no "I'll just quickly fix it." The skill's value is the cumulative learning across every application; skipping breaks the cumulative effect.

**2. Don't use this skill when the loop ISN'T really broken.** If the loop CAN process the bug-about-itself (slow, painful, partial — but possible), use the user-sim path instead. Cheating beyond the entry condition makes the skill a back-channel and erodes the user-sim discipline.

**3. Every application produces an incident log + substrate improvement + (usually) PLAN.md update.** No silent fixes. Each fix exists to make the next break less likely; you only get that compounding by writing it down.

## Entry condition — when the loop is "really broken"

ANY of these triggers the skill:

- Dispatcher wedged: tasks pile up in pending; supervisor_liveness reports `stuck_pending_max_age_s` above 5 minutes with no concurrent processing.
- Supervisor restart loop: container restart-loop watchdog fires repeatedly; daemon never reaches steady-state.
- Daemon subprocess wedged: process exists but doesn't pick work; no heartbeat advance.
- MCP surface 502/down: production canary RED for >5 min.
- Filesystem-bricked state: env unreadable, disk full, image-pull stuck — the layer 1 (container restart) and layer 2 (GHA p0-triage) self-heal classes that PLAN.md § Uptime And Alarm Path documents.
- Wiki write/file_bug failing: users can file but their filings don't reach the loop's queue.

If you can't tell whether you're in this state, run:
```bash
python3 scripts/mcp_probe.py status
```
Look at `supervisor_liveness.warnings` and queue counts. A stuck_pending warning + 0 running + non-zero pending is the strongest signal.

## The 4 reflection questions

Every application of this skill answers all four. Write the answers in the incident log. The questions are the only way the skill compounds — they push each fix to address not just *this* break but the *class* of break.

1. **How did the loop break this time?** What is the immediate proximate cause? What chain of events led to the state we're in? Be specific — not "dispatcher wedged" but "dispatcher wedged because <x> didn't release the lock when <y> happened."
2. **How can the loop notice this break next time, automatically?** The loop should detect this class without a human running mcp_probe. What signal would have flagged this earlier? Is there an existing warning that didn't fire? Is there a new warning to add?
3. **How can the loop fix this break next time, automatically?** What's the smallest autonomous response that would unwedge the loop without external intervention? Restart? Lock cleanup? Backoff? Process-kill-and-respawn? Name the fix even if you can't ship it now.
4. **How can the loop avoid this break in the first place next time?** The deepest question. What architectural change makes this break-class structurally impossible? This is usually substrate work bigger than the immediate fix, but if you don't name it now, it never gets prioritized.

## What to actually do during the application

Order matters. Do not skip steps.

1. **Confirm entry condition.** Run mcp_probe (or equivalent diagnostic). Confirm you're in a real-broken state, not a slow-but-working one.
2. **Capture incident state.** Take a snapshot of the relevant signals (supervisor_liveness, queue counts, recent activity_log_tail, last successful run). This is the evidence pack the incident log will reference.
3. **Apply the immediate fix.** This may be host-side (restart supervisor, clear lock, restart daemon) or code-side (ship a patch to main). Whatever's needed to unwedge.
4. **Verify recovery via canary, not via warning-cleared.** Re-run mcp_probe. Cleared warnings + pending=0 are NECESSARY but NOT SUFFICIENT — that just means the wedge symptom went away, not that the loop can actually process new work. To declare recovery, you must observe a NEW request advance to terminal status (succeeded / failed / cancelled) AFTER the break. Two cases:
   - **Existing backlog**: watch the queue. If pending tasks were stranded by the wedge, they should advance now. Confirm at least one advances to a terminal status post-break.
   - **Empty queue**: file a minimal canary patch request through the user-sim path (chatbot → file_bug). The canary should be safe, small, and likely to clear quickly — a wiki-cleanup observation, a docs typo, anything that exercises the dispatcher → daemon → terminal-status pipeline without risk. Do NOT skip the canary step because the queue is empty — empty queue is the ONLY case where you definitely don't have a natural verifier, and that's exactly when you need a synthetic one.
   Recovery is "we watched a request go through end-to-end after the break" — not "the warning cleared and we crossed our fingers."
5. **Write the incident log** at `.agents/skills/loop-uptime-maintenance/incidents/<YYYY-MM-DD>-<short-name>.md`. Use the four questions as section headers. Include the evidence snapshot from step 2.
6. **Identify the substrate improvement** the incident log asks for. File it appropriately:
   - Small + clearly substrate? Push as PR via the standard substrate path.
   - Large + needs design? File via user-sim (chatbot) as a normal feature request — the loop will pick it up once it's working again.
   - Cross-cutting + architectural? Update PLAN.md § Uptime And Alarm Path with the new failure class + recommended layer.
7. **Update this skill file if needed.** If the skill itself missed something (entry condition didn't catch this kind of break, or the discipline failed in a new way), edit `SKILL.md` to fix it.

## Connection to existing uptime infrastructure

This skill complements PLAN.md § Uptime And Alarm Path, which documents three host-independent self-heal layers (container restart, GHA p0-outage-triage auto-repair, deploy-side invariants). Those layers handle classes of failure that are well-witnessed and have known remedies. **This skill exists for failures that are NOT yet known classes** — the new ones, the ones layer 1-3 don't catch yet. Each application of this skill is a candidate to graduate from "skill-handled" to "self-heal-layer-handled" once the fix matures.

The arrow points from this skill toward the self-heal layers. Success is when a failure class moves out of this skill's incident log and into one of the three layers.

## Success metric

**Usage count of this skill should trend toward zero over time.** If we apply it twice this month and once next month and zero the month after, we're winning. If we apply it five times this week, the substrate isn't learning fast enough — the gap is in the reflection questions or in our discipline of actually shipping the substrate improvements they identify.

Track usage by counting incident log files. The count is the metric. Each incident log entry must reference its canary advance (request id + final status); incidents without a canary record are not counted as recovered, only as paused. When it stops growing, the loop has truly become self-healing and this skill has eliminated itself.

## Anti-patterns to avoid

- **Using this skill for slow-but-working failures.** If the user-sim path can still file the bug (even painfully), use that path. This skill is not a shortcut for impatience.
- **Declaring recovery without a canary advance.** "Warning cleared" is not "loop is processing." A wedged-then-quiet dispatcher can quietly stay quiet under no load, then fail again the moment the next request arrives. The canary step exists because outside-in observability cannot distinguish "healthy and idle" from "broken and idle." Skip it once and you ship the next stress test into a phantom-recovered loop.
- **Skipping the four questions.** Even when the immediate fix is obvious, the questions are what make the next break less likely. Without them, the skill is just substrate hacking with extra ceremony.
- **Not shipping the substrate improvement.** The incident log is necessary but not sufficient. If the substrate change identified by question 4 sits in the incident log forever, the skill doesn't compound.
- **Treating this skill as a permanent feature.** The whole point is that it makes itself obsolete. Don't get attached to it. Celebrate when its incident folder stops growing.
- **Hidden cheating during normal-working states.** The skill is the only authorized cheat condition. If you find yourself reaching for it because user-sim is annoying, stop — that's drift, not authorization.

## What goes in an incident log

Template at `.agents/skills/loop-uptime-maintenance/INCIDENT_TEMPLATE.md`. Each incident log:

- Front matter: incident date, severity, time-to-recovery
- Symptoms: what was observed
- Evidence snapshot: relevant signals at the moment of break
- Immediate fix applied: what we actually did to unwedge
- Verification: how we confirmed recovery
- The 4 questions answered
- Substrate improvement filed: link/PR/wiki page reference
- PLAN.md update (if any): which section, what added
