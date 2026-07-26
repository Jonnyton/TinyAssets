## MODIFIED Requirements

### Requirement: Subscription auth health is conservative, cached, and non-blocking on status reads
The provider layer SHALL expose `subscription_auth_health(provider_name, allow_probe=True)` with `ok`, `not_logged_in`, or `unknown` status and human-readable detail. When `TINYASSETS_AUTH_VIABILITY_PROBE` is not explicitly falsy, Codex health MUST use a layered presence, freshness, and live-viability policy: a missing `CODEX_HOME/auth.json` is `not_logged_in`; a recent parseable `last_refresh`, or the recent mtime of a valid JSON object that omits that field, is `ok`; and stale, corrupt, or suspicious state consults a TTL-cached verdict or one small real `codex exec` probe when probing is allowed. When that flag is falsy, any present `auth.json` yields presence-only `ok` without freshness parsing or probing. Only a recognized dead-auth signature produces `not_logged_in`; missing binaries, timeout, unexpected nonzero exit, or empty output without such a signature are inconclusive and remain `ok` with diagnostic detail. Probe-derived Codex verdicts SHALL be cached beside `auth.json` for cross-process visibility with an in-memory fallback. Claude health SHALL be `ok` for a non-empty OAuth token or populated config directory, `not_logged_in` for an absent, empty, or unreadable config directory without a token, and all unrecognized providers SHALL be `unknown`. Under an effective worker/provider V2 gate, loss of maintenance authority SHALL record the separate worker-only state `auth_unknown` and SHALL quarantine provider-capable spawn and claim without changing ordinary router eligibility or the `subscription_auth_health` result union. While V2 is dark, the worker SHALL retain the shipped quarantine trigger of `not_logged_in` only.

#### Scenario: fresh Codex auth avoids a subprocess
- **WHEN** Codex `auth.json` is a valid object with a parseable `last_refresh` younger than the configured freshness window
- **THEN** health is `ok` with refresh-viability detail and no live probe runs

#### Scenario: valid object without refresh timestamp uses mtime
- **WHEN** Codex `auth.json` is a valid JSON object without a usable `last_refresh` field and its file mtime is fresh
- **THEN** health is `ok` without a live probe, while corrupt JSON or a present unparseable timestamp does not receive that mtime fast path

#### Scenario: stale dead Codex credential is quarantined and shared
- **WHEN** stale or suspicious Codex auth triggers a live probe whose combined output matches a configured dead-auth signature, or whose empty stdout pairs with a broad auth signal on stderr
- **THEN** health is `not_logged_in`, the verdict is cached in memory and best-effort atomically beside `auth.json`, and a separate non-probing process sharing that home can observe the cached dead verdict

#### Scenario: inconclusive Codex probe does not falsely quarantine
- **WHEN** the live probe is unavailable, times out, exits unexpectedly without a dead-auth signature, or returns empty output without an auth signal
- **THEN** health remains `ok` with the inconclusive reason in its detail so only positive dead evidence quarantines the worker

#### Scenario: viability flag disables freshness and probing
- **WHEN** `TINYASSETS_AUTH_VIABILITY_PROBE` is explicitly set to a falsy value and Codex `auth.json` exists
- **THEN** health is presence-only `ok` without reading freshness, consulting cached viability, or running the live probe

#### Scenario: status never launches a live Codex probe
- **WHEN** the chatbot-facing status path reads writer auth health
- **THEN** it calls the health function with probing disabled, consumes presence, freshness, and any cached verdict, and reports stale uncached auth as `ok` with deferred-probe detail instead of blocking on a subprocess

#### Scenario: worker gate owns live quarantine
- **WHEN** a cloud worker is pinned or explicitly assigned to a subscription writer
- **THEN** it performs the probing health check before runtime registration or queue work
- **AND** while V2 is dark it self-quarantines only on `not_logged_in`
- **AND** under an effective worker/provider V2 gate it self-quarantines on `not_logged_in` or the separate maintenance-authority state `auth_unknown`; a generic worker without a resolvable writer is not gated by this check

#### Scenario: unavailable maintenance authority is a worker-only quarantine
- **WHEN** an effective worker/provider V2 gate cannot obtain maintenance authority for fresh conclusive health evidence
- **THEN** the supervisor records `auth_unknown` and does not spawn or claim provider-capable work
- **AND** ordinary router `unknown` or inconclusive health remains eligible and is not converted to `not_logged_in`

#### Scenario: status summarizes subscription-writer loss only
- **WHEN** supervisor liveness computes auth health for `codex` and `claude-code`
- **THEN** `provider_auth.writers` contains each status and detail, `all_writers_unauthenticated` is true only when both checked subscription writers are `not_logged_in`, and warnings distinguish that condition from partial subscription-writer loss
- **AND** the roll-up does not inspect `ollama-local` or opted-in API-key providers and MUST NOT be treated as proof that every possible provider route is unavailable
