# Design — Stream and classify provider attempts (Slice 1)

Evidence + full architecture: prod diagnosis (claude-code turns hit the 300s total
timeout → 120s sole-writer cooldown → conversation-wide "at capacity" mislabel) and
the Codex cross-family design memo (2026-08-19). This slice is the minimal internal
change that materially restores single-user reliability; it changes no public MCP
handle, no action authority, and no Slack delivery contract.

## Streaming read (ClaudeProvider.complete)

Launch: `claude -p --output-format stream-json --verbose --include-partial-messages`
(installed CLI 2.1.236 supports these). Write+close stdin, read stdout line-by-line
as NDJSON, drain stderr concurrently. Do NOT use `communicate()`. Parse only
documented events; the terminal `result` event is the canonical response + telemetry.

Assemble the reply text from assistant message text deltas; ignore internal
reasoning/thinking blocks (never relayed). Keep the existing exit-code handling
(exit 1 <5s = unavailable; Windows crash codes; bwrap check) as terminal outcomes.

## Idle watchdog (replaces the single 300s total deadline)

A timeout PROFILE, not one wall-clock. Reset the idle deadline on ANY recognized
protocol event that proves the CLI is alive and working: an assistant text delta,
`tool_use` start, `tool_result`, a documented `system/api_retry`, the terminal
`result`, AND — reconciled against a real 2.1.236 trace (Codex REVIEW blocker C) —
any recognized non-relayed protocol event as a **liveness heartbeat**: reasoning /
`thinking_delta` / `signature_delta` / `thinking_tokens`, hooks
(`hook_started` / `hook_response`), `system/status`, `system/notification`, stream
framing (`message_start` / `_delta` / `_stop`, `content_block_start` / `_stop`,
`ping`), `tool_progress`, `system/tool_heartbeat`, and an informational
`rate_limit_event` (`status == "allowed"`). During reasoning the stream emits ONLY
thinking + framing, so excluding them false-killed a working turn at the idle
boundary. Do NOT reset on whitespace, arbitrary bytes, stderr chatter, malformed
JSON, or an unknown-but-well-formed type. **Reasoning/thinking content is a
liveness signal but is NEVER relayed** into the assembled reply — only assistant
text and the terminal result are relayed.

When a documented `system/api_retry` carries a `retry_delay_ms`, the idle budget
for the following wait is extended to cover that stated wait (+ margin), so a real
provider retry is not relabeled `provider_idle_timeout` (bounded by the absolute
cap).

Initial profile (tunable via config, defaults):
- process → valid `system/init`: 10s (CLI/MCP startup failure)
- first useful progress after init: 20s
- inter-event idle: 30s (hung completion/tool)
- interactive soft SLO: 60s (emit a status; NOT a failure)
- absolute interactive safety cap: 600s (END the turn; do NOT cooldown provider)

A streaming substantive turn never trips the idle deadline; a genuinely hung turn is
caught in ~30s instead of 300s. The absolute cap is a GENEROUS fairness/resource
guard (well past the old 300s total deadline so a long progressing turn survives),
not evidence of an unhealthy provider.

## Failure taxonomy (replaces substring "exhausted"→capacity)

Derive `failure_class` from the stream + exit, not the aggregate error name:
- `provider_rate_limited` / `provider_overloaded` — from `system/api_retry` typed
  categories (Anthropic documents rate-limit, overloaded, auth, server-error). Carry
  `retry_after`.
- `authority_held` — ProviderAuthorityHeldError (serving authority unavailable/revoked).
- `provider_idle_timeout` — idle watchdog fired (no progress). NOT provider-wide.
- `interactive_deadline` — absolute cap reached. NOT provider-wide.
- `provider_protocol_error` — malformed/unparseable stream.
Each attempt records: failure_class, phase, provider, retryable, retry_after,
side_effect_state (none|possible|committed), TTFT, last-progress age, tool phase,
terminal result, process exit.

## Router health/cooldown model (router.py:717, quota.py:21)

A subprocess timeout is an ATTEMPT outcome, not proof the credential is down.
- `provider_rate_limited`/`overloaded` → cooldown until the provider's own retry_after
  (+jitter). Real capacity — keep the cooldown, keep fallback forbidden.
- `authority_held` → authority quarantine (reconnect/reseed), no blind retry.
- `provider_idle_timeout` / `interactive_deadline` → **NO provider-wide cooldown**;
  kill the process; the next turn stays eligible.
- Repeated launch/endpoint failure → circuit-breaker after a threshold (short probe
  recovery) — distinct from a single idle timeout.

Remove synchronous retry sleeps from the interactive path: `call.py` aggregated-
exhaustion retry and `universe_intelligence.py:639` 30/60s sleeps must not block the
ingress request or hold a worker slot. Sole-writer retry policy: allow ONE immediate
fresh-process retry only if no user-visible output AND no tool started AND no possible
side effect; otherwise end the turn honestly (no auto-retry, no sleep).

## Honest user notice (app_ingress._failure_notice)

Map `failure_class` → truthful text: idle_timeout = "the model stopped making
progress, I ended that attempt (no provider cooldown)"; interactive_deadline = "this
reply exceeded the interactive window; I did not claim completion";
provider_rate_limited = "your connected model is rate-limited; retry available after
…"; authority_held = "the served-writer authorization is unavailable or revoked".
Never call a timeout "capacity."

## Fail-closed posture

No final conversation record until a terminal provider `result` exists. Partial
streamed text may be persisted for reconciliation but is NEVER labeled a completed
assistant response. If visible text or a possible side effect occurred, do NOT blindly
retry the whole completion.

## Seams
- `providers/base.py:47` ModelConfig — add a timeout profile (idle/first-progress/
  init/soft-SLO/absolute) alongside legacy `timeout`; `:117` keep ProviderResponse
  as terminal. Add normalized stream-event + failure-class types.
- `providers/claude_provider.py:220-311` complete() — native streaming reader.
- `providers/router.py:667` route a stream; `:717-728` new health/cooldown map.
- `providers/quota.py:21` cooldown semantics per failure_class.
- `providers/call.py` + `universe_intelligence.py:639` — remove interactive sleeps.
- `app_ingress.py:360` _failure_notice — structured mapping.

## Build/test ordering
1. Stream reader + assemble final text; return existing ProviderResponse (behavior-
   parity test vs a recorded stream fixture).
2. Idle watchdog: fixture streams with gaps → alive while progressing; idle→fail.
3. Failure taxonomy from api_retry/exit fixtures.
4. Router cooldown: idle/deadline → no cooldown; rate_limited → cooldown w/ retry_after.
5. Remove interactive sleeps; assert no sleep on the ingress path.
6. _failure_notice mapping tests (timeout ≠ capacity).
7. Backward-safe: non-streaming callers still get a terminal ProviderResponse.
