# Design: fail-closed universe credentials

## Decisions

### D1: Enforce at both environment and router boundaries

Universe-scoped subprocess environments always remove API-key and subscription-auth variables before the vault overlay. The router separately removes cloud providers whose credential class is unresolved. The environment boundary prevents accidental variable inheritance; the router boundary prevents CLI default-home discovery from bypassing an unset variable.

### D2: Preserve host flows by making universe context the boundary

Calls without an explicit universe directory retain the current daemon/developer environment and are classified as host-paid or local. Only calls carrying `UniverseContext.universe_dir` receive the fail-closed policy.

### D3: Receipts are provider-result metadata, not global last-call state

The call bridge returns a string-compatible result carrying immutable provider metadata. This avoids the concurrency-unsafe module-global `last_provider` seam. `converse` returns two purpose-labelled receipts (`reply` and `learning_extraction`). Graph execution copies the same metadata into its existing durable `provider_calls` event.

### D4: Async run acknowledgement cannot claim a provider before one serves

`run_graph` returns an explicit pending receipt state and an empty receipt list at enqueue. `get_run` reads the durable provider-call event and returns the completed per-node receipts. This is honest under zero-node and multi-node runs and remains auditable after the worker finishes.

### D5: Credential classes disclose payer category, never credential material

Public values are `founder_byo_api_key`, `universe_subscription`, `host_api_key`, `host_subscription`, `local_no_credential`, or `unknown`. Receipts also derive `credential_owner` (`founder`, `universe`, `host`, `none`, or `unknown`).

### D6: One provider call gets one credential route

When a universe contains both a BYO API key and subscription auth for the same provider, the BYO key wins and the subprocess receives an isolated empty provider home rather than the subscription token/home. This makes the payer class deterministic. A `host_daemon` selection alone is not a credential binding: it persists the requested writer but keeps `allowed_providers=[]` until a founder-hosted runtime credential is explicitly bound.

## Risks and mitigations

- Provider implementations that authenticate outside known env/home mechanisms could evade env sanitization: the router's resolvable-credential gate blocks unknown universe-scoped cloud providers.
- An incorrectly broad set-engine allowlist could strand market/host-daemon sources: source modes with no bound runnable credential persist an empty allowlist and fail closed rather than guess.
- String-subclass metadata could be lost when callers coerce early: graph and conversation boundaries consume it immediately and tests cover both paths.

## Rollback

Revert the branch. This restores ambient fallback and removes receipts; no storage migration is introduced.
