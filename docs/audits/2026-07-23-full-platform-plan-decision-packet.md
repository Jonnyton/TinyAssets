# Full-Platform PLAN Decision Packet

**Date:** 2026-07-23

**Initial provider:** Codex

**Required opposite-provider reviewer:** Claude, after provider capacity resets

**Status:** HOST DIRECTION RECEIVED 2026-07-24 — opposite-provider review
required before PLAN/OpenSpec/build/push; this packet is not yet build authority

**Scope:** the four contradictions blocking three full-platform OpenSpec target groups
**Build effect:** none; this lane does not edit PLAN, OpenSpec, runtime code, deployment, or live state

## Host direction received 2026-07-24

The host approved the bundle's architectural direction with this refinement:

- policy is situational rather than one global mode;
- applicability can be scoped to a universe, branch, artifact, dataset,
  taxonomy, location, workflow step, provider route, organization, or other
  explicit subject;
- HIPAA, privacy, residency, retention, and similar obligations apply only
  when the declared actors, data, activity, location, contract, or purpose
  makes them relevant;
- users and authorized organizations supply intent and applicability facts,
  assisted by their chatbot;
- the chatbot receives the best current applicable practices, citations,
  effective dates, unresolved questions, and required controls while it works,
  so it can guide the user in context instead of relying on a single static
  settings page;
- most higher-level behavior remains buildable, remixable, combinable, and
  copyable from primitives.

This does not authorize the chatbot to invent legal applicability,
certification, contractual eligibility, or user consent. It may propose a
classification or explain likely implications, but an authorized actor owns
the applicability facts and high-impact decisions. The platform owns the
non-optional enforcement substrate and must fail closed when a required
control or eligibility fact is unresolved.

### Commons page-write boundary delegated to Codex

The host delegated the PR #1583 commons-write boundary decision. The selected
target keeps one `write_page` primitive with an explicit destination:

- `scope="commons"` is explicit public-publication intent and uses the public
  draft/CAS path;
- `scope="universe"` requires a universe target and routes typed page intent
  through the universe intelligence's governed writer;
- omitted or conflicting scope is non-mutating and returns structured
  migration guidance;
- all canonical, directory, and temporarily callable legacy shells use the
  same destination and authority resolver;
- typed public coordination filings may remain inherently commons-scoped when
  their contract already makes publication intent explicit.

The destination boundary is structural; content classification and
situation-specific privacy policy remain composable. The chatbot may help the
user choose and understand the destination, but it never infers publication
consent from authentication, a home universe, or an omitted field.

## Decision request

Approve, adapt, or reject this four-part bundle:

1. Use typed canonical authorities rather than one universal store:
   Postgres/Supabase first for transactional platform control state and live
   catalog coordination; the proposed OKF bundle for universe-brain knowledge;
   Git/GitHub for source code plus versioned public export and contribution;
   object/local/self-hosted stores for placement-selected payloads.
2. Support four explicit placement modes — public commons,
   permissioned-cloud-private, local-private, and self-hosted — with new
   universes and unclassified content private until an authorized actor
   publishes selected material.
3. Keep the canonical public MCP surface at the existing seven advertised
   tools, backed by the five abstract permission handles. New catalog,
   collaboration, organization, connector, compliance, and market behavior
   composes behind those handles unless an independently reviewed
   irreducibility proof finds a missing primitive.
4. Make the platform responsible for enforceable security and evidence
   invariants; make communities and organizations responsible for evolvable,
   context-scoped industry rulebooks, SOPs, and policy packs. Resolve the
   applicable guidance into the user's chatbot context at the scope where it
   applies. A rule pack or chatbot judgment never creates a certification or
   legal-compliance claim.

These choices are designed as one bundle. Selecting only one or two leaves
contradictions:

- browser-only private organizations require an authorized cloud-private
  placement, so “the platform never stores private content” cannot remain
  absolute;
- cloud-private placement is unsafe without platform-owned tenant isolation,
  authorization, audit, deletion, retention, and provider-eligibility
  enforcement;
- live multi-user control state cannot use Git commits as the authoritative
  transaction path, while portable universe knowledge should not become
  trapped in a hosted database;
- Zapier-class breadth cannot become one public MCP tool per application
  action without violating the minimal-surface rule.

## Why a decision is required now

The OpenSpec full-coverage audit identifies three target groups that cannot be
specified without these choices:

1. collaborative catalog and control plane;
2. realtime collaboration, artifact CRUD, discovery, remix, convergence,
   presence, export, and the private/host boundary;
3. portability, deletion, succession, and feedback.

The current repository simultaneously says:

- the target backend is Supabase/Postgres and the full-platform architecture is
  integrated (`PLAN.md:490-541`);
- Postgres-canonical versus GitHub-canonical remains unresolved
  (`PLAN.md:573-581`);
- private content never exists on the platform (`PLAN.md:55-63`);
- the integrated architecture stores owner-private records and private object
  references (`docs/design-notes/2026-04-18-full-platform-architecture.md:1217-1354`);
- the newer organization/trust design explicitly offers
  permissioned-cloud-private, local-private, and self-hosted modes and says it
  supersedes commons-first absolutism
  (`docs/specs/2026-06-10-tiny-first-principles-spec.md:138-176`);
- the 2026-07-02 host direction says universes begin private and grow into
  granular multi-actor visibility
  (`docs/design-notes/2026-07-02-universe-visibility-and-access-model.md:15-75`);
- canonical vocabulary names five abstract permission handles
  (`PLAN.md:77-110`), while the shipped public connector correctly advertises
  seven concrete tools, adding `converse` and `get_status`
  (`openspec/specs/live-mcp-connector-surface/spec.md:38-88`).

OpenSpec must not choose between those statements implicitly.

## Non-negotiable invariants

All options were tested against these existing project commitments:

1. A browser-only user can create, edit, and collaborate on a universe with
   zero personal daemon hosts online; model or node execution requires
   requester BYOC, an authorized organization route, or an accepted market
   grant and otherwise returns `setup_required`.
2. A requester’s model or compute usage never consumes maintainer credentials
   or maintainer provider quota.
3. Public commons content remains exportable, remixable, forkable, and
   contributor-friendly.
4. Local-private and self-hosted users remain first-class, not legacy
   compatibility modes.
5. Tenant, organization, universe, actor, and delegated-agent authority is
   fail-closed at every read, write, route, effect, and receipt boundary.
6. Git clone-and-run stays viable for OSS contributors.
7. Public MCP surface area stays intentionally small.
8. Industry rules can evolve without a platform release.
9. Security and legal claims remain evidence-backed and narrowly worded.
10. Portability, deletion, legal hold, lineage, and commons preservation have
    explicit and testable conflict rules.
