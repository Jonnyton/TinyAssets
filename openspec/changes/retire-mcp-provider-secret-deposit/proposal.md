## Why

TinyAssets currently invites a founder to supply a provider API key through a
hidden MCP action and persists it as base64-recoverable content in the
universe's JSON vault. That crosses the chatbot/control-plane boundary before
the requester-controlled executor can protect the secret, conflicts with the
BYOC architecture, and can make a shared-universe administrator a confused
deputy for another principal's provider authority.

## What Changes

- **BREAKING:** prohibit new raw or recoverable bring-your-own
  `llm_api_key` deposits through MCP, prompts, the control plane, and the
  per-universe JSON credential vault. Subscription, VCS, and social credential
  custody remain unchanged and keep their existing owners.
- Store requester-supplied provider API keys only in the
  requester-controlled executor's native OS
  secret store; keep only an opaque, non-derivable, host/principal/universe/
  provider/generation-bound reference in control-plane state.
- Dereference the secret exactly at requester-owned local provider launch
  inside draft PR #1691's frozen
  `ProviderInvocation -> ProviderLaunchHandle` barrier, with no file,
  environment, host-home, or maintainer/founder fallback.
- Retire legacy `llm_api_key` records through a metadata-only,
  owner-initiated, rotation/revocation-first, compare-and-delete saga that never
  decodes, exports, or silently migrates plaintext.
- Separate universe administration from provider-credential authority; a
  shared-universe admin cannot use, replace, rotate, or delete another
  principal's binding.
- Keep the current `runner/v1` credential-reference field as an opaque carrier,
  not an authority validator. Requester-owned local invocation must compose the
  exact credential binding with draft PR #1691's frozen launch barrier.
  Accepted-market remote execution must use the owner-accepted production
  B2/distributed-execution authority contract. The current D0
  fake-only/production-denied seam is not ordinary requester-provider
  authority; add no parallel authority system.
- Keep #1691 as the sole owner of provider destination ceilings,
  `setup_required`, engine assignment, and no-maintainer-route behavior. This
  change writes no competing `provider-routing` delta.
- Keep #1736 as the owner of account refresh-token custody/host registration;
  provider-secret references use a disjoint namespace and lifecycle.
- Record structured `write_graph(target=universe)` mutation as the preferred
  successor candidate, not existing behavior. The universe/interface owners
  must accept, specify, and land its typed operation, authorization,
  idempotency, and compatibility behavior before runtime retirement.
- Require custody-specific local multi-process concurrency proof while leaving
  the broader full-platform §14/Track J load suite honestly deferred.

## Capabilities

### New Capabilities

- `provider-credential-custody`: Requester-executor native API-key custody,
  opaque binding semantics, launch-time dereference, legacy `llm_api_key`
  retirement, and custody-specific concurrency.

### Modified Capabilities

- `credential-vault`: Stop accepting/resolving recoverable `llm_api_key`
  records, preserve the truthful as-built protection contract for every
  credential class that remains, and define locked legacy
  inventory/deletion behavior.
- `identity-auth-and-access-control`: State that universe administration does
  not confer provider-credential authority.
- `distributed-execution`: Preserve the existing nine-field `runner/v1`
  carrier truth while distinguishing requester-owned #1691 local invocation
  from accepted-market B2 execution and refusing to present the current
  fake-only/production-denied D0 seam as ordinary provider authority.

## Impact

- This lane is review/spec-only. It changes no runtime or canonical spec until
  dependency owners accept their boundaries.
- Future runtime owners: universe setup/prompt handling, local tray/native
  credential storage, provider launch, credential-vault retirement tooling, and
  canonical/plugin mirrors.
- Exact dependency anchors: draft PR #1691
  (`constrain-set-engine-provider-authority`) for assignment,
  `ProviderInvocation`, and `setup_required/held`; draft PR #1736 for native
  account-token storage and production principal-to-host binding;
  `openspec/changes/universe-creation/` plus #1484 for the birth/configuration
  seam; `openspec/specs/distributed-execution/spec.md` plus its B2 production-
  authority owner for accepted-market composition;
  `openspec/changes/test-identity-and-reset/` for reset adaptation; and
  `openspec/changes/retire-legacy-live-mcp-tools/` for hidden-tool removal.
- Explicitly excluded: provider-routing delta ownership, subscription/VCS/
  social credential migration, organization-pooled credentials,
  cross-principal delegation, server-side encrypted provider custody, and
  #1469's parallel grant/lease/fence system.
