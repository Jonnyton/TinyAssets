## Context

The live implementation accepts a raw bring-your-own provider API key through the hidden
`universe action=set_engine` path, writes a base64-recoverable
`llm_api_key` record into a per-universe JSON file, and later overlays that
secret into a provider child environment. Slice A0 now prevents ambient host
and maintainer authority from entering a universe-scoped child, but selected
universe vault material remains recoverable control-plane custody.

This change is deliberately limited to `llm_api_key`. Existing
`llm_subscription`, `vcs`, and `social` records retain their canonical
behavior, storage limitations, and separate owners. In particular, this
change does not silently adopt #1736's account-token lifecycle or remove the
truth that retained vault secrets are protected only by filesystem
permissions.

The platform architecture requires requester-owned BYOC, no maintainer quota
consumption, minimal canonical MCP primitives, and private data remaining on a
host. The exact-seven public surface has no `set_engine` handle, and the active
legacy-tool retirement change will unregister the hidden `universe` tool.

Opus 5 reviewed this boundary on current main and returned ADAPT. Its durable
verdict is
`docs/audits/2026-07-24-retire-mcp-provider-secret-deposit-opus5-review.md`.

## Goals / Non-Goals

**Goals:**

- Remove raw API-key elicitation and reject unsupported `llm_api_key` fields at
  ingress without echo before application mutation or any inventoried
  TinyAssets-owned log, ledger, trace, capture, crash-report, or argv sink;
  client-owned upstream transcripts remain outside TinyAssets control.
- Keep requester-supplied provider API keys only in requester-controlled
  native OS secret storage.
- Carry a non-secret binding reference through draft PR #1691's requester-
  local assignment/launch barrier or an owner-accepted production B2 market
  authority path; keep `runner/v1` opaque and D0 fake-only/production-denied.
- Dereference only at the selected local executor's provider-launch boundary.
- Retire legacy recoverable records without decoding/exporting them.
- Fail closed through enrollment, migration, rotation, deletion, host expiry,
  and every crash/retry point.

**Non-Goals:**

- A new MCP tool/action or a second provider-routing/assignment contract.
- A second grant, lease, generation, or fence system.
- Server-side encrypted provider-secret custody, including #1469's backend.
- Organization-pooled provider credentials or cross-principal delegation.
- Subscription, VCS, or social credential retirement; those retain their
  existing canonical behavior and owners.
- Claiming the local custody race proof satisfies the broader §14 Track J load
  suite.
- Runtime edits while #1691, `bind-host-principal-to-account`, #1736's
  client/native-store seam, universe-creation, #1484, and
  distributed-execution owners still hold their seams.

## Decisions

### 1. Provider custody is a separate capability

`credential-vault` describes the shipped per-universe file store;
`desktop-host-runtime` describes the source tray; PR #1736's runtime branch
owns account refresh tokens, native-backend allowlisting, and the client-side
onboarding protocol. It explicitly leaves the production server-side
principal-to-host route unfinished. None owns requester-supplied API-key
lifecycle across principal, host, universe, provider, assignment generation,
and execution.

This change therefore introduces `provider-credential-custody` and modifies
only the shipped capabilities whose current truth conflicts with it.

Alternative rejected: fold everything into #1691. #1691 intentionally owns
provider destinations, `setup_required`, assignment, and invocation shape—not
credential-source isolation—and its provider-routing delta would collide.

### 2. `write_graph` is the preferred successor candidate, not landed behavior

Current `write_graph(target="universe")` creates a universe and its
`changes_json` argument is documented and dispatched only for
`target="branch"`. It does not currently configure a provider. The preferred
successor candidate after the hidden legacy `universe` tool retires is a typed,
non-secret provider-binding mutation on `write_graph(target="universe")`, but
that is new behavior, not an already canonical sub-operation.

The owners of `openspec/changes/universe-creation/`,
`openspec/changes/retire-legacy-live-mcp-tools/`, and the live interface must
accept and specify the operation name, authorization, idempotency, create
versus update discrimination, response envelope, and malformed/unknown-op
behavior before landing it. This custody change does not modify
`universe_server.py`, does not create a new public verb, and does not treat the
candidate as accepted dependency state.

