# Stream and classify provider attempts (interactive reliability)

## Why

A served converse turn runs the writer as ONE blocking `claude -p` subprocess with
a single 300s TOTAL wall-clock timeout (`claude_provider.py:264`
`asyncio.wait_for(proc.communicate(), timeout=config.timeout)`), non-streaming. A
substantive turn — model reasoning plus engine-MCP tool round-trips, all inside the
one subprocess — burns real wall-clock and can exceed 300s → `ProviderTimeoutError`
→ the router puts the SOLE served writer on a 120s cooldown
(`quota.py:21 COOLDOWN_TIMEOUT`) → with fallback correctly forbidden, the turn and
every follow-up within that window fail as `AllProvidersExhaustedError`, shown to
the user as "I'm at my model's capacity." Confirmed on prod: a single 300s timeout
poisons the whole conversation, mislabeled as capacity. Every meaningful
back-and-forth breaks. (Diagnosis + prod evidence: this change's `design.md`;
external-pattern research + Codex design memo referenced there.)

The root problem is a total wall-clock deadline that cannot tell "actively working"
from "hung," plus a cooldown that treats a transient attempt timeout as
provider-wide unavailability.

## What changes (no public surface change)

- `ClaudeProvider.complete` streams `claude -p --output-format stream-json
  --verbose --include-partial-messages`: read stdout line-by-line as NDJSON, drain
  stderr concurrently, assemble the final reply from the terminal `result` event,
  never `communicate()`.
- Replace the single 300s TOTAL deadline with an **idle watchdog**: the deadline
  resets only on a real protocol event (text delta, tool start/result, documented
  `system/api_retry`, terminal result) — NOT on whitespace, stderr, malformed JSON,
  or internal reasoning. A streaming turn is "alive" for as long as it makes
  progress; only a genuinely idle turn is ended. A generous absolute cap remains a
  resource backstop (ends the turn, does NOT cooldown the provider).
- Introduce a **failure taxonomy** — `provider_idle_timeout`, `interactive_deadline`,
  `provider_rate_limited`, `provider_overloaded`, `authority_held`,
  `provider_protocol_error` — derived from the stream's own `api_retry`/exit
  signals, replacing the substring `"exhausted"→capacity` heuristic.
- The router (`router.py:717`) stops applying a provider-wide cooldown for
  idle-timeout / interactive-deadline outcomes (a transient attempt timeout is not
  proof the credential is unavailable); real rate-limit/overload still cools with
  the provider's own retry-after. Remove the synchronous 30/60s retry sleeps from
  the interactive path (`universe_intelligence.py:639`, `call.py`).
- `app_ingress._failure_notice` maps the structured `failure_class` to a truthful
  user notice (timeout ≠ capacity).

Scope guard: NO change to the seven public MCP handles, the `run_graph` envelope,
action authority, or the Slack delivery contract (still a single final post).
Native Slack streaming and action-decoupling are later slices
(`stream-app-conversation-turns`, `admit-conversation-actions-to-epoch2-and-deliver-results`).

## Impact

- Spec: `provider-routing` (streamed attempt contract + timeout taxonomy +
  health/cooldown rules). Coexists with `provider-attempt-receipts` (receipts) —
  different requirements on the same capability, no overlap.
- Code: `providers/claude_provider.py`, `providers/base.py` (timeout profile +
  normalized event/failure types), `providers/router.py`, `providers/quota.py`,
  `providers/call.py`, `universe_intelligence.py` (drop interactive sleeps),
  `app_ingress.py` (`_failure_notice`); plugin mirror + tests.
- Deploy: prod runs a pre-#2438/#2439 image; this fix needs a durable deploy to
  reach the live user (founder deploy decision), with `TINYASSETS_ALLOW_CLAUDE_SERVING=1`.
