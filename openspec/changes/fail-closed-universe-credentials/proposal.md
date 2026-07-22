# Fail-closed universe credentials and provider receipts

## Why

Universe-scoped provider subprocesses inherit a copy of the daemon environment. The current sanitizer removes API-key variables only when the host has not opted into them, while ambient subscription selectors (`CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME`) survive. A universe with no vault can therefore spend host subscription credentials. `set_engine` records only `preferred_writer`, so even a founder who supplies a key can fall through to another host-paid provider. Public `converse` and `run_graph` responses do not identify the serving provider or credential payer class, making the breach unauditable after the fact.

## What Changes

- Sanitize every universe-scoped provider environment of ambient API-key and host-subscription auth before overlaying vault-owned auth. Host-scoped daemon and local-development calls with no universe context retain their current environment behavior.
- Filter universe-scoped routing to providers with a resolvable universe credential, except explicitly credentialless local providers. Missing/unresolvable vault auth fails closed before a cloud provider subprocess is invoked.
- Make every `set_engine` source write `allowed_providers` alongside `preferred_writer` whenever a provider is selected; BYO keys may select only the provider route that consumes that key.
- Make BYO API-key auth mutually exclusive with subscription auth for the same call, and keep unbound market/host-daemon selections non-runnable rather than treating ambient platform auth as a binding.
- Stamp successful provider responses with a non-secret credential class and owner, and expose purpose-labelled receipts for both `converse` calls.
- For async `run_graph`, return `provider_receipt_status=pending` on enqueue, persist per-node provider/payer receipts, and expose them through `get_run` after calls occur.

## Impact

- A newborn or misconfigured universe that previously succeeded by borrowing host Claude/Codex auth now fails with provider exhaustion (or uses an explicitly available credentialless local provider).
- A founder's configured writer no longer falls through outside its allowlist.
- `host_daemon` and market selections without an explicitly bound runtime credential now remain pending and fail provider calls; they previously appeared configured while silently spending ambient platform credentials.
- Host daemon/dev calls without a universe context keep their existing ambient-auth behavior.
- No secret value, auth path content, or token is emitted in a receipt.
