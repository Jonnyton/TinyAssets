# Request authority, open compute markets, and remaining OpenSpec gaps

**Freshness:** 2026-07-22 PT
**Initial provider:** Codex
**Repository baseline:** `origin/main` at `2190f65d03f58ef8cb619b3eefbf0a13588d4828`
**Status:** Research and spec proposal only. Runtime implementation is blocked on an independent Claude security review after its 2026-07-24 evening PT capacity reset.
**User constraint:** TinyAssets provides the control plane, not user compute. A user's work may use that user's BYOC resources or an exact market agreement they accepted; it never consumes project maintainer/founder/operator credentials, subscriptions, quota, accounts, hardware, or hidden platform compute.

## Executive judgment

TinyAssets has the right top-level shape: a neutral, chatbot-first control plane over user-owned and permissionless market resources. The missing center is not another provider router. It is an explicit authority and agreement layer between intent and execution.

The clean system is:

```
chatbot / organization adapter
  -> authenticated TinyAssets control plane
  -> policy + request execution authority
  -> requester BYOC grant OR exact accepted market agreement
  -> provider/model/host execution through one bounded protocol
  -> correlated usage/effect receipt
  -> settlement, reputation, lineage, and audit
```

This structure supports inference, fine-tuning, distributed training, model hosting, software automation, and later physical fabrication without pretending they are fungible. The shared primitives are typed demand, verifiable capability, bounded mandate, exact agreement/lease, execution fence, evidence, receipt, and settlement. Each domain retains its own executor and verification rules.

The DEX analogy is useful only at the edges: transparent quotes, price ceilings, deterministic matching, immutable acceptance, conserved fees, and auditable settlement. Constant-product pools and permissionless token swaps are the wrong execution model because compute is heterogeneous, perishable, failure-prone, locality/privacy-sensitive, and often non-atomic.

The immediate P0 is the first-contact authority handshake. The new OpenSpec change `define-first-contact-authority-handshake` makes that seam implementation-ready without touching runtime. It also corrects a current unsafe shape: raw provider keys can cross public MCP/chat JSON and are stored as base64-equivalent data; provider isolation starts from ambient environment state and removes known names. Both must be replaced, not extended.

## Source freshness and canonical sources

All external facts below were re-checked against primary official sources on 2026-07-22.

### Authorization and interoperability

