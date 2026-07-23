## Context

First-contact birth and provider execution are separate transitions. The canonical `identity-auth-and-access-control` spec already allows an authenticated opening `converse` to create and bind one home universe while explicitly declining to promise provider execution. The active `universe-creation` change further requires a complete requester-owned or requester-accepted market authority bundle, bundle-constrained fallback, `held/setup_required` outcomes, and per-phase receipts. It does not yet define the executable authority value, delegation boundary, market-grant proof, safe setup channel, or replay/revocation rules.

Today `UniverseContext` contains only the universe directory and configuration, provider routing can read a persistent `allowed_providers` ceiling, and `ProviderResponse` has provider/model telemetry but no request authority or phase receipt. `converse` constructs one context and makes separate reply and learning-extraction calls. Draft PR #1606 hardens the persistent ceiling and CLI credential isolation but intentionally does not create request authority or accepted-market grants.

The public MCP surface remains exactly seven handles. Raw provider secrets cannot safely traverse chatbot messages or MCP tool arguments because those surfaces may be retained by the chatbot, connector, application logs, or traces. TinyAssets supplies a control plane, not hidden compute: maintainer, founder, operator, and platform resources are never an emergency fallback for another principal.

Current standards inform the shape without forcing TinyAssets to become a general OAuth authorization server for compute. OAuth security guidance favors audience-restricted, least-privilege, sender-constrained, short-lived credentials and explicit subject/actor delegation. Open compute markets separate demand, offers, acceptance/agreement, execution, and settlement. OpenRouter demonstrates request-level provider/model/privacy/price constraints, but its account-funded fallback is not a TinyAssets authority source.

## Goals / Non-Goals

**Goals:**

- Make the existing first-contact authority invariant implementation-ready.
- Give every provider invocation one immutable, request-scoped authority object whose eligible resources are derived rather than rediscovered.
- Separate content access, execution delegation, payment authority, and the acting chatbot.
- Admit requester BYOC and accepted-market grants through one verification boundary while preserving their different ownership and settlement semantics.
- Define safe setup, phase propagation, holds, receipts, expiry, revocation, idempotency, and replay behavior.
- Preserve the existing provider ceiling and R2-1b result-object receipt as the only selection and receipt seams.

**Non-Goals:**

- Adding an eighth MCP handle or accepting raw provider keys through `converse`, `write_graph`, pages, logs, or market rows.
- Implementing provider routing, a vault UI, market transport, settlement, training, graph execution, or runtime code in this change.
- Treating universe ACL membership, platform operator status, process reachability, or a provider configuration entry as spending authority.
- Implementing paid-market ranking, agreement/reservation formation, distributed-training group formation, settlement, or the distributed-execution lease protocol; this seam consumes their verified outputs.
- Selecting a blockchain, token, exchange mechanism, or platform-owned compute fleet.

## Decisions

### D1 - One sealed request authority, assembled from separately verified grants

The resolver produces an immutable, strict-schema `RequestExecutionAuthority` before any provider-backed phase. Unknown fields or versions fail closed, and only the trusted server composition root may construct it; caller JSON, config rows, caches, requests, and receipts can never create positive authority:

| Field | Meaning |
|---|---|
| `schema_version` | Version of this contract; unknown versions fail closed. |
| `authority_id` | Opaque unique identifier for this resolution, never a bearer secret. |
| `request_id` | Server-issued globally unique stable idempotency key for the user turn or graph run. |
| `request_digest` | Canonical digest of the exact operation, target, and inputs; authority cannot be rebound to different work. |
| `operation` | Authorized public operation such as `converse` or `run_graph`. |
| `invocation_ids` | Domain-separated ids derived from schema domain, requester issuer/subject, universe, request id/digest, operation, phase, and ordinal; they survive re-resolution and fence spend/replay without cross-tenant aliasing. |
| `requester_principal_id` | Stable issuer/subject identity of the human, service, or organization on whose behalf the operation runs. |
| `actor_principal_id` | Stable issuer/subject identity currently performing or accepting the action; may equal requester or act through delegation. |
| `oauth_client_id` | MCP/application transport client provenance when known; it never grants content or spending authority. |
| `resource_owner_principal_id` | Principal that owns/pays for the admitted credential, compute, model access, or organization budget. |
| `delegation_id` | Explicit grant from resource owner to requester/actor when they differ; absent for truly self-owned resources. |
| `universe_id` | Tenant/resource audience. Authority for one universe cannot cross into another. |
| `phase_requirements` | Required resource kinds, route ids, invocation/token/time/cost limits, and capability constraints for each phase. |
| `phase_grants` | Verified requester-owned grant references or exact accepted market agreement references admitted to each phase. |
| `issued_at`, `not_before`, `expires_at` | Short request lifetime with bounded clock-skew policy; expiry never exceeds the shortest admitted grant or agreement. |
| `revocation_snapshot` | Epoch/version checked again at every authority sink. |
| `policy_digest` | Digest of the persistent ceiling and request policy used to derive the bundle. |
| `evidence` | Positive authority from an M1 purpose-separated signature or M3 fresh external reconfirmation, plus M2 content digests that bind exact bytes inside that verified authority. M2 never proves authorization or truth by itself. |
| `canonicalization`, `authority_digest` | Versioned `request-execution-authority/v1` domain prefix, RFC 8785 JSON Canonicalization Scheme, and SHA-256 digest over every security-relevant field. |

