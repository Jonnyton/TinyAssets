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
  provider/generation-bound reference in control-plane state. Bind and
  independently recheck both current active `host_principal_generation` and
  provider-assignment generation immediately before protected launch or
  custody commit.
- Resolve the secret only at the transport-owned boundary behind the merged
  `constrain-set-engine-provider-authority` change's
  `ProviderAssignmentAdmission` and frozen
  `ProviderInvocation -> ProviderLaunchHandle` barrier.
  `ProviderInvocation` carries a reference and provenance, never secret
  material. CLI/local/in-process transports dereference only inside
  executor child/request memory. Remote HTTP receives only the outbound
  owner's non-serializable, grant-bound credential-blind proxy; that proxy
  alone resolves the reference and performs network I/O. There is no file,
  ambient environment, host-home, parallel outbound grant, or
  maintainer/founder fallback.
- Retire legacy `llm_api_key` records through a metadata-only,
  owner-initiated, rotation/revocation-first, compare-and-delete saga that never
  decodes, exports, or silently migrates plaintext.
- Separate universe administration from provider-credential authority; a
  shared-universe admin cannot use, replace, rotate, or delete another
  principal's binding.
- Keep the current `runner/v1` credential-reference field as an opaque carrier,
  not an authority validator. Requester-owned local invocation must compose the
  exact credential binding with that provider-authority owner's frozen launch
  barrier.
  Accepted-market remote execution must use the owner-accepted production
  B2/distributed-execution authority contract. The current D0
  fake-only/production-denied seam is not ordinary requester-provider
  authority; add no parallel authority system.
- Consume merged PR #1784 (`constrain-set-engine-provider-authority`,
  Opus-approved head `abdca5fe`, merge `620fed5a`) as the sole owner of generic
  provider-destination ceilings, `setup_required`/held assignment state,
  `ProviderAssignmentAdmission`, assignment CAS/generation, and the frozen
  launch barrier. This change owns the `llm_api_key`-typed ingress
  refusal and writes no competing `provider-routing` delta. The general
  no-maintainer-route invariant remains owned by landed Slice A0/provider-auth
  isolation.
- Keep PR #1736's shipped branch as the owner of account refresh-token custody,
  its stable account-token namespace, native-backend allowlisting, and its
  client-side onboarding protocol. Provider-secret references and lifecycle
  stay in this change; the missing authenticated production principal-to-host
  binding belongs to the existing active `bind-host-principal-to-account`
  successor.
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
  carrier truth while distinguishing requester-owned provider-authority local invocation
  from accepted-market B2 execution and refusing to present the current
  fake-only/production-denied D0 seam as ordinary provider authority.

## Impact

- This lane is review/spec-only. It changes no runtime or canonical spec until
  dependency owners accept their boundaries.
- Future runtime owners: universe setup/prompt handling, local tray/native
  credential storage, provider launch, credential-vault retirement tooling, and
  canonical/plugin mirrors.
- Surface successors remain separate and are not yet created:
  `activate-requester-host-engines` is the planned owner of completable
  Tier-2/Tier-3/plugin native-custody setup and attested local request
  authority; `activate-connector-requester-authority` is the planned owner of
  the newborn Tier-1 accepted-market path without raw secret deposit or
  desktop/web-app dependency. This custody lane grants neither path.
- Exact dependency anchors: merged PR #1784
  (`constrain-set-engine-provider-authority`, Opus-approved head `abdca5fe`, merge
  `620fed5a`) for assignment, `ProviderAssignmentAdmission`, reference-only
  `ProviderInvocation`, and generic `setup_required/held`; PR
  #1736 for native account-token storage/backend policy and its existing
  `OriginClient` protocol; active `bind-host-principal-to-account` for the
  authenticated server-side production principal-to-host route;
  `openspec/changes/outbound-boundary-layer/` for acceptance of the
  requester-host-local credential-blind proxy's provider-custody native
  reference source while retaining other credential classes;
  `openspec/changes/universe-creation/` plus #1484 for the birth/configuration
  seam; `openspec/specs/distributed-execution/spec.md` plus its B2 production-
  authority owner for accepted-market composition;
  `openspec/changes/test-identity-and-reset/` for reset adaptation; and
  `openspec/changes/retire-legacy-live-mcp-tools/` for hidden-tool removal.
- Explicitly excluded: provider-routing delta ownership, subscription/VCS/
  social credential migration, organization-pooled credentials,
  cross-principal delegation, server-side encrypted provider custody, and
  #1469's parallel grant/lease/fence system.
