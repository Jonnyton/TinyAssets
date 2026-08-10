# Wire user-provided engine runtimes (self-host + market-brokered ceiling)

## Why
Founder directive 2026-08-10: the multi-user final shape is that **every
universe runs its LLM calls only on something the user provided or authorized**,
never the platform's credentials, fail-closed. `set_engine` already PERSISTS all
four engine sources (`byo_api_key`, `self_hosted_endpoint`, `market_rented`,
`host_daemon`) — but only `byo_api_key` has a wired RUNTIME. At call time,
`providers/router.py` ignores `engine_source` and routes through the platform
`FALLBACK_CHAINS` (`claude-code`/`codex`/free tiers/`ollama-local`) steered only
by `preferred_writer`/`allowed_providers`. So a universe that chose "my own
endpoint" or "a metered model within my ceiling" still executes on the platform
chain. This change wires the two remaining **user-provided / user-authorized**
runtimes.

Scope boundary (avoid thrash): the fail-closed enforcement of the no-universe /
process-global credential-leak path (`providers/base.py:386-387`) and the
per-requester binding of the converse path are the charter of the in-flight
`constrain-set-engine-provider-authority` — NOT this change. This change wires
runtimes for engine sources a universe explicitly set.

## What Changes
- **`self_hosted_endpoint` runtime** ("user provides their own compute"): when a
  universe's `engine_source=self_hosted_endpoint`, route its writer/judge calls
  to an OpenAI-compatible provider pointed at the universe's `engine_endpoint`.
  No platform credential is used. Fail-closed: if the endpoint is unreachable or
  unset, the call fails loud — it does NOT fall back to the platform chain.
- **`market_rented` runtime** ("user authorizes a ceiling; platform brokers"):
  when `engine_source=market_rented`, route calls to a platform-brokered
  OpenRouter provider using the universe's `market_model`, and enforce the
  user-authorized `spending_cap` as a hard per-universe ceiling. The platform
  holds the OpenRouter key, but a universe may only spend up to its authorized
  ceiling; once the ceiling is reached the engine fails closed (no further spend,
  clear "raise your ceiling" signal). A durable per-universe spend ledger records
  each metered call's cost against the cap.
- **Engine-source-driven routing**: provider resolution reads `engine_source`
  BEFORE the fallback chain; for these two sources the chosen runtime replaces
  the chain (single provider, no platform fallback). `byo_api_key` and
  `host_daemon` are unchanged.

## Capabilities
### Modified Capabilities
- `provider-routing`: routing honors per-universe `engine_source`; self-host and
  market runtimes execute on user-provided/authorized providers, fail-closed,
  with ceiling enforcement for the market source.

## Impact
- New: `tinyassets/providers/self_hosted_provider.py`,
  `tinyassets/providers/openrouter_broker_provider.py`,
  `tinyassets/spend_ledger.py` (per-universe metered-spend ledger + ceiling gate).
- Modified: `tinyassets/providers/router.py` (engine-source resolution hook),
  `tinyassets/providers/base.py` (self-host/broker cred resolution),
  `tinyassets/config.py` (already carries the fields).
- Tests: self-host routing + fail-closed, market ceiling enforcement (spend ≤ cap,
  fail-closed at cap), engine-source resolution.
- Secrets: the OpenRouter broker key is a platform secret resolved in the
  credential-blind path (like WorkOS Pipes) — never in MCP output or public SQLite.