A requester-owned `ExecutionResourceGrant` is a verified, non-secret value with `grant_id`, `resource_owner_principal_id`, `accepted_by_principal_id`, `issuer`, `resource_kind` (`compute`, `model_access`, or `bundled`), provider and exact model/capability id/version/digest constraints, permitted phases, universe/resource audience, `issued_at`/`not_before`/`expires_at`, revocation epoch, budget ceiling where applicable, and typed evidence. A vault locator or broker capability reference may be present; raw credentials and bearer tokens may not.

Market authority has three immutable layers instead of overloading that grant:

1. `MarketPurchaseMandate`: the requester-signed demand boundary—resource/model capability, phases, provider/venue constraints, privacy/compliance/locality predicates, maximum unit and total all-in spend, currency, expiry, and any bounded delegate.
2. `ExecutionAgreement`: the exact accepted provider offer/lease—mandate id/digest, accepting principal and optional bounded delegation, acceptance time/idempotency identity, provider or daemon identity/key, reserved capacity, locked normalized integer price/fees and unit basis, capability/manifest/terms digests, allocation or escrow reference, `issued_at`/`not_before`/`expires_at`, typed evidence, sender binding, and current lease fence.
3. `RequestExecutionAuthority`: references only agreements that satisfy the mandate and the other authority intersections; neither the live quote nor mandate is executable by itself.

Completeness is computed per phase. A phase is executable only when its required compute and any separately required model access are covered by compatible grants. One bundled provider grant may cover both only when that provider's execution contract actually supplies both.

Alternative: pass a provider name and key locator. Rejected because it loses principal, phase, budget, expiry, delegation, and market evidence and encourages later code to rediscover ambient credentials.

### D2 - Content ACL and execution delegation are orthogonal

Universe `read`/`write`/`admin` grants authorize content operations only. They never authorize spending the founder's, another collaborator's, an organization's, or a market buyer's resources.

The default requester is the authenticated `(issuer, subject)` pair, never an email or display name. A collaborator therefore uses their own BYOC or a market grant they accepted. Use of founder-owned or organization-owned resources requires a separate execution delegation bound to the resource owner, requester, current actor, universe, allowed operations/phases/providers/models, budget, validity window, and revocation epoch. The acting chatbot/client id is transport provenance and cannot widen that delegation. Organization administrators may issue organization-resource delegations, but membership alone is insufficient.

Alternative: make a universe's configured engine available to every ACL member. Rejected because content collaboration and financial/resource delegation have different risk and revocation boundaries.

### D3 - Authority only narrows at each boundary

For each phase:

```
eligible = persistent_engine_ceiling
           INTERSECT verified_request_grants
           INTERSECT phase_requirements
           INTERSECT current_policy_and_privacy_constraints
```

`None` in a legacy persistent ceiling is not positive request authority. An empty intersection is a setup/policy hold. Provider selection, retry, fallback, and model substitution operate only inside the derived set. They may narrow further for availability, price, privacy, latency, or capability; they cannot add a provider or resource.

The sealed object remains immutable, but every provider invocation re-checks its digest and exact request binding, time validity, revocation epoch, persistent-ceiling version/digest, budget reservation/fence, request and universe audience, phase, and evidence status at the authority sink. A changed fact causes a hold and a newly resolved authority on retry; no field is mutated in place. Accepted-market token exchange does not imply automatic revocation propagation, so current introspection/epoch/fence checks are explicit.