11. Every uptime-track feature includes production-shaped concurrency, load,
    failure, rendered-chatbot, and post-fix clean-use proof.

---

## Decision 1 — Canonical live state authority

### Options considered

| Option | Shape | Strength | Fatal problem |
|---|---|---|---|
| A. Typed canonical authorities; relational live control plane | Transactional relational DB owns identities, ACLs, durable catalog coordination, requests, quotes, receipts, collaboration-session membership, and edit-session leases; live presence, typing, and heartbeat remain ephemeral non-authoritative Realtime/TTL state. Generic execution leases/fencing stay with `distributed-execution`. The OKF bundle and its Git-backed snapshot own universe-brain durability after their active proposal is approved. Git owns source and receives separate public projections/contributions. | Fits multi-user transactions and portable knowledge without declaring one store authoritative for unrelated data classes. | Requires explicit durability boundaries, commit protocols, and projection reconciliation per data class. |
| B. Git/GitHub canonical | Every authoritative change is a commit/PR or bot-authored commit. | Native provenance, forks, public inspection, and OSS ergonomics. | GitHub documents operational limits on repository reads and pushes; commit-based writes do not provide tenant-isolated realtime transactions, presence, hot-row coordination, or browser-only private collaboration. |
| C. Dual authority | Postgres and Git both accept authoritative writes and reconcile later. | Appears to preserve both models. | Split-brain authority, irreconcilable deletion/ACL races, ambiguous receipts, and no deterministic answer when histories diverge. |

### Recommendation

Choose **Option A**, with each data class assigned exactly one semantic owner
and durability boundary, expressed through provider-neutral contracts rather
than a permanent Supabase dependency.

Authority and placement are orthogonal. Authority names the model/mutation
owner and durability boundary; placement names where that authority is hosted.
An OKF bundle or versioned artifact authority may be public-cloud,
tenant-private, local, or self-hosted. An object store is a persistence medium,
never by itself the semantic authority.

| Data class | Semantic owner and durability boundary | Placement and projections |
|---|---|---|
| Identity, organization, membership, ACL, delegation | transactional identity/access-control records; constraints and committed authority version are durable | relational cloud or self-host control plane; SCIM/IdP/Slack are authenticated command/projection sources, never silent authority |
| Catalog identity, comments, publication state, revision/current pointers, durable collaboration-session membership, and edit-session leases | transactional collaborative-catalog owner; immutable IDs, committed pointers, CAS/revision state, collaboration membership, and edit leases are durable; generic execution leases/fencing remain with `distributed-execution` and are reused where semantically applicable | relational control plane; CDN/search/Git catalog views are rebuildable projections |
| Live presence, typing, and heartbeat | ephemeral collaboration state; explicitly non-authoritative | Realtime Broadcast/Presence or TTL state, never durable catalog rows |
| Nodes, Edges, State schemas, and BranchDefinitions | existing `graph-execution-substrate` owns graph-definition structure, executable serialization, and run binding; active `node-authoring-and-autoresearch` owns draft/edit/test/version/publication lifecycle; each published graph version is immutable and durable only when body and digest are committed | body may be inline or content-addressed; catalog owns only projections, discovery, comments, presence, and current-pointer CAS |
| Goals, bindings, and convergence state | existing `shared-goals-and-convergence` owner; versioned Goal and binding transition plus authoritative receipt | relational control state and portable artifact projection according to that owner |
| Pages, universe-brain knowledge, and rule-pack content | `wiki-commons` owns page lifecycle/publication; the OKF bundle owns brain-content durability after `brain-okf-canonical-store` approval; under that proposal its Git-backed bundle snapshot is the durable store | relational outbox/index and SQLite/FTS/vector stores are operational projections; public catalog Git publication is a separate projection |
| Large payload blobs | the referencing immutable artifact version owns identity, digest, authority, lifecycle, and deletion state | placement-selected object, local, or self-host store; the medium is not semantic authority |
| Runs and Triggers | runtime/graph owner plus durable journal/checkpoint/terminal receipt | execution may be local, organization-provided, or market-provided; bounded control-plane status is a projection |
| Market request, quote, reservation, and settlement | owning transactional market ledger and signed authority records | relational market store; public aggregate and tenant-private audit projections |
| External effect and handoff evidence | destination/system of record owns the external fact; TinyAssets owns immutable attempt, acceptance, uncertain, and later-outcome evidence bound to a receipt | evidence journal plus audit/outcome projections; a TinyAssets receipt never fabricates destination truth |
| Source code | Git/GitHub commit and review history | packages, images, and deployments are derived artifacts |

The active `brain-okf-canonical-store` design already rejects naive dual writes:
its operational layer handles concurrency, but a brain entry is durable only
after the explicit outbox/commit protocol places it in the OKF bundle, whose
Git-backed snapshot is the proposed durable store. This packet preserves that
owner instead of relabeling Postgres as canonical for brain knowledge. If that
active contract changes, it must return for host and opposite-provider review.

The first implementation may use Supabase because its official documentation
supports browser access guarded by Postgres Row Level Security, private
Realtime Broadcast/Presence authorization, and RLS-controlled object storage:

- <https://supabase.com/docs/guides/database/postgres/row-level-security>
- <https://supabase.com/docs/guides/realtime/authorization>
- <https://supabase.com/docs/guides/storage/security/access-control>

PLAN should say “relational control-plane contract (Postgres/Supabase first),”
not “all platform state permanently depends on hosted Supabase.”

### Why Git remains essential

Git is not demoted in importance; it is assigned the authority it handles best:

- canonical source code and review history;
- public, portable, diffable commons snapshots;
- offline clone, remix, and contribution;
- provenance export and disaster-recovery material;
- self-host bootstrap.

It is not used as a substitute for a high-contention application database.
GitHub’s own repository guidance recommends bounded read and push rates and
warns of degraded repository health when activity exceeds operational
guidelines:
<https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits>.

### Required consequences

- Every projection has a declared direction, cursor/version, idempotency key,
  reconciliation rule, lag signal, and failure state.
- Every capability declares what “durable” means and may not acknowledge a
  write from a rebuildable index or incomplete projection.
- A relational current pointer may become visible only after the referenced
  artifact authority reports durable, or it remains explicitly pending. A
  crash may never expose a pointer to missing or uncommitted content. The same
  idempotency key, artifact version, digest, and receipt bind the content
  commit and pointer publication.
- Git import is an authenticated proposal into the control plane, not an
  unreviewed overwrite.
