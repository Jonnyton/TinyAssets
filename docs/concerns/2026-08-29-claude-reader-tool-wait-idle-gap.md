# The claude reader idle-kills a turn that is waiting on its own tool

**Filed:** 2026-08-29
**Verified:** REPRODUCED on the real reader, 2026-09-21, base ded0fb12 (runtime identical to
deployed f5c5e5ec). Root committed the red evidence at 4dca407f: a synthetic
`--output-format stream-json` protocol with identified tool start/result, injected model-idle
interval 0.15s, tool gap 0.35s, absolute cap 5s. Windows,
`C:/Users/Jonathan/Projects/TinyAssets/.venv/Scripts/python.exe -m pytest -q
tests/test_provider_stream_and_classify.py -k "identified_pending_tool or one_completed_tool or
completed_identified_tool"` -> 2 failed / 1 passed (the post-tool-silence control correctly timed
out). The earlier "not reproduced live -- Claude is not the served writer in production" wording
was stale: Claude IS used in production. What is reproduced is the *mechanism* -- healthy pending
tool silence being ended at the model-idle boundary -- on a controlled stream, not a captured
production trace.
**Severity:** P2 -- the mechanism is live-reachable; the blast radius is a served turn whose tool
outlives the idle interval.

## The claim

The idle watchdog (`StreamTimeoutProfile`, idle 30s) resets on protocol events. A tool call that
takes longer than the idle interval produces no events between `tool_use` start and its result, so
a claude-served turn that is legitimately waiting on its own tool is ended as `provider_idle_timeout`.

The codex reader fixed exactly this in #2674: while an `item.started` has no matching
`item.completed`, the allowance is `min(absolute cap, _TOOL_WAIT_S=900s)`, and only `turn.failed`
clears the in-flight tool. The claude reader has the equivalent signal (`tool_use` -> `tool_result`)
and does not use it.

## Historical cause remains unknown

Run `6ffec5e973734074` (failed 06:52:05-06:53:05 UTC, `provider_idle_timeout`, no protocol event
for 30s, committed side-effect state, one indeterminate reservation) is read-only evidence of a
timeout and nothing more. No tool-phase evidence was persisted for it, so whether a tool was
pending when it failed is NOT established -- committed side-effect state and a later successful
retry are not proof of cause. Do not replay it. This is the gap that
`respect-provider-tool-waits` task 1.3 closes going forward, not backwards.

## What resolving it looks like

Give the claude reader the same in-flight-tool allowance, with a test that drives the real reader
on a fake stream (tool start, silence > idle, tool result) and is RED on the current tree first.

Change `respect-provider-tool-waits` tasks 1.2/1.3 have landed that on branch
`codex/provider-tool-wait`: identities paired from `id` / `tool_use_id`, allowance
`min(absolute cap, _TOOL_WAIT_S=900s)`, and validated `tool_phase` / `last_progress_age_ms`
through `ProviderAttemptDiagnostic` into the persisted authorized run read.

**Still open.** This file is NOT deleted yet and acceptance is NOT closed: tasks 2.1-2.3 still owe
the Linux regression set, exact-head cross-family review, CI, the protected deployed SHA, and the
ordinary app-agent long-tool acceptance. Delete this file with the test names and the landed
commit once that live proof exists.