Before dispatch, the server atomically reserves a stable, tenant-scoped `invocation_id = digest(domain, requester issuer/subject, universe_id, request_id, request_digest, operation, phase, ordinal)` plus its budget. The id survives authority expiry, revocation, policy change, and re-resolution, while `authority_id` identifies the verification snapshot used for one attempt. A duplicate cannot spend twice, and identical caller-visible request ids in other principals or universes cannot collide. If a network outcome is unknown, the invocation remains consumed/reserved until an upstream idempotency or reconciliation proof resolves it; the server does not issue a free retry under a new authority id.

Alternative: validate once at first contact. Rejected because grants can expire, be revoked, lose budget, or be superseded between reply and extraction or during a graph run.

### D4 - BYOC setup is out-of-band and secretless in chat

A `held/setup_required` response includes non-secret setup descriptors, not credentials:

- a short-lived, single-use `setup_challenge_id` bound to requester and universe;
- an HTTPS `authorization_url` for requester-owned credential/device enrollment;
- a non-secret `market_request_id` and HTTPS market-selection URL when market fulfillment is allowed;
- missing resource kinds, expiry, and retry guidance.

The user completes secret entry or provider authorization directly with the credential-custody/provider flow over same-origin HTTPS. Completion atomically verifies the challenge is unused/unexpired, re-authenticates the exact `(issuer, subject)`, re-authorizes current universe/tenant access and any delegation, verifies the credential-store owner, uses exact redirect origins and CSRF state, and uses authorization code plus PKCE for vendor OAuth. A static-key fallback posts from a masked browser form directly to encrypted KMS/secret-manager custody; base64 is not encryption. The chatbot and MCP request never receive the secret. The inbound MCP/WorkOS bearer token authenticates TinyAssets only: it may derive requester identity but is never stored, exchanged, forwarded upstream, or treated as provider/market authority. The setup challenge proves continuity to enrollment but is not itself execution authority. After completion the user retries the original `converse`; the server resolves fresh authority. The trusted broker may vend only a purpose/route/phase/job-scoped ephemeral secret lease and destroys it after use.

Alternative: ask the user to paste a provider key in chat or place it in `write_graph` text. Rejected because chat, tool arguments, traces, and logs are not a secret-entry boundary.

### D5 - Accepted-market authority requires mandate, agreement, and current lease

Market discovery, bidding, and price comparison do not confer execution authority. In the owning paid-market lane, the requester first issues or confirms a `MarketPurchaseMandate`; that lane filters hard constraints, ranks adequate offers by normalized all-in cost and declared quality, and creates one exact accepted `ExecutionAgreement`. This authority seam receives only that exact agreement and verifies whether it can enter request authority.

The mandate and agreement together bind:

- mandate id/digest, accepted offer/agreement, buyer/requester principal, accepting principal, optional bounded delegation id, acceptance timestamp/idempotency identity, and proof that the actor acted inside the mandate;
- the target universe/request audience and resource/phase scope;
- provider/host identity plus exact capability/model id/version/digest, execution interface/route, privacy/compliance, locality, license/access, and availability constraints;
- normalized price basis, buyer unit and total ceilings, locked all-in price/fees, reserved maximum, currency/unit, and settlement fence;
- issuance, not-before, expiry, bounded skew, revocation, supersession, and replay/idempotency identity;
- typed evidence for every authority-bearing privacy/compliance/locality claim: registered type and issuer/trust basis, bound provider/endpoint/hardware subject, issue/expiry times, and positive M1 purpose-separated signature or M3 fresh external reconfirmation; M2 digests bind the exact verified bytes but cannot mint authority;
- a verifiable platform/market decision record or externally re-confirmed fact;
- sender binding to the authenticated executor at use time through DPoP, mTLS, or the distributed-execution device-key signed-request mechanism.

The paid-market successor owns offer filtering/ranking, requester or bounded-router acceptance, compare-and-set reservation, and exact agreement formation. It may let a bounded delegate select the cheapest adequate offer inside the mandate without requiring the user to click each offer, but the exact agreement records and proves that bounded acceptance. This authority seam only verifies and admits that exact agreement. The tightest mandate, agreement, persistent policy, and phase constraint wins. The agreement—not the quote, price index, mandate, or router preference—is the market authority. Provider advertisements and self-attested compliance labels are discovery inputs only.