- Export is never the only copy of tenant-private state.
- Search, vector, cache, and Git projections are rebuildable and never grant
  positive authority.
- There is exactly one authoritative receipt per authority-owned transition,
  correlated by one saga/operation ID.
- All hot writes use database concurrency controls appropriate to their
  invariant: optimistic version/CAS, unique constraints, transaction locks, or
  append-only allocation.
- Serializable/CAS retries restart the whole transaction with bounded backoff.
  Claims and leases carry fencing tokens so an expired owner cannot commit,
  and every retry reuses the operation idempotency key.
- Object/blob creation verifies durable object existence and digest before the
  relational version/current pointer can commit. Publish, placement move,
  deletion, legal hold, and cross-authority export are resumable sagas with
  one operation ID, per-authority prepare/commit/tombstone receipts, retries,
  reconciliation, and no false success. The control plane owns saga status;
  each authority owns its mutation receipt.
- Capability-defined artifact authorities come from a closed, versioned
  authority registry. A capability cannot invent an unreviewed durability
  contract.

---

## Decision 2 — Public and private data placement

### Options considered

| Option | Benefit | Failure |
|---|---|---|
| A. Commons-only platform; all private data host-local | Platform cannot leak content it never receives. | Browser-only private work, shared company brains, zero-host collaboration, and organization-managed cloud use become impossible or unavailable whenever a host is offline. |
| B. Cloud-only platform | Simple user experience and collaboration. | Breaks self-host/local-private autonomy, creates unnecessary processor exposure, and violates BYOC/no-lock-in direction. |
| C. Explicit hybrid placement modes | Each universe and artifact selects a verifiable placement compatible with its users and contracts. | More policy and test surface, but it is the only option satisfying both zero-host browser use and local/self-host autonomy. |

### Recommendation

Choose **Option C**.

This is a target-architecture choice, not a claim that managed private storage
or regulated cloud processing exists today. Until the cloud-private controls,
contracts, provider eligibility, isolation tests, and live acceptance gates
below are implemented and proven, the product must describe private execution
as local/self-hosted or unavailable—not silently route it through a public
platform or maintainer account.

#### Placement modes

| Mode | Content location | Control-plane knowledge | Availability | Intended use |
|---|---|---|---|---|
| `public_commons` | public platform store and public export | full public metadata and content | host-independent | reusable designs, public nodes, branches, rule packs, research, device/CNC/3D-print designs |
| `permissioned_cloud_private` | tenant-scoped encrypted cloud data/object plane | minimum necessary tenant metadata, ACLs, policy, receipts, and content references | host-independent | teams, shared company brains, browser-only private users, eligible regulated workloads |
| `local_private` | founder/organization-selected host | opaque existence/binding/status only when needed | host-dependent | personal or organization workloads that must remain local |
| `self_hosted` | organization-operated control and data plane | public service sees only explicitly federated/exported facts | organization-dependent | sovereignty, custom controls, regulated or air-gapped deployments |

Hybrid universes may combine modes. The minimum placement unit is an immutable
artifact version. Field-level separation is represented by explicit referenced
sub-artifacts; one mutable record never spans authorities. Each version has
one payload authority and one relational identity/current pointer. A reference
to a payload is not a second authoritative copy.

#### Default

New universes and unclassified content should be **private until an authorized
actor publishes selected material**. The chatbot should proactively identify
generic, reusable concepts and offer to publish them, but silence is not
publication consent.

This adapts the older public-biased concept model:

- public concepts remain the growth engine of the commons;
- user-specific examples, prompts, datasets, files, CAD inputs, employee
  records, customer data, credentials, and model-training data begin private;
- publishing is an explicit, reviewable transition with a diff, actor,
  authority, and receipt;
- public-to-private cannot erase already distributed public copies and must
  state that limitation before publication.

This default is consistent with the EDPB’s current guidance that privacy by
design and by default is a continuous duty, and with the European Commission’s
summary that defaults should minimize data, retention, and access:

- <https://www.edpb.europa.eu/documents/guideline/guidelines-42019-on-article-25-data-protection-by-design-and-by-default_en>
- <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en>

#### Context-scoped applicability

Placement and policy are evaluated for the smallest explicit scope that can
carry one coherent authority. A universe can therefore contain a public
reusable branch, a private dataset, a location-restricted taxonomy, and a
regulated workflow without forcing all four into one global mode.

Applicability is derived from versioned facts such as actor role, data
classification, processing purpose, jurisdiction/location, contract,
organization policy, provider route, and artifact lineage. Policies declare
their scope, authority, precedence, effective dates, citations, required
controls, evidence requests, and unresolved questions. More specific policy
does not silently weaken an applicable higher-authority floor.

Before a chatbot plans, edits, routes, publishes, trains, or executes within a
scope, it receives the resolved policy and best-practice context relevant to
that action. The user can inspect why each item applies, its source and
freshness, which facts were supplied or inferred, and what decision or evidence
is missing. The chatbot may recommend or ask, but publication, legal
applicability, consent, and other high-impact authority remain explicit
authorized decisions.

### Cloud-private does not mean “we cannot see it, so law does not apply”

HHS says a cloud provider that creates, receives, maintains, or transmits ePHI
is a HIPAA business associate even when it holds only encrypted data and lacks
the encryption key. A regulated TinyAssets cloud offering therefore needs
contractual and operational eligibility, not an encryption marketing claim:

- <https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html>
- <https://www.hhs.gov/hipaa/for-professionals/covered-entities/sample-business-associate-agreement-provisions/index.html>

The paid-market router must fail closed when a workload requires a BAA, DPA,
region, retention, training exclusion, subprocessor restriction, isolation
class, or deletion obligation and no independently verified route satisfies
it. A seller-applied “HIPAA” label is not authority.

This is architecture and product research, not legal advice. HIPAA/GDPR roles
and obligations depend on the actual actors, data, purposes, contracts,
jurisdictions, and data flows. The later product must record those facts and
route unresolved applicability to qualified counsel or an authorized
organization decision; it must not infer legal status from a domain label.

### Required platform controls for cloud-private

The platform substrate must provide or verify:

- tenant and universe identity on every row, object, cache key, queue item,
  quote, grant, receipt, backup, log, and deletion job;
- resource-level owner/editor/commenter/viewer/auditor/delegated-agent
  authorization with revocation invalidating cached positive authority;
- encrypted transport and storage, managed keys, rotation, revocation, and
  crypto-shredding where the contract uses it;
- minimum-necessary content flow and payload-free operational telemetry;
- audit records for access, effects, policy changes, exports, deletions,
  market routes, model/provider versions, and administrator actions;