Alternative rejected: preserve or rename `set_engine` as another public tool.
Engine assignment is universe state mutation and composes through
`write_graph`.

### 3. Secret and binding references are distinct

The native store creates a random, versioned `native_secret_ref` in a
provider-secret namespace. It never overwrites or reuses #1736's predictable
account-token reference.

The control plane's versioned #1691 assignment state stores a
`credential_binding_ref` that is:

- opaque, random, non-secret, and not a key-derivation input;
- bound to canonical provider, universe, principal, host/daemon, scope,
  assignment generation, issue time, and expiry;
- a locator only, never a bearer grant.

The unversioned `.credential-vault.json` SHALL NOT be authoritative binding
state; it may contain display-only non-secret metadata that is safe to lose,
but provider launch never trusts it. Only the bound host maps
`credential_binding_ref` to `native_secret_ref`. Neither identifier is copied
to another host or principal.

Enrollment is a two-store commit-token protocol, not a cross-store CAS:

1. the local host atomically records a random `native_secret_ref`, enrollment
   id, and one-use commit token as `pending` in a bounded local pending index,
   then writes the exact secret under that native reference;
2. the control plane compare-and-swaps a pending binding carrying that
   enrollment id and commit-token digest into draft PR #1691's expected
   assignment generation;
3. the host reads that exact committed binding and records a local
   acknowledgement before marking the mapping `committed`;
4. a bounded reconciler may tombstone a timed-out pending local reference only
   after an authenticated control-plane read finds no matching binding;
5. because those stores share no transaction, reconciliation re-reads after
   local tombstone; if a late binding appeared, it holds provider launch and
   compare-clears only that exact control-plane enrollment id, token digest,
   and assignment generation;
6. the split-brain path never restores the deleted local secret and requires a
   fresh enrollment.

Native keyrings expose exact-reference set/get/delete, not portable
enumeration. The bounded local pending index is therefore the only
enumeration source for reconciliation. A native reference absent from that
index is unreachable, not discoverable by scanning the keyring. The index
contains no secret material and is updated atomically with the local lifecycle
state.

### 4. The owning authority path depends on fulfillment class

Draft PR #1691 (`constrain-set-engine-provider-authority`) owns requester-owned
local assignment and its shared-reader
`ProviderInvocation -> ProviderLaunchHandle` launch barrier. The shipped D0
path is fake-only/production-denied and therefore cannot be required as
ordinary requester-provider authority. Accepted-market remote execution must
instead use the owner-accepted production B2/distributed-execution authority
contract. The shipped `runner/v1`
`credential_grant_ref` is only a nine-field wire carrier; it lacks universe,
provider, host, and assignment-generation fields, and `ExecutionGrantV1` does
not contain a credential reference. `SandboxRunner` therefore cannot validate
the full custody tuple and this change does not pretend that it can.

Consuming D0's landed `Verified[T]` and execution-record types is type reuse,
not a D0 authority grant. It does not create a production D0 route, make D0
live-acceptable, or upgrade an opaque locator into provider authority.

For requester-owned local execution, the implementable seam is a typed #1691
local-launch adapter that receives the frozen `ProviderInvocation` and exact
`credential_binding_ref`, validates their complete tuple, and crosses #1691's
launch barrier before constructing a provider child. For accepted-market
remote execution, the binding may compose only with the future owner-accepted
production B2 authority envelope. If either path later routes through
`runner/v1`, its owning adapter may copy an already-validated opaque reference
into `credential_grant_ref`; the runner field remains a locator, never a bearer
grant. Fail-closed is absence of the authority required by the selected
fulfillment class, not an empty capability ceiling or fake-only D0 record.

### 5. Dereference occurs at one local launch boundary

For requester-owned local invocation, after destination, credential-owner
principal from verified request/assignment authority, host, assignment
generation, and draft PR #1691's shared-reader
`ProviderInvocation -> ProviderLaunchHandle` barrier validate, the selected
executor resolves the binding once and injects the secret into provider-child
memory/environment. Accepted-market remote execution SHALL use its separately
accepted B2 authority and SHALL NOT receive a requester-local secret merely
because `runner/v1` carries a locator. The secret is never placed in argv,
persisted child config, logs, or server state.