Public/shared demand exposes only the minimum redacted capability and constraint summary plus content digests. Prompts, private inputs, training data, artifacts, and scoped data references are released only to the exact accepted provider after agreement and request-authority validation.

Separate compute and model-access agreements may compose only when their exact model/capability identity/version/digest, execution interface/route, phase, audience, overlapping validity, privacy/locality policy, and license/access terms are compatible. Any mismatch holds the phase before dispatch.

Distributed training that needs multiple devices or hosts is admitted only from a paid-market-owned group agreement keyed by the canonical training instrument (`hardware class × interconnect tier × gang size × window`) with frozen full membership, interconnect compatibility, a common start/window/fence, and one group allocation/escrow identity. This seam verifies the group before admission; it does not form or reserve the group. No sublease is independently executable or payable until the full compatible set is reserved. Existing formation, checkpoint, payment, and settlement rules remain owned by paid-market capabilities.

Alternative: treat the best available quote as executable or use an AMM-style price as authority. Rejected because compute is heterogeneous, expiring, non-atomic, failure-prone capacity; quotes are mutable advertisements without acceptance, allocation, compatibility, or payment authority. Exchange ideas apply to transparent quotes, ceilings, immutable acceptance, and conservation receipts—not fungible-pool execution.

### D6 - Phases share an authority lineage but receive least privilege

Reply and learning extraction for one `converse` request may share one request-authority lineage. Each invocation receives only its phase view, not every grant or secret reference in the bundle. Reply success does not silently authorize extraction. If reply is covered and extraction is not, the result is `partial`: the reply is returned, extraction is held, and separate phase outcomes explain the boundary. Every separately initiated `run_graph` has a new request id, exact operation/input digest, and authority; it never inherits a chat authority.

Alternative: treat extraction as internal bookkeeping. Rejected because it is a second billable/provider-backed call and can otherwise escape the requester's budget or provider policy.

### D7 - Result envelopes and receipts are typed, redacted, and race-safe

The public outcome is one of `success`, `partial`, `held`, or `failed`. `held` is pre-dispatch and uses a stable reason such as `setup_required`, `authority_expired`, `authority_revoked`, `budget_unavailable`, or `policy_blocked`. `failed` means an authorized invocation was attempted and can include `provider_exhausted`; it is never rewritten as an authority hold. Outcomes expose `request_id`, `authority_id`, `universe_id`, phase states, missing resource kinds, and non-secret setup descriptors.

Each attempted invocation extends R2-1b's returned result object with a receipt containing `receipt_id`, stable `invocation_id`, authority/request ids and digests, universe, turn/run id, phase and ordinal, redacted route/endpoint-audience digest, provider/model identity, authority class, stable redacted principal/actor and mandate/agreement/grant/evidence references, start/end timestamps, outcome including `unknown`, upstream request/idempotency id, integer usage and cost with explicit unit basis, quoted and actual all-in price/fees, currency, budget/group-allocation/fence reference, policy digest, revocation epoch, and sanitized error class. A canonical private endpoint may appear only in a tenant-private access-controlled receipt class required by policy. Receipts never contain prompts, completions, emails, raw credentials, authorization headers, bearer tokens, endpoint queries, setup challenges, or provider auth-home paths. Persistence is unique by `invocation_id`, append-only/idempotent, and never uses a process-global last-provider value.

An invocation/authority receipt records a decision and never releases payment. Settlement requires the exact agreement, terminal independently verified execution evidence, and the canonical oracle/transaction receipt. Provider self-report is insufficient. Unknown outcomes keep reservation and settlement fenced until reconciliation.

Alternative: log the selected provider after the call. Rejected because concurrent calls race and logs do not form a typed, redacted, correlated accounting record.

### D8 - Provider execution defaults deny ambient authority

Every provider adapter declares its credential/resource surfaces: API-key environment variables, CLI subscription auth, home/profile/config directories, cloud metadata/credential chains, local sockets, hardware devices, in-process clients, and brokered market capabilities. For an explicit request authority, the adapter starts from a minimal denied/isolated environment and empty home/cloud-profile roots, then overlays only the referenced resource needed for that phase. It never copies the ambient environment and deletes known names. Unknown or undeclared surfaces make the adapter ineligible, and isolation errors fail closed.

