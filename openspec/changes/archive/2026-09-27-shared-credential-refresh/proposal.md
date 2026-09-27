## Why

A subscription source deposited as an OAuth bundle has no refresh story, so the
founder's ChatGPT subscription has failed every turn since 2026-09-24.

Each launch hands the CLI a throwaway read-only copy of the vault's
`llm_subscription` auth document (`snapshot_llm_subscription_credential`,
`credential_vault.py`). The CLI refreshes its own token inside that copy, the
provider rotates the refresh token, and the copy is deleted — so every later
launch replays a spent single-use refresh token and the provider answers
"refresh token was already used". `ensure_codex_home_from_vault` compounds it by
overwriting a newer on-disk document with the stale vault one. There is no
single-flight, so concurrent launches each spend the same token.

The HTTP `oauth2` path already does this correctly (`connection_oauth/tokens.py`):
per-credential thread + file lock, re-read inside the lock, the vault's exclusive
admission taken *before* the refresh token is spent, and the rotated bundle
written under that hold. That logic is the second implementation of refresh in
the repo; the subscription path must not become a third.

Two facts found while reading, which shape the design:

- Writing a rotated document back to the vault invalidates serving as it stands.
  `_subscription_record_digest` hashes the credential material plus the whole
  record, and that digest is pinned into the provider binding
  (`provider_serving_binding.py` refuses when
  `provider_binding.credential_reference_digest != custody.reference_digest`).
  A refresh must therefore renew the accepted source through the existing
  renewal path, not merely write the vault.
- On the sandboxed launch path the CLI cannot rotate at all: `/codex-home` is a
  tmpfs with each credential file bound read-only, so its write fails and the
  rotation is lost rather than merely discarded. Only the non-sandboxed path has
  a rotation to recover after a run.

A terminal refusal is also mis-typed. The launch path raises a plain
`ProviderUnavailableError`, so the router applies a 120 s cooldown and the turn
stops, instead of the `ProviderAuthenticationError` that marks the source for
reconnect and lets the turn continue to the next model the owner allowed.

## What Changes

- Add one `refresh_credential(...)` primitive holding the lock → hold-vault →
  re-read → spend → atomic write-back core. `ConnectionTokens` keeps its
  observable behaviour and calls the primitive instead of owning the core.
- Refresh a subscription bundle on the PLATFORM side before launch, through the
  primitive, whenever the stored document is near expiry or past the refresh
  threshold. The endpoint comes from the CREDENTIAL, not from the platform: the
  issuer named in the stored identity token, and that issuer's own RFC 8414
  metadata. Write back atomically, then renew the accepted source so the binding
  follows the rotated record, then snapshot for launch.
- Adopt a rotation the CLI made in a materialized home into the vault when its
  stamp is strictly newer. NOT from the launch copy: that copy is sealed `0o400`
  and bound read-only into the jail, so it cannot hold a rotation at all.
- Stop `ensure_codex_home_from_vault` overwriting a newer on-disk document with
  an older vault one. Newest wins, decided under the lock.
- Type a terminal refresh refusal (`invalid_grant`, "already used", "sign in
  again") as `ProviderAuthenticationError`, so the router marks the source for
  reconnect instead of cooling it.
- Make a sign-in failure ADVANCE the turn. Only a capacity exhaustion did, so the
  fallback chain excluded auth: `agent_turn_coordinator._next_after_signin` is the
  sibling of `_next_after_capacity`, reaching only models already in the owner's
  accepted order.
- One builder for `llm_subscription` records, stamping `deposited_at` and
  `last_refresh`, matching the landed `http_credential_record` shape.

## Capabilities

### New Capabilities

None. The refresh is an internal mechanism of storage the owner already
deposited; no new MCP action, route, or request kind.

### Modified Capabilities

- `generic-oauth-connections`: refresh becomes one shared primitive, with the
  `oauth2` connection behaviour unchanged.
- `byo-llm-connect-flow`: a deposited subscription bundle is refreshed by the
  platform before launch, and a terminal refusal marks the source for reconnect
  instead of cooling the provider.

## Impact

`connection_oauth/tokens.py`, a new `credential_refresh.py`,
`credential_vault.py` (record builder, subscription refresh seam, the
stale-overwrite deletion), `providers/codex_provider.py` (failure typing).
Storage shape changes by two added fields on an existing record type; no
migration — both fields are absent-tolerant reads.

Deliberately NOT in this change: the re-authentication request card. `rotate_http`
structurally cannot carry it (`_unpasteable_scheme` refuses sign-in schemes by
design, and the pending-request rail treats `rotate_http` as a secret-bearing
paste), so a card that starts the one-tap device flow is new public request
surface and gets its own change. The turn does not stop without it: it falls back
to the next model the owner allowed, and the source is marked for reconnect.

Owner: Claude. Branch: `claude/credential-refresh`. One PR.