- [Model Context Protocol authorization specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization): protected-resource metadata, resource indicators, audience validation, PKCE, and no token passthrough.
- [OAuth 2.0 Security Best Current Practice, RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html): least privilege, audience restriction, sender-constrained tokens, and replay defenses.
- [OAuth Resource Indicators, RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html): resource/audience binding and tenant-specific audiences.
- [OAuth Token Exchange, RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html): subject/actor/delegation vocabulary and the warning that token exchange does not automatically propagate revocation.
- [OAuth Rich Authorization Requests, RFC 9396](https://www.rfc-editor.org/rfc/rfc9396.html): structured locations/actions/data types/privileges as inspiration for phase/resource constraints.
- [JSON Canonicalization Scheme, RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html): versioned deterministic JSON bytes for request and authority digests.
- [DPoP, RFC 9449](https://www.rfc-editor.org/rfc/rfc9449.html): sender-constrained proofs, unique request ids, URI/method binding, access-token hashing, and nonce-based replay defense.
- [OAuth token revocation, RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.html) and [token introspection, RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html): explicit current-state checks where supported.

### Inference routing and open compute markets

- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): request-level provider allow/deny/order, fallbacks, required parameters, privacy filters, zero-data-retention, price, throughput, and latency constraints.
- [OpenRouter management keys](https://openrouter.ai/docs/guides/overview/auth/management-api-keys), [guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview), and [workspaces](https://openrouter.ai/docs/guides/features/workspaces/overview): separate administrative keys, per-key budgets, model/provider restrictions, team/workspace isolation, and observability.
- [OpenRouter provider logging/data policy](https://openrouter.ai/docs/guides/privacy/provider-logging): provider-specific retention/training differences and request/account policy filters.
- [Akash deployments](https://akash.network/docs/learn/core-concepts/deployments/) and [providers/leases](https://akash.network/docs/learn/core-concepts/providers-leases/): deployment demand, order, bid, explicit provider choice, lease, resource reservation, price, attributes, and provider audit filters.
- [Golem requestor/provider interaction](https://docs.golem.network/docs/creators/common/requestor-provider-interaction) and [Golem overview](https://docs.golem.network/docs/golem/overview): demand/offer negotiation, bilateral agreement, execution activity, billing notes/invoice, and provider/requestor symmetry.
- [Uniswap whitepaper](https://docs.uniswap.org/whitepaper.pdf): reviewed only to bound the DEX analogy; its fungible AMM does not map to executable compute capacity.
- [Kubernetes Dynamic Resource Allocation](https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/): structured device claims and scheduler-visible resource availability as an executor-side reference, not a global TinyAssets market.

### Organizations and regulated work

- [HHS cloud computing guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html): a cloud service provider that creates, receives, maintains, or transmits ePHI for a covered entity/business associate can itself be a business associate even if data is encrypted and it cannot view the data.
- [HHS sample BAA provisions](https://www.hhs.gov/hipaa/for-professionals/covered-entities/sample-business-associate-agreement-provisions/index.html): permitted uses, safeguards, incident reporting, individual-rights support, return/destruction, and subcontractor obligations.
- [HHS Security Rule summary](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html), [Privacy Rule summary](https://www.hhs.gov/hipaa/for-professionals/privacy/laws-regulations/index.html), [breach notification](https://www.hhs.gov/hipaa/for-professionals/breach-notification/index.html), and [de-identification guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/de-identification/index.html).
- [HHS certification FAQ](https://www.hhs.gov/hipaa/for-professionals/faq/2003/are-we-required-to-certify-our-organizations-compliance-with-the-standards/index.html): private certifications do not discharge HIPAA obligations; TinyAssets must not market a generic “HIPAA certified” state.
- [NIST OSCAL 1.0 announcement](https://www.nist.gov/news-events/news/2021/06/nist-has-developed-open-security-controls-assessment-language-oscal-100) and [NIST SP 800-66r2](https://csrc.nist.gov/pubs/sp/800/66/r2/final): strongest reference for versioned control/assessment/evidence packs and HIPAA-to-NIST mapping.
- [SCIM protocol, RFC 7644](https://www.rfc-editor.org/rfc/rfc7644.html), [WorkOS organizations](https://workos.com/docs/authkit/users-organizations), [Directory Sync](https://workos.com/docs/directory-sync), and [roles/permissions](https://workos.com/docs/authkit/roles-and-permissions): organization lifecycle, directory/group mapping, and deprovisioning inputs.
- [Slack request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/) and [Slack security](https://docs.slack.dev/concepts/security/): signature/replay verification and least-privilege scopes for a control adapter.

### Zapier-class automation

- [Zapier product overview](https://help.zapier.com/hc/en-us/articles/37518970271245-What-is-Zapier): current workflow, MCP, SDK, Tables, Forms, and Agents surfaces over a 9,000+ app catalog.
- [Zapier trigger model](https://docs.zapier.com/integrations/build/cli-hook-trigger), [deduplication](https://docs.zapier.com/integrations/build/deduplication), [actions](https://docs.zapier.com/integrations/build/action), and [searches](https://docs.zapier.com/integrations/build/search): polling/instant triggers, event identities, typed actions, searches, and find-or-create.
- [Zapier Paths](https://help.zapier.com/hc/en-us/articles/8496288555917-Add-branching-logic-to-Zap-workflows-with-Paths), [delays](https://help.zapier.com/hc/en-us/articles/8496288754829-Add-delays-to-Zap-workflows), and [loops](https://help.zapier.com/hc/en-us/articles/42969233918477-Understanding-Looping-by-Zapier): control-flow coverage tests.
- [Zapier authentication](https://docs.zapier.com/integrations/build/auth) and [app connections](https://help.zapier.com/hc/en-us/articles/36818633398157-App-connections-on-Zapier): reusable per-account connections, refresh, sharing, transfer, expiration, and managed connections.
- [Zapier replay](https://help.zapier.com/hc/en-us/articles/19220226086797-What-is-replay), [error handlers](https://help.zapier.com/hc/en-us/articles/22495436062605-Set-up-custom-error-handling), [limits](https://help.zapier.com/hc/en-us/articles/8496181445261-Zap-limits), and [integration operating constraints](https://docs.zapier.com/integrations/build/operating-constraints): run history, retry, holds, quotas, and throttling.
- [Zapier organization roles](https://help.zapier.com/hc/en-us/articles/47031545308557-Roles-and-permissions-in-organizations-and-workspaces), [app policies](https://help.zapier.com/hc/en-us/articles/8496307974541-App-access-policies-in-Zapier), and [SCIM](https://help.zapier.com/hc/en-us/articles/8496291497741-Provision-user-accounts-with-SCIM): workspace governance and provisioning.

## Frontier convergence

The frontier is converging on five interoperable planes rather than one vertically integrated AI vendor:

1. **Design plane:** a model, workflow, application, evaluator, device, or fabrication job is an immutable/versioned design artifact with lineage.
2. **Control plane:** identity, policy, demand, planning, collaboration, routing, budgets, and receipts remain available without owning the execution fleet.
3. **Resource plane:** user-owned devices, provider APIs, organization resources, and permissionless market hosts expose typed capabilities.
4. **Agreement plane:** a mandate constrains selection; an exact agreement/lease binds provider, capability, price, privacy, capacity, validity, and settlement.
5. **Evidence plane:** signed/content-addressed/external facts, execution receipts, evaluations, and provenance determine acceptance, payment, reputation, and reuse.

Interoperability belongs at these typed boundaries. TinyAssets should not standardize one model runtime, GPU vendor, cloud, chain, or maker machine. It should standardize what a requester needs, what a provider proves, what was accepted, what ran, what it produced, and what was paid.

## The correct live-price and routing model

### Discovery is not authority

A live price index is a read model over executable offers and recent settled receipts. It can answer “what is the best adequate ask now?” but cannot authorize execution. Stale, incompatible, privacy-violating, unfunded, or unleased offers must never become the displayed executable best price.

### Three immutable market layers

1. **Market purchase mandate:** requester or bounded delegate states resource/model capability, phases, privacy/compliance/locality constraints, allowed venues/providers, maximum unit price, maximum total all-in spend, currency, expiry, and fallback policy.
2. **Execution agreement/lease:** one exact provider offer is accepted, capacity and funds are reserved, normalized price and fees are locked, capability/manifest/terms digests and provider identity are fixed, and a current lease fence prevents stale work.
3. **Request execution authority:** one request references requester-owned resource grants and/or exact accepted agreements, intersected with persistent universe/organization policy and phase scope.

Effective authority is always an intersection:

```
universe/org ceiling
  INTERSECT authenticated requester/delegate mandate
  INTERSECT requester grant or accepted provider agreement
  INTERSECT phase requirements
  INTERSECT current unexpired/revocation/budget/lease fence
```

The tightest price, provider, model, privacy, locality, retention, and spend constraint wins. Incompatibility produces `held/setup_required` or a more exact policy/budget/expiry hold; it never weakens policy or silently falls back.

### Ranking

Filter hard constraints first. Rank only executable survivors by normalized all-in cost:

- provider usage;
- startup and minimum charges;
- model-token or accelerator-time units;
- storage and egress;
- platform fee;
- declared quality, throughput, latency, reliability, and evidence freshness.

Price arithmetic and usage are integers in normalized units, not floats. The accepted agreement locks a provider-specific price/expiry. Receipts report actual usage, charge, fee split, evidence, and terminal result.

### Inference and model hosting

An independently designed model becomes a versioned model artifact plus training recipe, dataset references/consents, evaluator gates, runtime/quantization requirements, and lineage. Training uses requester BYOC or market agreements. A host later advertises an inference capability bound to the exact model digest/runtime and can compete on price, throughput, latency, privacy, geography, and reliability. Users pay through the same mandate/agreement/authority/receipt path.

OpenRouter is useful inspiration for provider preferences, max price, capability filtering, privacy, fallbacks, workspaces, and usage receipts. TinyAssets must not copy its central account credits as an authority root or permit fallback beyond the signed mandate.

### Training compute

Single-host training can use one agreement. Distributed training requires an atomic group agreement: compatible devices/hosts, common topology and start, synchronized lease fence, and all-or-none reservation. No sublease becomes executable or payable until the whole group is ready. Checkpoint lineage and evaluation evidence chain to the group agreement and settlement.

### Physical fabrication and the builder community

3D printers, CNC machines, PCB assemblers, and other maker resources fit the same market grammar but not the same executor. Their typed capability includes material, dimensions/tolerances, process, location/shipping, queue time, calibration/evidence, safety constraints, and inspection/acceptance. The first slice should reuse mandate/agreement/evidence/settlement primitives while keeping fabrication executors, custody, disputes, and physical-world safety in a separate OpenSpec capability.

## Request authority contract

The new OpenSpec change modifies both `identity-auth-and-access-control` and `credential-vault` and defines:

- `RequestExecutionAuthority`: strict, immutable, server-constructed, exact-request/universe/operation/phase/budget bound, with a canonical digest and verified evidence references.
- requester-owned grants: opaque vault/device/broker references, never secret values;
- market mandates and exact agreements: discovery and acceptance stay separate;
- explicit delegation: universe ACL membership never implies permission to spend another principal's resources;
- secretless setup: short-lived same-origin HTTPS enrollment descriptors; vendor OAuth uses code + PKCE; static keys go directly to encrypted credential custody, never chat;
- per-phase revalidation: expiry, revocation, persistent ceiling, budget, capacity, audience, evidence, and lease fence;
- atomic invocation/budget reservation and idempotent reconciliation for unknown outcomes;
- typed `success`, `partial`, `held`, and authorized-attempt `failed` outcomes;
- append-only, race-safe, redacted receipts that record but never create authority;
- default-deny provider isolation and SSRF-safe self-hosted endpoint audiences.

Current implementation gaps supporting the change:

- `tinyassets/providers/base.py`: `UniverseContext` has no requester authority; provider environment construction begins from ambient state.
- `tinyassets/providers/router.py`: persistent `allowed_providers` constrains a universe but is not positive per-request spending authority.
- `tinyassets/universe_intelligence.py`: reply and learning extraction receive only ordinary universe context.
- `tinyassets/api/universe.py`: current `set_engine` accepts a raw `api_key` through JSON; self-hosted endpoints and market settings are persistence shapes, not verified requester grants or exact agreements.
- `tinyassets/credential_vault.py`: current base64/file-permission storage is not encrypted credential custody.

Draft PR #1606 is still valuable: it supplies the persistent provider ceiling and a narrower CLI isolation prerequisite. It does not close the request-authority, setup, market-agreement, phase, or receipt gaps.

## Zapier capability parity without cloning Zapier

“Anything users can do on Zapier” is a valid coverage goal, but Zapier's product categories should be acceptance tests, not TinyAssets' module boundaries. The clean TinyAssets primitive chain is:

```
event source -> typed versioned graph -> durable wait/branch/loop
             -> governed connection effect -> receipt and run history
```

Current coverage:

| Zapier-class capability | TinyAssets assessment |
|---|---|
| Polling and instant webhook triggers with deduplication | Scheduler/event subscriptions are partial; no general connector trigger catalog, polling cursor contract, webhook-ingress resource, or per-connection event identity. |
| Typed create/update/delete actions, searches, find-or-create | Missing as a portable connector/version/operation contract bound to a user-owned connection. |
| Multi-step workflows, filters, paths, loops, subflows, schedules | Mostly composable from branch graphs, conditional edges, cycles, child branches, schedules, and checkpoints; durable arbitrary waits, explicit error branches, and per-step replay semantics remain gaps. |
| Sandboxed Python/JavaScript steps | Not safe as built: public user code must wait for distributed-execution confinement rather than exposing in-process `source_code`. |
| Reusable OAuth/API connections, sharing, transfer, refresh, expiry | Provider/GitHub credentials are special cases; no general encrypted connection lifecycle or credential-blind adapter boundary is as built. |
| Run history, failed-step/whole-run replay, error handlers | Partial statuses/checkpoints exist; destination reconciliation, immutable version-bound replay, and mandatory effect idempotency are incomplete. |
| Tables and Forms | Compose from typed user-owned record collections plus rendered ingress artifacts; do not create siloed parallel products. |
| Agents using knowledge and app actions | Compose universes/daemons, Brain knowledge, graphs, and connection grants. |
| Organization/workspace governance | Major gap; shares the organization/delegation lane described below. |

Recommended OpenSpec decomposition:

1. `connector-catalog-and-connection-grants`
2. `durable-event-ingress-and-trigger-cursors`
3. `replay-safe-external-effect-transport`
4. `run-history-replay-and-error-handlers`
5. `sandboxed-user-code-nodes`
6. `typed-record-resources-and-input-surfaces`

These changes should depend on first-contact/general request authority, encrypted credential custody, and the distributed-execution confinement boundary as applicable.

## User growth and concurrent users

The target architecture can scale, but the as-built deployment has not proven product-scale concurrency. The architecture document correctly targets stateless control-plane replicas, Postgres/RLS canonical state, capability-sharded realtime notifications, compare-and-swap edits, durable host/market claims, and explicit load tests. Current runtime evidence is much smaller:

- one default Uvicorn process;
- local SQLite stores;
- a per-universe JSON queue that rewrites the whole array under a file lock;
- four statically declared workers sharing a local Docker volume;
- process-local provider quota/cooldown state;
- no edge rate limit;
- tests cover small concurrent groups, not 1,000/10,000 public sessions, connector-429 storms, or noisy-neighbor isolation.

BYOC/market execution prevents user growth from consuming platform model quota, but it does not remove control-plane scaling work. The required runtime shape is:

1. stateless MCP/API replicas;
2. Postgres canonical tenant, configuration, run, job, and effect state with enforced tenant isolation;
3. durable partitioned queues with leases, visibility timeouts, held/dead-letter states, and weighted per-tenant fairness;
4. BYOC/market workers pulling owner-bound signed jobs through the distributed-execution protocol;
5. transactional inbox/outbox records for connector events and effects;
6. deterministic effect idempotency keys, intent-before-call journaling, and destination reconciliation;
7. distributed token buckets by tenant/connection/connector/operation that honor upstream `Retry-After`;
8. object storage references rather than large queue payloads;
9. realtime only for presence/notification, never as the durable job queue;
10. burst, steady-state, recovery, quota-exhaustion, tenant-isolation, and noisy-neighbor load proofs.

“Exactly once” should describe the observable external effect, not message delivery. Queue delivery will be at least once; deterministic keys, intent/result journals, destination reconciliation, and immutable receipts make repetition produce one effect.

A dedicated `multi-tenant-control-plane-and-load-admission` change should prove at minimum 1,000 subscriber fanout, a 500-daemon reconnect/claim storm, connector 429 handling, tenant fairness under queue pressure, recovery after worker/control-plane loss, and 10,000 idle sessions. Estimates in a design note are not completion evidence.

## Organizations and shared universes

The correct organization shape is not “a Slack channel owns a universe.” It is:

- first-class organization/tenant;
- org-owned universe whose lifetime does not depend on one employee;
- membership, group, service account, daemon, auditor, and break-glass principals;
- explicit, conditional, expiring delegation and revocation;
- external identity links from Slack, WorkOS/IdP, SCIM, or future systems;
- one TinyAssets policy-decision engine and receipt path.

Slack and similar systems are signed control adapters. They verify the incoming platform request, map its external user/team identity to an existing TinyAssets principal, then invoke the same action and authorization boundary. Channel membership, bot installation, or Slack admin status never creates TinyAssets content, spending, or market authority.

Organization resource policy composes with request authority by intersection. An org can fund a shared model/provider/daemon only through an explicit delegation with universe, phase, provider/model, budget, expiry, revocation, and purpose constraints.

## HIPAA and regulated industries

HIPAA is the correct spelling. More importantly, self-hosting or BYOC does not automatically remove TinyAssets from HIPAA obligations. Applicability follows the parties, relationships, and actual ePHI data flow. If TinyAssets or its connector, telemetry, control plane, storage, provider, or subcontractor creates, receives, maintains, or transmits ePHI for a covered entity/business associate, legal and contractual analysis is required.

The platform is not currently regulated-ready. Highest gaps are:

1. no first-class organization/membership/group/delegation lifecycle;
2. no regulated data-plane and processor/subprocessor/BAA registry;
3. credential storage is not encrypted custody;
4. no complete tenant-scoped access/effect/authorization journal;
5. retention, legal hold, deterministic deletion, residency, and incident/breach workflows are design intent rather than as-built requirements;
6. permissionless Internet hosts are not classified by contractual, privacy, region, retention, or evidence eligibility.

For ePHI, unknown/unreviewed market hosts are categorically ineligible. Provider and market policy must narrow routes by approved processors/subprocessors, contract/BAA state, geography, retention/no-training, encryption/key handling, incident obligations, and current evidence. Market listings and bids must never contain PHI.

Standards support should use versioned assurance packs inspired by OSCAL:

- source/effective version and applicability;
- selected controls and parameters;
- required evidence and tests;
- retention/residency/provider constraints;
- responsible actor;
- exceptions with owner and expiry;
- assessment freshness and coverage.

Packs may only narrow authority. A run binds an immutable pack/policy version and receipts record it. User-facing states should be `configured`, `evidence_current`, `assessment_pending`, or `exception_open`, never a blanket `certified` or `HIPAA compliant` claim. This is architecture research, not legal advice; counsel and a real covered-entity/business-associate data-flow review remain external gates.

## Current OpenSpec coverage and ranked gaps

The 2026-07-22 baseline has 24 canonical as-built capabilities and nine active changes. Recent reconciliation PRs corrected older audit counts, so this ranking uses current `origin/main`, not historical headline numbers.

| Rank | Gap | Judgment / next shape |
|---|---|---|
| P0 | First-contact request authority | Current change `define-first-contact-authority-handshake`; spec-only and Claude-review-blocked. |
| P0 | Moderation, abuse response, appeals, public rate limits | No canonical capability; create `specify-moderation-and-abuse-response` from existing moderation docs without colliding with active connector changes. |
| P0 | Organization ownership, membership, delegation | Create `define-organization-membership-and-delegated-authority`; WorkOS/SCIM/Slack are identity/control adapters, not separate authority engines. |
| P0 | Regulated data plane and assurance packs | After org identity, create `define-regulated-data-plane-and-assurance-packs`; include processor eligibility, audit, retention/hold/deletion, residency, incidents, and evidence packs. |
| P1 | Paid-market transaction transport | Replace stale/conflicting broad PR #1542 with narrow `paid-market-transaction-transport`; authenticated idempotent transaction/CAS/drain/migration only. |
| P1 | Node discovery, remix, convergence, live collaboration | Coverage is fragmented and collides with universe visibility/brain changes and PR #1467; reconcile those dependencies first. |
| P0 | Multi-tenant durable control plane and load admission | Current file/SQLite/single-process shapes are not scale proof; specify stateless replicas, durable queues, tenant fairness/backpressure, distributed quotas, and executable load gates. |
| P0 | Replay-safe connector effects and connection grants | Prerequisite to safe Zapier parity; user/org-owned encrypted connections, credential-blind adapters, mandatory idempotency, outbox/inbox, and ambiguous-result reconciliation. |
| P1 | Zapier-class automation breadth | Split connector catalog, event ingress/cursors, replay/error history, sandboxed code, and typed record/input surfaces; do not create one catch-all tool. |
| P1 | One-click packaged host installer | Canonical specs document the absence; create a separate installer change after shared control-plane blockers. |
| P2 | Physical fabrication market | Reuse market grammar but create typed fabrication capability, executor, inspection, logistics, safety, and dispute rules separately. |

The paid-market Wave 2 worktree/PR should not be continued wholesale: it conflicts with current main, is based on superseded forward specs, and has no completed implementation tasks. Its useful authenticated transaction/idempotency/CAS ideas should be selectively ported into a fresh narrow change. The old “best live route and fee” notes are not yet canonical truth.

## Adopt, adapt, avoid, defer, watch

### Adopt

- Server-constructed, request/audience/phase/budget-bound authority.
- Requester mandate -> exact agreement/lease -> execution authority.
- Hard-constraint filtering before cheapest-adequate ranking.
- Explicit provider capability/privacy/locality/evidence attributes.
- Immutable design/model/workflow artifacts with lineage and evaluator gates.
- Append-only correlated receipts, integer accounting, idempotency, and fences.
- Organization-owned universes plus external identity/control adapters.
- Versioned assurance packs that narrow policy and emit assessment evidence.

### Adapt

- OpenRouter routing controls into buyer mandates and phase policy, without central-account fallback.
- Akash/Golem demand/offer/agreement/lease patterns into TinyAssets' existing signed distributed-execution contracts.
- OAuth subject/actor/audience/replay concepts into internal authority values; do not force every local grant through token exchange.
- OSCAL concepts into community-remixable standards packs and executable SOP branches.
- DEX transparency/conservation ideas into price indexes and settlement receipts, not AMM execution.

### Avoid

- Treating a quote, provider config, universe ACL, reachable credential, or receipt as positive authority.
- Raw secrets in chat/tool arguments or base64 as credential protection.
- Copying host environment/home/profile state and trying to scrub a denylist.
- Model/provider fallback outside the request mandate to improve success rate.
- Public PHI in market demand, bids, logs, traces, or training datasets.
- Compliance badges unsupported by scoped, current evidence and external assessment.
- A fungible-token AMM for heterogeneous compute capacity.

### Defer

- Blockchain selection, secondary derivatives, and cash-settled compute instruments.
- Private-source work on untrusted market hosts until explicit confidentiality tiers and owner-controlled delivery are proven.
- Physical fabrication activation until domain safety, inspection, shipping, and dispute rules exist.

### Watch

- DPoP or mTLS as the default sender constraint for high-risk market capabilities.
- Verifiable provider attestations and independent capability benchmarking.
- Portable model/runtime packaging and accelerator interoperability.
- New HHS Security Rule changes; as of this audit, HHS still labels the 2024 update proposed and the current rule remains in effect.

## Cross-provider review gate

Research-derived implementation, push of implementation, live rollout, and acceptance testing remain blocked until Claude independently:

1. re-checks the primary sources;
2. inspects the current TinyAssets provider, auth, vault, market, and first-contact paths;
3. reviews `define-first-contact-authority-handshake`;
4. leaves a durable verdict of `approve`, `adapt`, `defer`, or `reject`;
5. re-reviews any required adaptations.

Codex subagent reviews in this lane improve quality but do not satisfy the opposite-provider gate.

## Pickup packets

### A. First-contact authority (active)

- **Source:** this audit and `openspec/changes/define-first-contact-authority-handshake/`.
- **Initial provider / reviewer:** Codex / Claude.
- **Branch/worktree:** `codex/first-contact-authority-handshake`; `../wf-first-contact-authority-handshake`.
- **Write set:** current OpenSpec change, this audit, `STATUS.md` only.
- **Dependencies:** draft PR #1606 live prerequisite; R2-1b receipt implementation; opposite-provider review.
- **First build slice after approval:** fake-only immutable authority/completeness/delegation tests and types; no real provider or market.
- **Publish:** draft PR, explicitly review-blocked.
- **Exit:** strict validation + accepted Claude review; runtime remains separate.

### B. Organization membership and delegated authority

- **Proposed branch/worktree:** `codex/organization-delegated-authority`; `../wf-organization-delegated-authority`.
- **Next action:** primary-source research review, then OpenSpec proposal only.
- **Write boundary:** `openspec/changes/define-organization-membership-and-delegated-authority/` plus a dedicated review artifact.
- **Applies when touching:** organizations, shared universes, WorkOS, SCIM, Slack/Teams adapters, service accounts, auditor access, resource spending.
- **Dependencies:** identity/access-control current truth; first-contact delegation terms; opposite-provider review.

### C. Regulated data plane and assurance packs

- **Proposed branch/worktree:** `codex/regulated-data-assurance-packs`; `../wf-regulated-data-assurance-packs`.
- **Next action:** OpenSpec proposal only after packet B establishes tenant/principal/delegation ownership.
- **Write boundary:** `openspec/changes/define-regulated-data-plane-and-assurance-packs/` plus a dedicated HIPAA/NIST review artifact.
- **Applies when touching:** PHI/PII, provider markets, training data, retention/deletion, residency, incidents, audit/evidence, compliance wording.
- **External gates:** counsel, real customer/data-flow review, security assessment; no certification claim.

### D. Paid-market transaction transport

- **Proposed branch/worktree:** `codex/paid-market-transaction-transport`; `../wf-paid-market-transaction-transport`.
- **Next action:** replace the stale broad Wave 2 proposal with a narrow current-main OpenSpec change.
- **Write boundary:** `openspec/changes/paid-market-transaction-transport/` only at proposal stage.
- **Dependencies:** current paid-market canonical spec, identity, distributed-execution contracts, and opposite-provider review.

### E. Moderation and abuse response

- **Proposed branch/worktree:** `codex/specify-moderation-abuse`; `../wf-specify-moderation-abuse`.
- **Next action:** proposal/design/delta/tasks from `docs/specs/2026-04-18-moderation-mvp.md` and `docs/moderation_rubric.md`.
- **Write boundary:** `openspec/changes/specify-moderation-and-abuse-response/` only; avoid active live-MCP files.
- **Reason:** it is the highest uncovered Forever Rule uptime surface after the active request-authority P0.

### F. Connector catalog and replay-safe effects

- **Proposed branch/worktree:** `codex/connector-catalog-effects`; `../wf-connector-catalog-effects`.
- **Next action:** split into `connector-catalog-and-connection-grants`, `durable-event-ingress-and-trigger-cursors`, and `replay-safe-external-effect-transport` proposals with explicit dependencies rather than one omnibus change.
- **Write boundary:** new change directories only during proposal; do not touch current connector/effect runtime until review and file claims exist.
- **Applies when touching:** Zapier parity, OpenAPI/MCP adapters, OAuth connections, webhooks, polling, schedules, retries, external mutations, forms, tables, and agents.
- **Dependencies:** request authority, encrypted credential custody, organization delegation where shared, distributed execution for remote adapters, opposite-provider review.

### G. Multi-tenant control-plane scaling

- **Proposed branch/worktree:** `codex/multi-tenant-load-admission`; `../wf-multi-tenant-load-admission`.
- **Next action:** create `multi-tenant-control-plane-and-load-admission` as a spec and executable load-plan lane, not a premature database rewrite.
- **Write boundary:** new OpenSpec change plus a scoped §14 load harness/plan after review.
- **Applies when touching:** public MCP/API, state stores, queues, worker claims, realtime, connector limits, user growth, organization isolation, and concurrent users.
- **Exit proof:** 1,000 fanout, 500-daemon storm, connector 429/backoff, tenant fairness/noisy-neighbor, recovery, and 10,000 idle sessions without maintainer compute or provider quota.

## Open questions and verification gaps

- The exact same-origin web route and custody backend for credential enrollment need their own auth/security/UI review.
- The current paid-market transport that mints an `ExecutionAgreement` is not yet built.
- Organization ownership and delegation are not yet canonical capabilities.
- The current vault is not suitable for regulated secrets or ePHI-adjacent key custody.
- No complete post-fix real-user evidence can exist until request authority is implemented, deployed, and exercised without maintainer-resource use.
- This audit does not authorize `PLAN.md` changes; accepted architecture changes still require host approval.