- declared retention, deletion, legal-hold, export, residency, training,
  incident, and subprocessor rules;
- authorized deletion propagation across canonical data and rebuildable
  projections, subject to documented legal holds and statutory exceptions,
  with content-minimized tombstones only where an invariant requires them;
- typed access, export, and portability workflows producing open
  machine-readable formats for the legally applicable scope;
- availability, backup, restore, incident, and breach-response evidence;
- per-provider eligibility facts and contract references;
- production-shaped tenant-isolation and concurrency proof.
- fail-closed RLS on every exposed tenant table, with explicit `USING` and
  `WITH CHECK`, indexed policy columns, non-owner application roles,
  `FORCE ROW LEVEL SECURITY` where appropriate, `security_invoker` views (or
  revoked/unexposed views), and no client-visible service/BYPASSRLS
  credential; whole-table operations and referential-constraint leakage
  receive separate privilege/error tests;
- private Realtime with public access disabled and `private:true` channels,
  sharded per universe/capability; ephemeral presence/typing uses
  Broadcast/Presence rather than durable rows;
- a declared maximum Realtime revocation window, short JWT
  lifetime/refresh-reconnect behavior, and transactional reauthorization for
  every sensitive read, mutation, claim, and effect because channel
  authorization is cached for a connection.

Audit records are themselves protected data when they contain principals,
resource names, IP addresses, private route facts, payload fragments, PHI, or
personal data. The platform must minimize their fields, exclude payloads,
tenant-scope access, define retention/hold/deletion behavior, and audit access
to the audit system.

HHS guidance makes risk analysis foundational and expects safeguards across
the confidentiality, integrity, and availability of all ePHI:
<https://www.hhs.gov/hipaa/for-professionals/security/guidance/guidance-risk-analysis/index.html>.
HHS’s minimum-necessary guidance requires reasonable limitation of access and
disclosure for the intended purpose:
<https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html>.
Current binding technical and administrative safeguard text should be grounded
in the current eCFR, not in a proposed rule:

- <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.306>
- <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.308>
- <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.312>

### Organization administration

TinyAssets should own an organization model independent of any chat vendor:

- organization, workspace/universe, group, user, service principal, agent, and
  invitation identities;
- membership lifecycle;
- owner/admin/billing/admin-security/auditor/member/guest and resource-level
  relations;
- delegated agent authority with actor, delegator, scope, purpose, expiry, and
  revocation;
- SSO/IdP binding and SCIM-compatible provisioning;
- immutable admin/effect receipts;
- emergency and break-glass controls with review.

SCIM 2.0 standardizes HTTP/JSON provisioning for Users and Groups and defines
create, read, replace, delete, and capability discovery. PATCH, filtering,
bulk, versioning/ETags, and multitenancy have explicit optionality: bulk and
multitenancy are optional, RFC 7644 defines no multitenancy scheme, and
conditional `If-Match` applies only when the provider supports resource
versioning. `/ServiceProviderConfig`, `/Schemas`, and `/ResourceTypes` must
drive interoperability. SCIM is provisioning, not SSO, and defines no
SCIM-specific authentication, authorization, or role model. RFC 7643 says
Group membership does not itself grant authorization; TinyAssets must map it
through tenant-owned, audited role bindings:

- <https://www.rfc-editor.org/rfc/rfc7643.html>
- <https://www.rfc-editor.org/rfc/rfc7644.html>

Slack may be a user-facing command and notification surface, but it must not
become TinyAssets’ hidden identity database. Slack is nonnormative product
evidence for useful enterprise-admin patterns: organization-level
installation and credentials, scoped/delegated authority with a privilege
ceiling, read-only organization audit events, organization-wide rate limits,
and per-resource serialization for SCIM writes. TinyAssets remains the
authority for its own principals, roles, policy, and receipts:

- <https://docs.slack.dev/admins/scim-api/>
- <https://docs.slack.dev/reference/scim-api/>
- <https://docs.slack.dev/admins/audit-logs-api/>
- <https://slack.com/help/articles/1500004132581-Assign-members-to-system-roles>

A Slack command that changes TinyAssets organization state must resolve the
Slack actor to a TinyAssets principal, authorize the exact action, require any
necessary confirmation, execute through the same canonical mutation path, and
return the same receipt as web/chat/MCP/SCIM callers.

### Authorization model implication

Flat user/universe ACLs are insufficient for nested organizations, shared
universes, groups, resource inheritance, guests, and delegated agents.
TinyAssets should specify relationship-based authorization semantics without
requiring a specific vendor. Google’s Zanzibar paper is primary evidence that
a uniform relation model can provide consistent authorization across many
services and resource types:
<https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/>.

The target contract should model relationships and consistency requirements;
OpenFGA or another implementation can be evaluated later. Authorization data
must remain part of the canonical control-plane authority and must not be
derived from untrusted content or stale chat state.

The initial implementation should keep simple organization and resource ACLs
in the relational authority. A separate ReBAC service is justified only when
inherited relationships such as user → group → organization → universe →
artifact or delegated market agents exceed the safe expressiveness of those
tables. If introduced, it must not become a second resource-invariant
authority; model versions and consistency level must be bound to sensitive
commands and checked against revocation races.

Relationship rows and their monotonic `authz_version` remain canonical in the
relational control plane. A ReBAC service, if introduced, is populated from
the transactional outbox and returns its immutable model ID plus projection
watermark on every check. A positive decision used for a private read,
mutation, delegation, market claim, or effect is accepted only when its
watermark is at least the resource’s required `authz_version`; otherwise the
caller waits boundedly, checks the canonical authority, or fails closed. ACL
tuples are never dual-written. The resource transaction rechecks
authorization and version at commit.

---

## Decision 3 — Public tool and integration surface

### Current truth

There are two layers, and PLAN currently blurs them:

1. Five abstract permission handles:
   `read.graph`, `write.graph`, `run.graph`, `read.page`, and `write.page`.
