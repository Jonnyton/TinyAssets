# First-contact authority opposite-provider review packet

**Status:** review input only; not architecture, canonical spec truth, or
implementation authority.

**Freshness:** 2026-07-23 PT against `origin/main` `85c91087`, draft PRs
[#1606](https://github.com/Jonnyton/TinyAssets/pull/1606) and
[#1617](https://github.com/Jonnyton/TinyAssets/pull/1617), and the current
OpenSpec tree.

**Required reviewer:** Claude, after its 2026-07-24 evening PT capacity reset.
Codex authored the initial research. Per `AGENTS.md`, only an independent
opposite-provider source/context re-check can satisfy the planning review gate
for fold-in. It does not itself release tests or runtime work:
`universe-creation` task dependencies, accepted owning-spec updates, and strict
validation still apply.

## 1. Decision requested

Review whether TinyAssets can safely let a newborn universe speak using either
requester-owned resources or an exact accepted-market execution agreement,
while proving that no maintainer, founder, operator, or platform credential,
quota, auth home, hardware, account, or subsidy can become fallback authority.

Return one durable verdict:

- `APPROVE`: the review findings are accepted for fold-in to the owning
  OpenSpec changes; no runtime task begins until those changes are
  updated/validated and that task's explicit dependencies have landed;
- `ADAPT`: list exact normative changes and re-review them;
- `DEFER`: identify the missing owner or prerequisite;
- `REJECT`: identify the unsafe premise and replacement direction.

No runtime implementation, live provider call, market execution, or acceptance
test is authorized by this packet.

## 2. Authoritative current state

1. The active `universe-creation` change is the current owner. It has 6 of 33
   tasks complete. Task 2.0 blocks execution-authority tests and implementation
   until this review is accepted.
2. Birth and execution are already separate transitions. Authenticated opening
   `converse` can atomically create and bind a founder home without a provider
   call. The unresolved transition begins when the universe intelligence tries
   to generate its reply.
3. `tinyassets/universe_server.py::converse` resolves the founder home and calls
   `universe_intelligence.converse`; it does not resolve a request execution
   authority or return the specified structured hold.
4. Reply generation and learning extraction make separate provider calls from
   ordinary `UniverseContext`. They do not share an immutable authority lineage.
5. Provider routing can use a persistent `allowed_providers` ceiling, but a
   ceiling is not positive per-request spending authority. `None` currently
   means the ordinary chain, including configured local/provider fallbacks.
6. The current universe child-environment guard strips normal inherited
   subscription homes when a newborn has no vault. Partial overlay or a
   resolver/materialization exception can retain ambient host authority. The
   current STATUS claim is branch `codex/fail-closed-provider-auth-overlay` at
   `15fac0b4`; its former PR #1609 is closed, so the repaired seam is not
   consumable until that branch is republished/merged or an accepted successor
   is named.
7. `set_engine` persists BYOC/self-hosted/market configuration, but no runtime
   accepted-market execution grant exists. A universe vault record also lacks
   sufficient resource-owner/delegation evidence to prove economic authority.
8. Production evidence shows birth followed by provider exhaustion, not a
   speaking newborn. Existing first-contact reply tests replace the provider
   call with a fake before proving the reply path.
9. Draft PR #1606 supplies part of the persistent provider ceiling and migration
   fence, but its current independent review is `ADAPT`; it intentionally does
   not own request-authority propagation or accepted-market grants.
10. Active change `provider-attempt-receipts` owns the target race-safe provider
    result/receipt seam (STATUS shorthand R2-1b); its runtime remains pending.
    This lane must not create `_last_provider` or a second receipt system.
11. `docs/design-notes/2026-04-18-full-platform-architecture.md` §20—not
    `PLAN.md`—defines BYOC/self-host and accepted-market fulfillment as peer
    user choices and rejects a guaranteed reference-host pool. The host has
    separately directed that the platform provides no compute and that user
    work must not consume maintainer subscriptions. The setup, custody, budget,
    state-machine, and separately modeled compute/model details in this packet
    are proposed adaptations, not consequences already approved by §20. They
    require fold-in to exact owning specs and, where they change PLAN-level
    architecture, explicit host approval.

## 3. Proposed invariant for review

Authorization is route-specific. Ordinary server-side BYOC uses:

```text
eligible server providers
  = current persistent engine ceiling
  ∩ verified positive request grants
  ∩ phase capability/model requirements
  ∩ current privacy, locality, data-scope, and budget policy
```

Requester-tray and accepted-market execution use:

```text
eligible remote executors
  = verified positive request grants
  ∩ signed executor destination and current lease/fence
  ∩ phase capability/model requirements
  ∩ current privacy, locality, data-scope, and budget policy
```

Remote execution does not enter the ordinary server provider router and may
correctly retain an empty persistent `allowed_providers` ceiling.

- Every applicable term is positive authority. Missing/`None` never widens the
  set.
- Server-provider or remote-executor selection and fallback may narrow their
  respective set and may never add to it or cross route classes.
- Reachability, universe ACL, configuration, a copied token, a prompt claim,
  local hardware discovery, a price quote, or an MCP bearer is not positive
  execution authority.
- Birth may complete with an empty set. Provider-backed execution may not.
- The platform provides a control plane, not compute or hidden subsidy.

## 4. Capability ownership and dependencies

| Concern | Owner / required seam | This lane may do |
|---|---|---|
| Founder-home birth and held first contact | active `universe-creation` | Integrate the authority result into first contact |
| Persistent server-provider ceiling and fallback | STATUS R2-1a; draft PR #1606, unlanded and currently ADAPT | Consume the accepted successor's derived eligible-provider seam; do not build a router |
| Ambient credential isolation | STATUS branch `codex/fail-closed-provider-auth-overlay` at `15fac0b4`; former PR #1609 closed | Owner unresolved until republished/merged or superseded; do not consume a hypothetical repair |
| Result-local invocation receipt | active `provider-attempt-receipts`; runtime pending | Extend its accepted returned result with authority dimensions |
| Market quote/ranking | active `paid-market-live-price-discovery` | Discovery only; never positive authority |
| Request/bid/match/claim and logical accounting | active `paid-market-track-e-wave-2-transport` | Consume its accepted terminal handoff; do not duplicate transport |
| Remote executor identity/lease/fence | active `distributed-execution` | Verify and bind its accepted signed result; do not invent a lease protocol |
| Reply and learning personification contract | active `reconcile-universe-personification-relay` | Add/depend on an accepted explicit zero-turn hold exception |
| Current as-built credential truth | active `backfill-credential-vault-shipped-contracts` | Preserve current truth; it is not encrypted target custody |
| Encrypted target custody and scoped secret leases | no accepted owner | `DEFER` setup implementation until an exact reviewed owner/contract exists |
| Organization spending delegation | no accepted organization-authority capability | `DEFER`; keep cross-principal delegation out of the first self-owned slice |

## 5. Required contract adaptations

The top-level active OpenSpec invariant is correct, but these points must become
normative before implementation.

### 5.1 Bind execution venue, not only provider name

Authority must identify the executor backend and invocation locus:

- requester device/tray;
- requester-owned server endpoint;
- accepted market host under its signed lease/fence; or
- an explicitly eligible server-side noninteractive credential route.

A market agreement must cause execution on its claimed host. The central server
must not import a seller credential and turn the job into an ordinary ambient
provider call. A local-tray consumer subscription remains local execution; it
is never uploaded into platform custody.

### 5.2 Define one market handoff

Discovery and live price are not authority. The paid-market and
distributed-execution owners must expose one canonical verified handoff shape
binding:

- authenticated requester/accepting actor and universe/request;
- exact provider/host/executor identity;
- capability, model/version/digest, phase, and execution route;
- quote and offer versions/digests plus bid/match/claim identities;
- locked normalized price, fee, currency/unit basis, and requester ceiling;
- capacity reservation and lease/fence;
- validity, revocation/supersession generation, and replay identity;
- allowed data scope, privacy/locality/compliance claims, and their evidence.

The authority resolver verifies that shape. It does not form, repair, rank, or
settle it, and this lane does not invent parallel `MarketPurchaseMandate`,
`ExecutionAgreement`, lease, or fence primitives when the owning capabilities
already have suitable records. DEX ideas apply to quote transparency, explicit
acceptance, conservation, and receipts—not to treating heterogeneous compute
as a fungible AMM pool.

### 5.3 Make credential admissibility explicit

Server-side BYOC may admit requester-owned API/project/service credentials,
approved enterprise noninteractive credentials, workload identity, or a
validated requester endpoint. Personal ChatGPT/Claude subscription material is
local-tray-only and may not be custodied server-side.

Copying a maintainer token into a universe vault does not prove requester
ownership. Positive owner/delegation evidence is required independently of
storage location.

Provider adapters must start from a minimal allowlisted environment with
isolated `HOME`, `USERPROFILE`, XDG/AppData, cloud profiles, helpers, `.netrc`,
metadata endpoints, sockets, and device surfaces. They overlay only the exact
authorized phase resource. Unknown surfaces or any overlay/materialization
error hold execution.

### 5.4 Separate content, transport, and economic authority

- Universe read/write/admin ACL authorizes content operations only.
- MCP/OAuth identity establishes requester and actor provenance only.
- Resource ownership or explicit spending delegation authorizes compute/model
  use.
- Organization membership alone does not authorize organization funds.
- The newborn, its prompt/self-model, `active_universe`, and stored engine
  configuration cannot create or accept authority.

The initial implementation should support one authenticated requester using
their own resource. Cross-principal and organization delegation should remain a
separate later slice with its own canonical owner.

### 5.5 Reserve worst-case budget atomically

Before every invocation, including retries and both reply/extraction phases:

1. assign a stable tenant-scoped invocation identity and worst-case budget;
2. atomically consume/claim the reservation while validating the current
   grant, expiry, revocation generation, lease/fence, policy, and data scope, or
   bind dispatch to an executor-enforced signed generation that provides the
   same authorization linearization point;
3. dispatch from TinyAssets at most once for that invocation identity;
4. claim at-most-once execution only for backends that durably enforce the same
   idempotency identity;
5. quarantine an uncertain external outcome as `unknown`, preserve its
   reservation, and do not automatically redispatch it;
6. reconcile actual use, and accept a late result or perform any learning write
   only when it proves the same valid fence/generation accepted at dispatch.

Concurrent turns must not oversubscribe the same grant. Re-resolving authority
must not create a free retry. No route may silently create negative margin or a
platform subsidy.

### 5.6 Treat each phase independently

Reply and learning extraction share one request lineage but receive
least-privilege phase views. Reply success does not authorize extraction.
Expiry/revocation between phases is rechecked.

The result state machine must distinguish:

- `held/setup_required`: no complete positive authority existed;
- `queued/awaiting_compatible_capacity`: authority exists, executor capacity is
  not yet available;
- `running`;
- `success`;
- `partial`: reply succeeded while extraction was held/failed;
- `failed/provider_exhausted`: an authorized provider pool was actually tried.

The canonical personification contract currently demands one reply and one
learning turn. It needs an explicit control-plane zero-turn hold scenario or a
dependency on its active owner before this path can ship.

### 5.7 Keep receipt dimensions separate

R2-1b credential origin (`universe`, `host`, `local`, and similar) must not be
used as economic authority. A result-local redacted receipt needs separate
fields for:

- stable invocation/request/authority ids and digests;
- universe, operation, phase, and ordinal;
- provider/model and executor backend/resource owner;
- credential type, origin, and custody class;
- compute/funding authority class (`requester_owned` or `accepted_market`);
- opaque grant/agreement/lease/fence and budget references;
- start/end, outcome including `unknown`, integer usage/cost and unit basis;
- policy/revocation generation and sanitized error class.

It must never contain prompts, completions, emails, secrets, bearer tokens,
authorization headers, endpoint queries, setup challenges, or auth-home paths.
A receipt records a decision; it never releases settlement by itself.

### 5.8 Bind private-data egress

Compute authority includes destination and allowed data categories. A market
host does not receive a founder message, persona bundle, private state, training
data, or artifact merely because it advertises the right model. Private payload
release occurs only after exact agreement, executor, authority, and data-scope
validation.

## 6. Safe setup boundary

A `held/setup_required` response may expose only non-secret setup descriptors:

- missing resource kinds;
- a requester/universe-bound, short-lived, single-use setup challenge;
- a same-origin HTTPS authorization URL;
- an opaque market request/selection reference when market fulfillment is
  allowed;
- expiry and retry guidance.

Provider authorization or static-secret entry happens directly in a separately
reviewed same-origin custody flow. Vendor OAuth uses authorization code + PKCE.
The chatbot, `converse`, MCP arguments, wiki/pages, market rows, logs, and traces
never receive the secret. The setup challenge establishes enrollment continuity
only and cannot execute work.

This is a proposed protocol boundary, not an available custody seam.
Server-side secret enrollment remains deferred until an exact encrypted-custody
owner and reviewed contract exist. A requester-controlled tray can instead
enroll its device/executor identity while keeping provider credentials local.

## 7. Abuse cases the implementation must prove red, then green

1. Newborn plus hostile maintainer Claude/Codex/API/cloud/local credentials
   births successfully, invokes nothing, and returns the structured hold.
2. Partial overlay replaces one auth field while another host account remains;
   no inherited authority reaches the child.
3. Resolver/import/materialization error cannot restore the full provider chain.
4. Removing `CODEX_HOME` cannot rediscover `$HOME/.codex`; equivalent provider,
   cloud, profile, metadata, socket, and device paths are isolated.
5. Selected requester provider failure cannot fall through to maintainer
   Claude, Codex, API provider, or Ollama/local hardware.
6. Cross-tenant, copied, expired, revoked, cached, superseded, or replayed grant
   cannot authorize a new invocation.
7. Concurrent first contacts cannot double-spend one grant or exceed the
   combined reply/extraction budget.
8. Reply authorization cannot leak into extraction after expiry/revocation.
9. Free/BYOC cannot silently upgrade to paid or change executor venue.
10. Market executor cannot receive payload fields outside its agreement scope.
11. Late/unfenced remote results are rejected after cancellation or lease
    expiry.
12. Missing authority is never rewritten as generic provider exhaustion, and
    the chatbot never fabricates the universe's voice.

All pre-approval and contract tests use fake authority and fake executors. No
real provider, subscription, API key, maintainer quota, market funds, or user
data is a test dependency.

## 8. Smallest vertical delivery after approval

### Slice A — fail-closed hold

- Resolve no positive authority by default.
- Prove birth persists while reply/extraction make zero provider calls.
- Return the typed setup hold.
- Consume the separately repaired default-deny provider environment.

This closes the spend/leak safety boundary but intentionally leaves the newborn
unable to speak.

### Slice B — requester-controlled tray/endpoint BYOC

- Enroll one requester-owned tray/endpoint executor identity; keep provider
  credentials and subscription material on that requester-controlled executor.
- Construct an immutable self-owned authority bound to exact requester,
  universe, request, operation, phases, data scope, budget, and expiry.
- Dispatch through the signed remote-executor destination/lease/fence path,
  never the ordinary server-provider/R2-1a router.
- Extend the accepted `provider-attempt-receipts` result seam with separate
  authority dimensions.
- Prove reply relay, partial extraction behavior, concurrency, revocation, and
  retry idempotency with fake executors.

This is the smallest usable P0-closing slice that does not presume platform
secret custody.

### Slice C — server-side BYOC (`DEFER`)

- Name and accept an encrypted-custody/scoped-lease owner and contract.
- Only then enroll an admissible requester-owned API/project/service,
  enterprise noninteractive, or workload-identity resource out of band.
- Route its eligible server-provider set through the accepted PR #1606/R2-1a
  successor.

This slice is blocked and is not an implementation deliverable of this packet.

### Slice D — accepted-market execution

- Consume the paid-market verified handoff and distributed-execution
  lease/fence.
- Execute on the accepted host, never by importing seller credentials.
- Prove queued/running/terminal transitions, bounded private-data release,
  reconciliation, and settlement gating.

Training gangs and organization-funded delegation follow as separate slices
over the same authority grammar.

## 9. Claude review procedure

1. Re-check the primary sources indexed in
   `docs/audits/2026-07-22-request-authority-and-openspec-gaps.md`, especially
   MCP authorization, RFC 9700/8707/8693/8785/9449, OpenRouter routing, Akash
   leases, and Golem agreements.
2. Inspect current main paths:
   `universe_server.py`, `api/first_contact.py`, `api/universe.py`,
   `universe_intelligence.py`, `providers/call.py`, `providers/router.py`,
   provider adapters/base, `credential_vault.py`, and focused tests.
3. Review current `universe-creation`, canonical
   `identity-auth-and-access-control`, `provider-routing`,
   `credential-vault`, `universe-personification-and-relay`,
   `paid-market-economy`, and `distributed-execution`.
4. Treat PR #1617 as candidate detail, not current truth. In particular, do not
   remove as-built credential-vault requirements before a reviewed encrypted
   custody replacement exists.
5. Verify the adaptations in §5 close execution venue, budget, data scope,
   asynchronous state, receipt, and cross-capability conflicts.
6. Leave the verdict in a durable artifact and on the review PR. If `ADAPT`,
   enumerate exact changes and re-review the revised packet/spec.

## 10. Exit criteria for this planning lane

- Claude verdict accepted and durable.
- Required spec adaptations folded into the current owning OpenSpec changes
  without creating a second router, receipt system, vault truth, or market.
- `openspec validate --all --strict` passes.
- `STATUS.md` file claims are broadened to exact runtime/tests only after
  dependencies and ownership are clear.
- Implementation begins with red fake-only tests and never uses maintainer
  resources as proof.