Self-hosted endpoints are authority fields, not arbitrary router strings. They require canonical HTTPS audiences, explicit requester ownership/consent, no userinfo or fragments, controlled redirects, and SSRF/DNS-rebinding/cloud-metadata defenses. Private/LAN endpoints require an explicit reviewed policy rather than public-server reachability. Every remote or accepted-market grant is sender-bound at each use to the authenticated executor through DPoP, mTLS, or the existing device-key signed-request mechanism; cross-daemon or key-substitution replay is rejected. Third-party static BYOC keys whose vendors cannot sender-constrain are separately risk-classified and do not weaken market transport.

Fake-only contract and mutation tests must seed hostile maintainer credentials, homes, profiles, cloud metadata, hardware, and accounts and prove none become eligible. Live proof later uses only host-provided reviewed test authority; project maintainer quota is never a test dependency.

Alternative: scrub a denylist of known variables. Rejected because provider credential surfaces evolve and omissions fail open.

### D9 - This is the authority integration contract, not a duplicate implementation lane

This change refines and supersedes only the overlapping authority contract/work in active `universe-creation` tasks 2.1-4.7. Once draft PR #1606 and current owners clear, coordination must replace those tasks with dependencies/references to this change before runtime edits begin. `universe-creation` keeps birth, lifecycle, root migration, and final first-contact acceptance ownership.

This change consumes existing seams rather than recreating them: draft PR #1606's persistent ceiling, R2-1b's result object, credential custody, paid-market-created exact agreements/group agreements, and distributed-execution verification/fences. Market ranking/acceptance/reservation, group formation, and settlement belong to narrow market successors. Until ownership is reconciled, this lane is planning/review only.

## Risks / Trade-offs

- **[Authority object becomes a second router]** -> It contains verified eligibility evidence only; draft PR #1606 remains the persistent ceiling and the existing router remains the selection/fallback implementation.
- **[Short-lived grants interrupt a multi-phase turn]** -> Revalidate per phase and return an explicit partial/held outcome; never extend validity silently.
- **[Delegation model adds setup friction]** -> Default self-owned authority needs no delegation; cross-principal spending requires explicit, narrow consent because the alternative is unauthorized cost.
- **[Market claims are self-attested]** -> Quotes are never authority; require acceptance plus verified/fenced grant evidence and preserve capability claims in receipts for later dispute/reputation.
- **[Setup links leak]** -> Challenges are short-lived, single-use, requester/universe-bound, non-executable, redacted from receipts, and completed only after re-authentication.
- **[Provider isolation matrix decays]** -> Each adapter owns an explicit surface declaration and mutation tests; unknown surfaces fail closed.
- **[Endpoint authority becomes SSRF]** -> Canonicalize and validate the audience, resolve/re-check addresses, reject metadata/private ranges unless an explicit private route is authorized, and constrain redirects.
- **[Receipt detail becomes sensitive telemetry]** -> Store identifiers/digests and minimum accounting fields; exclude content and secret material; apply tenant access and retention policy.

## Migration Plan

1. Land this planning change as review-blocked; do not sync its requirements as as-built.
2. Obtain Claude's independent primary-source and TinyAssets security review after capacity resets; incorporate every `adapt` item and re-review.
3. Land and live-verify draft PR #1606's persistent ceiling/migration. Land R2-1b's race-safe result-object receipt seam.
4. Add fake-only contract tests for self-owned, delegated, accepted-market, partial, expired, revoked, replayed, concurrent, and hostile-ambient cases.
5. Implement the immutable resolver, verified grant adapters, phase propagation, and structured outcomes incrementally behind a default-off capability flag.
6. Add the out-of-band setup/enrollment route without changing the seven-handle set; separately complete the required auth/security review for that public flow.
7. Run focused tests, strict OpenSpec validation, concurrency/load proof, credential-leak scans, public canaries, and rendered chatbot acceptance.
8. Enable gradually. If any authority ambiguity appears, disable provider-backed execution while preserving the born/bound universe and returning a hold. Rollback never restores ambient fallback.

## Open Questions

- Which existing web surface will host the short-lived BYOC setup and market-selection flows? This requires a separate reviewed auth/UI change; the protocol contract here is independent of its route name.
- Which exact market decision record will mint accepted grants after the stale Wave 2 lane is split into a current transport change?
- Which receipt fields are retained for each regulatory standards pack, and for how long? The core receipt stays minimal; industry-specific retention belongs to policy packs.
- Which sender-binding mechanism applies to each remote executor class remains adapter-specific; proof of possession itself is mandatory for remote and accepted-market grants.