2. Seven concrete public MCP tools:
   `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
   `converse`, and `get_status`.

`converse` is the user’s first-person relay into a universe. `get_status` is a
pure read affordance. Neither justifies multiplying application verbs into
public tools.

### Options considered

| Option | Benefit | Failure |
|---|---|---|
| A. One public tool per behavior/integration | Obvious direct calls. | Tool explosion, client metadata cost, confused model selection, duplicated auth/evidence semantics, and a Zapier-sized action catalog that cannot fit coherently in chatbot context. |
| B. Seven stable routers plus typed targets/actions and discoverable connector/action records | Small public surface with unbounded typed composition behind it. | Router schemas and discovery must be exceptionally clear and fail closed. |
| C. One universal `execute` tool | Minimal count. | Erases permission and risk boundaries; every call becomes a catch-all mutation surface. |

### Recommendation

Choose **Option B** and update PLAN to distinguish the abstract five-handle
authorization basis from the concrete seven-tool public connector.

Catalog, collaboration, organization administration, connectors, market
quotes, training requests, hardware fabrication, export, deletion, and
compliance evidence should appear as:

- typed graph/page targets and actions behind the existing handles;
- discoverable resource/action descriptors with JSON Schemas;
- community-authored branches and connector manifests;
- explicit risk, authority, cost, reversibility, confirmation, idempotency,
  and receipt metadata;
- durable task/run identities for asynchronous work.

Before the seven-tool surface is fixed as the target, the proposal must publish
a router/action-class matrix and one conservative static annotation set per
public tool. `write_graph` is limited to internal control-plane mutation;
every external connector effect executes through `run_graph` and the canonical
effect authority. If `run_graph` can update/delete external state, it must
advertise `openWorldHint=true` and `destructiveHint=true`; if `read_graph` can
query external connectors, it must advertise `openWorldHint=true`. Any current
exact-hint requirement contradicted by this routing is a spec delta, not an
implementation detail. If a router cannot carry one truthful conservative
annotation and one authorization/confirmation contract, split at that
trust/effect boundary through the irreducibility gate.

Preflight is side-effect-free and returns a short-lived, single-use
confirmation token bound to actor/delegator, universe, connector/action
version, destination, immutable input/payload hash, credential grant,
cost/cap, idempotency key, expiry, and current authorization version. Execute
reauthorizes and rejects changed, stale, replayed, or mismatched tokens.
Standing connector consent never substitutes for required per-effect
confirmation.

MCP task IDs and results are bound to principal, tenant, and universe.
`list`, `get`, `result`, and `delete` reauthorize every access. Results have
bounded `keepAlive`, cleanup, pagination, and rate limits, and task possession
never grants effect authority.

The MCP specification already gives each tool an input schema, optional output
schema, annotations, and task support; tool annotations are untrusted unless
they come from a trusted server:
<https://modelcontextprotocol.io/specification/2025-11-25/server/tools>.
Its generic task design favors one uniform asynchronous mechanism rather than
tool-specific async protocols:
<https://modelcontextprotocol.io/seps/1686-tasks>.

### Zapier-equivalent capability without Zapier-equivalent tool sprawl

Zapier’s own integration model reduces application breadth to reusable
**triggers, actions, searches, and search-or-create** operations. Its official
guidance even permits one operation to cover multiple record models through a
typed model input:
<https://docs.zapier.com/integrations/quickstart/recommended-triggers-and-actions>.

TinyAssets can cover that capability space through its existing basis:

| Zapier concept | TinyAssets composition |
|---|---|
| Trigger | `Trigger` creates/resumes a `Run` |
| Action | effectful `Node` behind a declared connector action |
| Search | read node/connector action through `read.graph` |
| Search-or-create | deterministic branch with read, conditional edge, and idempotent effect node |
| Multi-step Zap | `BranchDefinition` over Nodes, Edges, State, Scope, Run, and Trigger |
| App integration | versioned `ConnectorDefinition` plus connection/grant/subscription/invocation/receipt records |
| Zap history | run/effect receipts and journal |
| Human approval | gate/confirmation node with delegated actor authority |

The older connector design already recommends one `ConnectorProtocol`, one
uniform invocation entry, shared OAuth, consent, audit, errors, idempotency,
and community-contributed plugins rather than connector-specific platform
architecture
(`docs/specs/2026-04-19-connectors-two-way-tool-integration.md:21-49,
222-468`). Its standalone RPC names should be translated into the canonical
seven-tool surface rather than revived as new public tools.

Connector breadth composes from a versioned `ConnectorDefinition` (auth,
trigger/search/action schemas, scopes, risk/cap/rate-limit/version metadata),
user-owned `Connection` credential reference, revocable per-universe
`ConnectionGrant`, `TriggerSubscription` (webhook or poll cursor),
`ActionInvocation` idempotency key, and terminal/unknown `EffectReceipt`.
Zapier is one adapter over these primitives, not a platform primitive and not
one MCP tool per action.

Webhook delivery is signature/timestamp/replay checked, durably journaled
before acknowledgement, deduplicated by source delivery identity, and resumed
with bounded retry/backoff. Polling records a cursor and stable item identity.
Subscribe/unsubscribe/expiry, multiple subscriptions, ordering,
schema-version migration, rate limits, and partial failure are explicit.
Outbound retries and manual replay always reuse the TinyAssets idempotency key
and reconcile unknown outcomes before another effect.

### Irreducibility gate

A proposed eighth public MCP tool requires:

1. a capability impossible or unsafe to compose behind the existing seven;
2. evidence that adding a typed target/action cannot express it;
3. a distinct authorization or client-interaction boundary that cannot be
   represented by schemas, annotations, confirmation, or task state;
4. host approval;
5. opposite-provider review;
6. public-surface canary and rendered-client proof.

Convenience, discoverability, or fewer internal routing steps is not enough.

---

## Decision 4 — Platform versus community privacy/compliance ownership

### The false binary

The current text sometimes frames the choice as either:

- platform-authored HIPAA/SOC2 modes; or
- all privacy/compliance behavior left to chatbots and community templates.

Neither is safe.

Policy changes by jurisdiction, industry, organization, contract, and time, so
it should not be frozen into platform feature flags. But identity isolation,
authorization, audit completeness, encryption, deletion, retention, and
fail-closed provider routing cannot be optional community conventions.

### Recommendation: enforcement substrate plus evolvable policy

#### Platform-owned and versioned

- identity, organization, tenant, resource, and delegated-agent authority;
- isolation across rows, objects, queues, caches, search, logs, receipts,
  backups, models, and market routes;
- authentication, authorization, consent, confirmation, and revocation;
- cryptographic integrity, version stamps, immutable receipts, and replay;
- retention, deletion, hold, export, and residency enforcement mechanisms,
  including authorized policy-supplied floors and ceilings; crypto-shredding
  only where the storage/key model and governing contract make it an accepted
  deletion mechanism;
- provider/host/market eligibility facts and fail-closed routing;
- effect idempotency, reversibility classification, and uncertain-outcome
  handling;
- audit/event schemas and evidence-packet integrity;
- incident, recovery, and access-review evidence;
- production-shaped isolation/load/fault tests.

#### Community/organization-owned and evolvable

- regulation and standard summaries with citations and effective dates;
- organization policies and SOPs;
- HIPAA, SOC 2, financial, export-control, clinical, legal, or other rule
  packs;
- validation scenarios and evidence-request mappings;
- threat-model templates;
- auditor lenses, checklists, and workflow branches;
- mappings from external obligations to platform-enforced controls;
- domain-specific minimum-necessary judgments.

These materials are versioned, composable designs rather than one global
“HIPAA mode” or hard-coded industry branch. They can attach to the exact
universe, branch, artifact, dataset, taxonomy, location, workflow step,
provider route, or organization scope where their applicability facts hold.
The policy resolver supplies the applicable set, provenance, conflicts,
uncertainty, and missing evidence to the user's chatbot during the work.

#### External legal, assurance, and certification evidence

- legal advice and applicability determinations;
- executed BAA/DPA and subprocessor terms, with parties, covered service/data
  flow, jurisdiction, effective/expiry dates, and evidence;
- SOC 2 examination reports or other assurance/attestation evidence, with
  system, period/type, standard, and scope;
- certifications only under the named scheme, body, holder, scope, validity,
  and evidence;
- clinical validation, audit opinions, and regulator decisions or acceptance
  only where actually issued.

### Orthogonal evidence dimensions

Every compliance claim about a rule pack, run, artifact, provider, or
deployment reports the applicable typed evidence dimensions below. A
non-compliance-bearing object carries no compliance claim; absence is not
`unreviewed`. `policy_state` applies to rule packs and policies. Assessment,
certification, and contract-eligibility evidence attach only to the exact
scoped subject they assess:

- `policy_state`: `unreviewed | mapped | scenario_validated |
  organization_adopted`;
- `assessment_evidence`: assessor, standard, artifact/version, scope, and
  date/period;
- `certification_evidence`: scheme, accredited body, holder, certified
  processing/product scope, validity, and evidence;
- `contract_eligibility`: agreement type, parties, covered service/data flow,
  jurisdiction/region, effective/expiry dates, subprocessor conditions, and
  evidence.

No field implies another. A mapped, validated, or adopted pack is not a
certification. A certification does not by itself create contract eligibility
or legal compliance. A successful workflow run does not certify the
organization, and a provider’s self-applied compliance label does not make a
market route eligible.

HHS states that the Security Rule does not require certification and does not
recognize private certifications as relieving legal duties. The European
Commission describes GDPR certification as optional and tied to an accredited
mechanism. AICPA describes SOC 2 as an examination and report under attestation
standards, not a product certification:

- <https://www.hhs.gov/hipaa/for-professionals/faq/2003/are-we-required-to-certify-our-organizations-compliance-with-the-standards/index.html>
- <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations/how-can-i-demonstrate-my-organisation-compliant-gdpr_en>
- <https://www.aicpa-cima.com/cpe-learning/publication/soc-2-reporting-on-an-examination-of-controls-at-a-service-organization-relevant-to-security-availability-processing-integrity-confidentiality-or-privacy>

### Why this matches actual obligations

HHS cloud guidance and BAA guidance assign real responsibilities to a cloud
provider/business associate: safeguards, incident reporting, access and
accounting support, return/destruction, and equivalent subcontractor
restrictions. Those cannot be delegated to a wiki template.

GDPR creates obligations that require technical and organizational support,
but its rights are scoped and conditional. Article 17 erasure has statutory
exceptions. Article 20 portability concerns personal data provided by the
data subject where processing is automated and based on consent or contract,
requires a structured, commonly used, machine-readable format, and must not
adversely affect others. Generic deletion or full-workspace export therefore
supports a request workflow but is not itself proof of compliance:

- <https://commission.europa.eu/law/law-topic/data-protection/information-individuals_en>
- <https://commission.europa.eu/law/law-topic/data-protection/rules-business-and-organisations/dealing-citizens/can-individuals-ask-have-their-data-transferred-another-organisation_en>

When TinyAssets processes personal data on an organization’s behalf, Article
28 requires documented instructions, confidentiality, Article 32 security,
prior specific or general written authorization for subprocessors plus change
notice/objection, equivalent downstream duties, assistance with rights and
Articles 32–36, delete-or-return at the controller’s choice on termination,
audit/information support, and warning when an instruction infringes
applicable data-protection law. These are platform workflow and evidence
requirements; a rule pack cannot create the contract or appoint a
subprocessor:

- <https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng>
- <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations/controllerprocessor/can-someone-else-process-data-my-organisations-behalf_en>
- <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/dealing-requests-individuals_en>

The legally responsible actor supplies policy and legal decisions. Under GDPR
the controller determines purposes/means and lawful basis while a processor
follows documented instructions; HIPAA covered-entity/business-associate
allocations follow law and the BAA. Retention values remain constrained by
applicable law and contract. The platform must provide substrate capable of
enforcing and evidencing those authorized choices.

---

## Coherent target architecture after approval

```text
ChatGPT / Claude / Slack / web / mobile / CLI / SCIM / other MCP hosts
                              |
       seven-tool surface with per-handle/action authn and authz
                 (eligible public reads may be anonymous)
                              |
             typed targets/actions + task/run identities
                              |
     identity / organization / authorization / consent / receipts
                              |
        relational live control plane + typed artifact authorities
             |                  |                  |
       OKF/artifacts      cloud-private data   market/host registry
             |                  |                  |
       Git/YAML export      encrypted objects    BYOC/market grants
             |
       clone / remix / PR import