For requester-owned local launch, `ProviderInvocation` carries only the opaque
binding reference plus credential/auth provenance. It never carries resolved
secret material. Only executor-local `start()` may resolve the native secret.

Background, resumed, retried, and scheduled launches derive the credential
owner from that persisted verified authority. They never use an ambient HTTP
subject, daemon process identity, current workspace member, or newly changed
universe ACL as the credential principal.

Rotation/removal fences new launches. In-flight launches either drain under the
captured generation or are cancelled by the explicit compromise policy before
the old native reference is deleted.

### 6. Retirement is a monotonic saga

Each legacy `llm_api_key` slot is keyed by immutable migration id, expected
record digest, assignment generation, and the environment-variable slot plus
stored occurrence derived from exactly `anthropic`, `claude`, `claude-code`,
`openai`, `codex`, `gemini`, `google`, `groq`, `xai`, or `grok`. Missing or
unsupported service is terminal `held_ambiguous`. The exact states are:

`discovered -> held -> notified -> replacement_pending ->
replacement_verified -> rotation_required -> revoked_upstream ->
cutover_committed -> artifacts_deleted -> record_deleted -> closed`.

`held_ambiguous` and `closed_without_replacement` are explicit terminal held
outcomes. `failed_held` is not a backward state transition; it is a retryable
overlay carrying the last committed state and a sanitized failure class, and a
retry may attempt only that committed state's next legal edge. No state other
than `closed` with a current replacement assignment permits provider launch.

Invariants:

- inventory records metadata/field names/digest/byte length only and never
  decodes secret fields;
- no plaintext export or silent migration exists;
- a replacement local reference remains `pending` until exact local provider
  authentication succeeds;
- owner notification, replacement verification, and provider-side
  rotation/revocation precede assignment cutover and deletion;
- `cutover_committed` is a compare-and-swap of #1691 assignment binding and
  generation; failure remains held and cannot delete the legacy record;
- an owner who intentionally declines replacement may reach
  `closed_without_replacement` only through `discovered -> held -> notified ->
  rotation_required -> revoked_upstream -> artifacts_deleted ->
  record_deleted -> closed_without_replacement`, and the assignment remains
  permanently held/setup-required;
- every transition holds the exclusive assignment lock owned by draft PR
  #1691 (`constrain-set-engine-provider-authority`);
- delete is compare-and-delete against the inventoried digest;
- stale generation re-inventories rather than acting;
- idempotency keys are scoped to universe, slot, and generation;
- every materialized artifact is inventoried by canonical path, content or
  metadata digest, credential slot, owner, generation, and reference count;
- a shared, mixed-owner, mixed-generation, changed, or ambiguous artifact is
  refused and keeps the saga held—whole provider homes are never recursively
  deleted merely from a service name;
- only exact owned, digest-matched, single-reference artifacts are deleted
  before the source record;
- malformed or unclassifiable existing vault state blocks every ordinary
  write/replacement and global reset before mutation;
- `openspec/changes/test-identity-and-reset/` must route any legacy
  `llm_api_key` cleanup through this saga and cannot clear the vault directly;
- retries converge to one monotonic state and never resurrect raw material;
- rollback rebinds a new local generation or remains held.

### 7. Administration is not credential authority

A universe admin may configure non-credential universe state but may not
attach an arbitrary binding, resolve, rotate, delete, replace, or use a binding
owned by another principal. Every binding mutation verifies the binding owner
against the persisted request/assignment principal. A shared universe without
an exact persisted credential-owner principal/host/provider/generation match
remains held.

Organization-owned pooling and delegation remain deferred until an accepted
organization identity/authority model exists.

### 8. Prompt prevention is load-bearing

The current first-contact prompt invites a founder to supply an API key.
TinyAssets can stop eliciting it, remove supported secret fields, reject a
supplied canary without echo before application mutation, and protect every
TinyAssets-owned sink. It cannot redact bytes already sent to a client-owned
upstream chatbot transcript. Before runtime, the
`openspec/changes/retire-legacy-live-mcp-tools/` live-MCP owner and production
gateway/deployment owner must inventory the gateway/access logs, MCP middleware
and structured request capture, traces, ledgers, exceptions, and crash
artifacts and assign an owner plus canary proof for each TinyAssets-controlled
sink.

