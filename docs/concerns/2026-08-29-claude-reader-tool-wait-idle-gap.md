# The claude reader idle-kills a turn that is waiting on its own tool

**Filed:** 2026-08-29
**Verified:** in code only -- `tinyassets/providers/claude_provider.py` tracks `tool_phase` as
telemetry and the idle allowance does not change while a tool is in flight. Not reproduced live:
Claude is not the served writer in production (`TINYASSETS_ALLOW_CLAUDE_SERVING` is unset).
**Severity:** P2 -- latent until a Claude-served universe exists; then it is the same failure
the founder hit on 2026-08-29 with codex (a healthy multi-step GitHub job killed mid-tool).

## The claim

The idle watchdog (`StreamTimeoutProfile`, idle 30s) resets on protocol events. A tool call that
takes longer than the idle interval produces no events between `tool_use` start and its result, so
a claude-served turn that is legitimately waiting on its own tool is ended as `provider_idle_timeout`.

The codex reader fixed exactly this in #2674: while an `item.started` has no matching
`item.completed`, the allowance is `min(absolute cap, _TOOL_WAIT_S=900s)`, and only `turn.failed`
clears the in-flight tool. The claude reader has the equivalent signal (`tool_use` -> `tool_result`)
and does not use it.

## What resolving it looks like

Give the claude reader the same in-flight-tool allowance, with a test that drives the real reader
on a fake stream (tool start, silence > idle, tool result) and is RED on the current tree first.
Then delete this file with the test name and the commit that landed it.