Local-private and self-hosted universes retain their own data authority and
federate only explicitly authorized metadata, public exports, requests, and
receipts.
```

The platform does not subsidize model or node execution from maintainer
credentials or quota. Ordinary control-plane processing remains
platform-owned. Model/node execution authority comes from:

- the requester’s explicit BYOC authority bundle;
- an organization-selected provider route;
- or an accepted market grant.

No browser, Slack, connector, rule pack, or organization membership may cause
maintainer provider credentials or quota to be used.

**Compute-authority boundary.** Zero personal daemon hosts does not imply free
model-provider quota. Control-plane reads, creation, editing, invitation,
publication, and collaboration must work without server-side model inference.
Before any operation that requires provider/model compute, the router resolves
exactly one current requester BYOC grant, organization-funded grant, or
accepted market grant, bound to actor/delegator, universe, provider/model
allowlist, budget, purpose, expiry, and revocation version. If none exists, the
operation fails before provider selection with typed
`compute_authority_required` evidence and setup/market choices. No fallback,
retry, queued resume, background worker, connector, or onboarding path may
inspect or consume maintainer credentials. Every provider receipt records the
non-secret `grant_id`, payer/credential class, provider/model actually used,
route decision, and budget effect.

## OpenSpec ownership unlocked by approval

After PLAN is updated and independently reviewed,
`complete-plan-gated-platform-targets` may coordinate the work, but the change
name owns no behavior. The OpenSpec proposal must begin with a
requirement-to-owner matrix. Every requirement has one semantic capability
owner; existing owners receive `MODIFIED` requirements, and a new capability
is created only for a genuinely unowned aggregate.

The active `build-forward-platform-capabilities` boundary-layer delta already
owns user-owned connections, per-universe grants, caps, replay-safe effects,
inboxes, credential-blind adapters, and OpenAPI/MCP-shaped commons adapters.
Subsequent connector changes must extend that owner rather than duplicate it.

| Requirement family | Intended semantic owner |
|---|---|
| principal authentication and actor binding | existing `identity-auth-and-access-control` |
| organization, group, membership, delegated-agent, and admin-lifecycle semantics not already owned | candidate new `organization-membership-and-delegation` |
| visibility, publication grants, private-by-birth, and per-actor access | active `universe-visibility`, extending identity/access where enforcement belongs |
| Goal/Branch convergence and binding semantics | existing `shared-goals-and-convergence` |
| page lifecycle and commons publication | existing `wiki-commons` |
| universe-brain durability and OKF projection | active `brain-okf-canonical-store` |
| live connector routing and wire behavior | existing `live-mcp-connector-surface`; it owns no domain behavior |
| graph-definition structure, executable serialization, and run binding | existing `graph-execution-substrate` |
| node/graph draft, edit, test, version, and publication lifecycle | active `complete-independent-full-platform-targets` delta `node-authoring-and-autoresearch` |
| catalog projections, comments, ephemeral presence, current-pointer CAS, collaboration-session membership/edit leases, and genuinely unowned discovery behavior | candidate new `collaborative-catalog-and-presence`, split further if the domain/invariants do not cohere; generic execution leases/fencing stay with `distributed-execution` |
| market lifecycle, quotes, reservation, settlement, and execution grants | existing `paid-market-economy` plus active transport/live-price owners |
| cross-owner access/export/portability/delete/hold orchestration | candidate new `data-portability-and-deletion`; every affected data owner receives its own conformance delta |
| succession | separate candidate capability unless proposal analysis proves a shared aggregate with an existing owner |
| feedback intake, triage, and closure | separate candidate capability unless proposal analysis proves a shared aggregate with an existing owner |

Export/import must be assigned once: the cross-owner portability orchestrator
owns user/account portability workflows, while each data owner owns how its
records participate; public catalog Git projection/import belongs to the
collaborative catalog owner. A coordinated change may contain many delta
capability folders, but it may not become a catch-all capability.

## Required acceptance evidence for later implementation

Approval of this packet is not implementation approval. Each subsequent
OpenSpec change must require at least:

- strict OpenSpec validation and collision/ownership checks;
- migration, rollback, projection-rebuild, and disaster-recovery proof;
- tenant/org/universe/actor/agent isolation across every storage and cache
  boundary;
- stale authorization and revocation races;
- concurrent same-resource writes and hot-resource load;
- public/private publication and non-publication tests;
- cross-placement export, restore, migration, and deletion;
- legal hold versus deletion conflict behavior;
- SCIM retry, ETag, duplicate, deprovision, and partial-failure behavior;
- Slack/web/chat/SCIM commands producing the same authorized receipt;
- connector OAuth, consent, revocation, idempotency, and uncertain effects;
- with maintainer credentials intentionally present, newborn, missing,
  revoked, exhausted, invalid-provider, retry, fallback, queue-resume, and
  partial-overlay paths prove from provider receipts and billing telemetry
  that none consumes maintainer quota;
- market compliance-eligibility failure closed;
- the canonical §14 scenarios: 1,000 subscribers on one hot universe with no
  missed events and broadcast p99 below 2 seconds; 500 capability-subscribed
  daemons competing through narrow claim RPCs during 1,000 requests per five
  minutes with dispatch p99 below 3 seconds and no loss/double claim; 200
  concurrent ranking refreshers without lock thrash; 1,000 Presence
  heartbeats per minute without churn; plus 100 mixed-role
  author/collaborator sessions across multiple tenants;
- an explicit 10× launch capacity model declaring baseline DAU/concurrency,
  operation mix, payload distribution, hot-key percentage, sustained
  duration, DB connection-pool limit, queue-age/backpressure thresholds,
  p95/p99 latency, allowed error rate, projection lag, and cost ceiling;
- simultaneous cross-tenant isolation under pooled connection reuse,
  serialization-retry storms, Realtime reconnect/revocation,
  lease-expiry/fencing, outbox backlog/replay, and destination
  retry/idempotency faults; the 1,000 sequential-session soak remains
  additional evidence, not cross-tenant bleed proof;
- outage, recovery, backpressure, queue-age, and storage-contention bounds;
- real Claude and ChatGPT rendered conversations through the live connector;
- post-fix clean real-user evidence or an explicit STATUS watch.

## User simulations to run before proposal approval

1. **Browser-only founder:** creates a private universe, never installs a host,
   invites one collaborator, publishes one generic node, and verifies private
   examples never enter discovery or Git export.
2. **Startup company brain:** an org owner provisions employees through SCIM,
   manages a shared universe from Slack, removes an employee, and proves that
   old Slack sessions and cached authority cannot read or execute.
3. **Regulated clinic:** selects cloud-private only when a BAA-eligible route is
   verified, exports an evidence packet, applies legal hold, and receives a
   fail-closed result when the only compute offer has a seller-authored HIPAA
   label.
4. **Local-sovereign user:** keeps all payloads local, publishes one reusable
   workflow concept, exports everything, moves to self-hosted, and never grants
   the public platform access to private payloads.
5. **Zapier migrant:** connects Gmail, Slack, a webhook, and a database;
   composes triggers/search/actions/approvals as a branch without any new
   public MCP tool; sees durable effect receipts and no duplicate send.
6. **Commons contributor:** clones the public catalog export, edits YAML,
   submits a PR, and sees an authenticated proposal imported without
   overwriting a newer live version.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Relational control plane becomes a vendor lock | Provider-neutral contract, Postgres-compatible schema, complete export, self-host probes, rebuildable projections |
| Cloud-private expands legal exposure | Explicit placement consent, contract/region/provider eligibility, data minimization, narrow claims, no regulated route without verified prerequisites |
| Private-by-default starves the commons | Proactive publish suggestions, simple per-piece review, public templates, remix incentives, explicit publication receipts |
| Relationship authorization becomes over-engineered | Specify semantics and invariants first; implement the smallest model that passes concrete org/share/delegation scenarios |
| Seven routers become catch-all unsafe tools | Closed schemas, typed target/action registries, per-action authority/cost/risk metadata, deny unknown fields, canary drift checks |
| Community rule packs are mistaken for certification | Machine-enforced claim levels and visible scope/issuer/version/validity/evidence |
| Git export silently diverges | Cursor/version receipts, lag alarms, deterministic rebuild, authenticated import proposals, no dual authority |
| Deletion breaks lineage or legal hold | Explicit content/identity split, tombstones without content, jurisdiction/hold decision record, projection propagation proof |

## Host response form

Reply with one of:

- **approve bundle**
- **adapt bundle:** list the decision number(s) and requested changes
- **reject bundle:** identify the incompatible invariant or preferred option

Optional per-decision form:

```text
D1 canonical authority: approve / adapt / reject
D2 placement modes + private default: approve / adapt / reject
D3 seven public tools + five abstract handles: approve / adapt / reject
D4 enforcement substrate / community policy split: approve / adapt / reject
```

After host approval:

1. Claude independently re-checks the primary external sources and current
   TinyAssets context.
2. Codex incorporates approve/adapt findings and records the review.
3. PLAN receives the approved decisions and removes contradictory Open
   Tensions in a narrow reviewed change.
4. `complete-plan-gated-platform-targets` is proposed through OpenSpec.
5. No runtime implementation begins until its `applyRequires` artifacts,
   security review, task plan, and host approval are complete.

## Source register

### TinyAssets

- `PLAN.md:21-76`, `77-110`, `377-398`, `490-541`, `573-581`
- `docs/audits/2026-07-22-openspec-full-coverage-audit.md:29-105,269-312`
- `docs/design-notes/2026-04-18-full-platform-architecture.md:46-255,1217-1354,1629-1713,2238-2518`
- `docs/specs/2026-06-10-tiny-first-principles-spec.md:138-176`
- `docs/design-notes/2026-07-02-universe-visibility-and-access-model.md:15-75`
- `docs/specs/2026-04-19-connectors-two-way-tool-integration.md:21-49,222-468`
- `docs/specs/2026-06-10-primitive-basis-audit.md:5-40`
- `openspec/specs/live-mcp-connector-surface/spec.md`
- `openspec/specs/identity-auth-and-access-control/spec.md`
- `openspec/changes/universe-visibility/`
- `openspec/changes/brain-okf-canonical-store/`
- `openspec/changes/complete-independent-full-platform-targets/`
- `openspec/changes/paid-market-live-price-discovery/`
- `pages/concepts/standards-rule-packs-over-generic-receipts-and-gates.md`

### Primary and official external sources

- HHS, cloud computing under HIPAA:
  <https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html>
- HHS, business associate contract provisions:
  <https://www.hhs.gov/hipaa/for-professionals/covered-entities/sample-business-associate-agreement-provisions/index.html>
- HHS, HIPAA risk analysis:
  <https://www.hhs.gov/hipaa/for-professionals/security/guidance/guidance-risk-analysis/index.html>
- HHS, minimum necessary:
  <https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html>
- Current eCFR HIPAA safeguards:
  <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.306>,
  <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.308>,
  and
  <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.312>
- Current eCFR HIPAA minimum-necessary, BAA, and individual-access duties:
  <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.502>,
  <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.504>,
  and
  <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.524>
- HHS, Security Rule certification claims:
  <https://www.hhs.gov/hipaa/for-professionals/faq/2003/are-we-required-to-certify-our-organizations-compliance-with-the-standards/index.html>
- GDPR, official regulation:
  <https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng>
- European Data Protection Board, Article 25 guidance:
  <https://www.edpb.europa.eu/documents/guideline/guidelines-42019-on-article-25-data-protection-by-design-and-by-default_en>
- European Commission, GDPR principles and individual rights:
  <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en>
  and
  <https://commission.europa.eu/law/law-topic/data-protection/information-individuals_en>
- European Commission, processor duties, rights requests, and certification:
  <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations/controllerprocessor/can-someone-else-process-data-my-organisations-behalf_en>,
  <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/dealing-requests-individuals_en>,
  and
  <https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations/how-can-i-demonstrate-my-organisation-compliant-gdpr_en>
- IETF, SCIM schema and protocol:
  <https://www.rfc-editor.org/rfc/rfc7643.html>
  and <https://www.rfc-editor.org/rfc/rfc7644.html>
- Slack enterprise administration patterns:
  <https://docs.slack.dev/admins/scim-api/>,
  <https://docs.slack.dev/reference/scim-api/>,
  <https://docs.slack.dev/admins/audit-logs-api/>,
  and
  <https://slack.com/help/articles/1500004132581-Assign-members-to-system-roles>
- AICPA, SOC 2 examination/report:
  <https://www.aicpa-cima.com/cpe-learning/publication/soc-2-reporting-on-an-examination-of-controls-at-a-service-organization-relevant-to-security-availability-processing-integrity-confidentiality-or-privacy>
- Google Research, Zanzibar authorization paper:
  <https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/>
- Supabase, RLS, Realtime authorization, and Storage access:
  <https://supabase.com/docs/guides/database/postgres/row-level-security>,
  <https://supabase.com/docs/guides/realtime/authorization>,
  <https://supabase.com/docs/guides/storage/security/access-control>,
  and <https://supabase.com/docs/guides/storage/schema/design>
- PostgreSQL, row-security semantics and bypasses:
  <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- OpenFGA, consistency and immutable authorization models:
  <https://openfga.dev/docs/interacting/consistency>
  and <https://openfga.dev/docs/getting-started/immutable-models>
- GitHub, repository operational limits:
  <https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits>
- Model Context Protocol, tools and generic tasks:
  <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>
  and <https://modelcontextprotocol.io/seps/1686-tasks>
- Zapier, recommended trigger/action/search integration model:
  <https://docs.zapier.com/integrations/quickstart/recommended-triggers-and-actions>
- Zapier, connector definitions, auth, versions, hooks, deduplication, and
  outage behavior:
  <https://docs.zapier.com/integrations/build-cli/overview>,
  <https://docs.zapier.com/integrations/build/auth>,
  <https://docs.zapier.com/integrations/manage/versions>,
  <https://docs.zapier.com/integrations/build/cli-hook-trigger>,
  <https://docs.zapier.com/integrations/build/deduplication>,
  and <https://docs.zapier.com/integrations/manage/api-outage>