`tinyassets/api/prompts.py` and its packaged mirror require a future exact
claim; they are not part of this review/spec-only write set.

### 9. Concurrency proof is custody-specific

Acceptance requires a named local multi-process race covering pending
enrollment, commit-token publication, local acknowledgement, local tombstone,
late control-plane binding, split-brain compare-clear, rotate, dereference,
revoke, delete, retry, stale-host expiry, and draft PR #1691's launch barrier.
It must prove a unique usable binding, coherent generations, no torn secret
read, and no orphaned or resurrected active native reference.

The full-platform §14 Track J scenarios remain a separate explicit obligation;
they exercise subscribers, bidding, read storms, and presence rather than
credential dereference.

## Risks / Trade-offs

- **Legacy users lose immediate raw-key setup** → return existing typed
  `setup_required/held` guidance to requester-local enrollment; never preserve
  the unsafe path as a shim.
- **Unowned legacy secret cannot be safely revoked** → remain terminally held;
  do not export or delete a still-live upstream key.
- **Control-plane binding is mistaken for authority** → require exact #1691
  local invocation authority or the separately accepted production B2
  authority for market execution; fake-only D0 never upgrades a locator.
- **Rotation races an in-flight launch** → use #1691's shared-reader launch
  barrier plus drain or explicit cancellation before native deletion.
- **Native store unavailable** → fail closed with no file/env fallback.
- **Provider revocation cannot be machine-verified** → accept only an honestly
  labeled owner attestation and remain held until recorded.
- **Existing full-platform load gate is misreported** → name the local proof
  accurately and retain the real Track J deferral.

## Migration Plan

1. Obtain written acceptance from draft PR #1691
   (`constrain-set-engine-provider-authority`) for requester-owned local launch
   and from the distributed-execution/B2 owners for accepted-market production
   authority; keep D0 fake-only/production-denied and the runner opaque.
2. Preserve PR #1736's account-token lifecycle, native-backend allowlist, and
   client-side `OriginClient` protocol unchanged. Land
   `bind-host-principal-to-account` as the authenticated server-side route
   that derives the account principal from verified identity, issues a stable
   server-attested host principal distinct from per-session host-pool rows,
   supports idempotent re-registration/revocation, and exposes the
   authenticated binding read needed by reconciliation. Keep the disjoint
   provider-secret namespace, pending index, commit-token protocol,
   split-brain compare-clear, tombstones, deletion, and rotation in this
   change.
3. Have `openspec/changes/universe-creation/`,
   `openspec/changes/retire-legacy-live-mcp-tools/`, and the live-interface
   owner accept and land a canonical non-secret setup successor—preferably the
   typed `write_graph(target=universe)` candidate—before hidden-tool retirement.
4. Remove raw-key elicitation and supported input fields; reject any supplied
   `llm_api_key` canary at ingress before mutation or durable diagnostic sinks
   and return the existing `setup_required/held` contract.
5. Create a pending local replacement and commit token, publish its binding
   through #1691 assignment CAS, acknowledge the exact token locally,
   reconcile any late-binding/local-tombstone split brain to held, and verify
   exact provider authentication without reading legacy secret bytes.
6. Hold legacy assignments, notify owners, require upstream
   rotation/revocation, commit the replacement cutover, then delete only
   exact-owned artifacts and the digest-matched source record.
7. Enable launch-time local dereference only in the typed #1691 adapter for
   requester-owned execution. Keep accepted-market remote execution blocked
   until its production B2 authority owner accepts the composition.
8. Complete local concurrency, parity, exact-seven `/mcp`, rendered-chatbot,
   and post-fix organic-use gates.

Rollback never re-enables raw deposits or uses legacy records. It disables new
bindings and leaves affected universes held until a corrected local generation
is enrolled.

## Open Questions

- Will the universe/live-interface owners accept the preferred
  `write_graph(target=universe)` successor candidate, or name another existing
  canonical handle before hidden-tool unregistration?
- Will #1691 and distributed-execution/B2 owners accept the
  requester-local/accepted-market authority split while D0 remains
  fake-only/production-denied and the runner stays opaque?
- What provider-revocation attestations are machine-verifiable per provider,
  and which require explicitly labeled owner attestation?
- Which later capability will own organization-pooled credential delegation?
