## Why

`set_engine` records preferences without a provider-eligibility ceiling, and
explicit-universe subprocess environments can retain ambient host auth when
API-key opt-in is enabled or vault access errors. These fail-open paths can use
a provider, host account, local route, or quota the requester never authorized
even though the router already has a strict allowlist primitive.

## What Changes

- Treat `allowed_providers` as the persistent provider-destination ceiling
  established by `set_engine`: a BYO Anthropic/OpenAI assignment gets the
  matching singleton; persistence-only self-hosted, market, and host-daemon
  choices get an empty ceiling until their destination is executable. This
  ceiling is necessary but never sufficient request execution authority.
- Reject an explicit `preferred_writer` that does not match the selected key
  service, and reject service aliases with no executable per-universe provider
  route, before writing either the credential vault or universe config.
- Make BYO vault/config mutation quarantine-first and rollback-safe so a failed
  assignment preserves the prior credential and ceiling, while rollback
  failure leaves a durable empty-ceiling quarantine instead of unrestricted
  routing. Successful assignment preserves unrelated vault records.
- For any explicit universe, strip ambient API-key and subscription auth before
  overlaying only vault-provided auth; vault/import/materialization errors fail
  closed rather than returning inherited host credentials.
- Block rollout until historical `set_engine` assignments are inventoried and
  explicitly migrated: confirmed BYO assignments receive the reviewed
  singleton, while ambiguous/incomplete assignments receive an empty ceiling.
- Prove end to end that failure of the assigned provider hard-fails with no
  call to any other registered provider, host account, local route, or quota.
- Keep request-scoped market/BYOC resolution, `run_graph` context threading,
  and race-safe provider receipts in their existing dependent lanes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-routing`: Make engine assignment establish a replace-not-union
  provider-destination ceiling, keep preference subordinate to it, and compose
  it with the separate request-authority bundle owned by #1582.
- `credential-vault`: Require the BYO key service, provider preference, and
  persisted allowlist to describe the same executable provider; sanitize
  explicit-universe environments and fail closed on vault errors.

## Impact

- Runtime: engine assignment, config semantics, credential-vault mapping,
  cross-process assignment serialization, and subprocess environment
  construction. Normal router preference ordering remains unchanged.
- Storage: every successful assignment replaces the non-secret
  `allowed_providers` field; BYO updates use
  `engine_assignment_state="pending"` plus an empty ceiling, preserve unrelated
  vault records, and restore prior state on ordinary failure.
- Tests: focused assignment and router integration tests; no real provider,
  network, credential, personal Claude/OpenAI quota, or platform compute use.
- Dependency: the active `universe-creation` change still owns request-scoped
  BYOC/accepted-market authority resolution and context threading for uncovered
  run paths; R2-1b still owns race-safe provider receipts.
