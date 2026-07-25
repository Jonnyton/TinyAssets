# Zapier-Equivalent Automation Platform Implications

**Archival status (2026-07-23):** Historical research evidence, current only as
of the checkpoints recorded below. Re-check every code, spec, product, and
operational prescription against fresh sources and current `origin/main` before
using it. The Claude verdict remains **ADAPT**, not approval or build authority.

**Status:** research draft; architecture implications only. Claude's required
opposite-provider verdict was `ADAPT`; its two factual corrections are folded
below. The review remains at
`docs/audits/2026-07-21-zapier-automation-platform-implications-claude-review.md`.
This document does not amend `PLAN.md`, create an OpenSpec requirement, or
authorize a build. Host approval and spec-truth resolution remain required.

**Research lane:** initial provider `codex-gpt5-desktop`; opposite-provider
reviewer Claude Sonnet via `scripts/peer_agent.py`; branch
`codex/compute-market-frontier-research`; worktree
`C:\Users\Jonathan\Projects\wf-compute-market-research`; intended landing route
is a research-only draft PR after the review is folded. No runtime build is
authorized by this lane.

**Freshness:** 2026-07-21. Zapier product, developer-platform, limits, pricing,
and enterprise claims were checked against the official sources linked below.
The freshest official overview says 9,000+ apps; older official developer pages
still say 7,000+ or 8,000+, so this report uses “thousands” except when
describing that dated current claim. Interfaces is now Forms. Zapier Functions
stopped accepting new users on 2026-06-01 and is scheduled to stop running on
2026-09-01; Code by Zapier is the current target. Zapier's SDK is still labeled
open beta, and its stale “Triggers API coming May 2026” text is not treated as
evidence that feature shipped.
TinyAssets claims were checked against `PLAN.md`, current OpenSpec specs, and
the repository at `0bc841aa` (`origin/main`).

## Executive judgment

The user's requirement is sound and should be accepted as an outcome benchmark:

> A TinyAssets user should be able to automate any supported event-to-outcome
> process they could build in Zapier, while retaining TinyAssets' open,
> community-evolved, provider-neutral, and hostless-capable architecture.

This does **not** mean cloning Zapier's UI, shipping thousands of platform-owned
connectors, putting private credentials into the public commons, or creating a
new core primitive for every Zapier product. It means closing the small number
of structural gaps that prevent the community from composing equivalent
outcomes.

Zapier's current surface is best understood as six layers:

1. an integration catalog and connection/authentication system;
2. an event-to-action workflow runtime;
3. logic, timing, code, and human-review controls;
4. durable run history, replay, versions, and operational controls;
5. composition products such as Tables, Forms, Canvas, Agents, Chatbots, and
   MCP access;
6. organizational governance, connector review, and usage accounting.

TinyAssets already has a more expressive graph substrate than Zapier: typed
state, conditional edges, validated cycles, nested version-pinned branches,
checkpoints, concurrent child work, evaluation, lineage, and remix. Its commons,
daemon, and chatbot architecture can make layers 5 and 6 more open than Zapier.
The main gaps are at the system boundary: the scheduler is not wired into
production, durable external ingress is missing, app connections and outbound
MCP/API transport are unimplemented, effect safety is adapter-specific, declared
node retry policies are not applied, typed-artifact compatibility is absent,
and public chatbot handles do not expose all existing automation controls.

Most of the right target is already binding in
`openspec/specs/boundary-layer/spec.md`: commons connector definitions,
resource-ledger grants, outbound MCP, authenticated transports that hide
credentials, action caps, an effect ledger, addressable inboxes, scheduling,
and typed artifacts. The Zapier comparison therefore supports an
implementation/conformance lane and identifies semantic corrections; it does
not justify inventing a second connector architecture.

## Requirement translation: parity without cloning

“Anything Zapier can do” should be tested as an outcome matrix, not as a list of
screens:

| User outcome | Required TinyAssets ability |
|---|---|
| React to an external change | Poll, subscribe to a webhook, or accept an event with a durable cursor and deduplication identity |
| Read or find external data | Invoke a typed, authenticated, non-mutating search/read capability |
| Change an external system | Invoke an explicitly granted side effect with idempotency, retry, and an auditable receipt |
| Transform and route data | Map fields, filter, branch, loop, call a reusable subgraph, and run bounded code |
| Act later | Persist a schedule, delay, or wait condition across restarts |
| Ask a person | Pause at an approval/input gate and resume from the same checkpoint |
| Maintain working state | Read/write durable typed records or artifacts without making a private central database mandatory |
| Collect input or expose a lightweight UI | Publish a form, chatbot, MCP App, or community web artifact bound to a workflow |
| Design with AI | Have a chatbot produce, explain, validate, and remix the same typed graph a human can edit |
| Operate safely | Inspect versioned runs, errors, retries, receipts, grants, and policy decisions; replay only with explicit effect semantics |
| Share and govern | Publish reusable public patterns, keep private instances private, constrain allowed integrations/actions, and audit access |

### Testable parity definition

“Supported” is not circular. A service operation is supported only when an
immutable connector version is discoverable (public or owner-private), its
trigger/search/action contract suite passes, an actor has a valid scoped grant,
and an eligible authorized executor is available or the run truthfully holds
for one. Catalog aspiration alone does not count.

Parity is evaluated with a versioned benchmark packet that pins the chatbot
host, model, system prompt, TinyAssets connector version, adapter versions,
fixtures, attempt budget, and expected receipts. For each outcome row above:

1. a user-like prompt is typed through a real rendered supported chatbot;
2. the chatbot must create or remix a valid graph in fewer than five reasoning
   steps, matching `PLAN.md`'s composition threshold, without hidden legacy
   tools;
3. the published graph must execute against fixtures and at least one real
   authorized integration where safe;
4. run, version, grant, event, attempt, effect, cost, and acceptance evidence
   must be inspectable through canonical public handles; and
5. the same packet must pass three independent fresh runs or publish the
   observed nondeterministic failure rate rather than claiming parity.

The suite covers all eleven outcome rows, not merely connector CRUD. Its fault
matrix injects duplicate delivery, crash after intent/before result, timeout
ambiguity, `429 Retry-After`, revoked/expired grants, no authorized host, schema
mismatch, hostile connector behavior, budget exhaustion, and workflow edits
during delayed work. Expected behavior is explicit: dedupe, idempotent success,
`unknown/held` reconciliation, bounded retry, fail-closed authorization,
design-time rejection, isolated failure, budget hold, or version-pinned resume.

Product-specific conveniences remain community-built. An imported Zap or
unsupported operation may be classified `EMULATED`, `MANUAL`, or `BLOCKED`; it
cannot be advertised as `SUPPORTED` until it meets this packet.

## Zapier's current system shape

### Workflow and flow-control surface

Zapier defines a Zap as one trigger plus one or more actions. Triggers may poll
or arrive instantly by webhook. A polling trigger relies on stable unique IDs
for deduplication. Multi-step workflows add field mapping, filters, paths,
loops, schedules, delays, reusable Sub-Zaps, webhooks, code, and Human in the
Loop review. Zero, one, several, or all Path branches may match. Current
documented limits include 100 total steps, up to ten branches in one Path
group, and three nested Path levels. Paths run left-to-right while loop
iterations can run in parallel. Schedules are approximate and timezone-bound.
Delay has `For`, `Until`, and FIFO `After Queue` forms, a 30-day maximum, and
the documented hazard that editing or disabling a Zap can strand delayed work.

This is a pragmatic directed workflow graph, not a general distributed-compute
protocol. Its important semantics are durable event identity, explicit data
mapping, bounded topology, and controlled effects.

### Integration and developer platform

Zapier's freshest official overview advertises 9,000+ apps. An integration
exposes three core operation families:

- **trigger:** polling or REST-hook event source;
- **search:** read/find records and return zero or more ordered matches;
- **create/action:** create or update an item, with destructive delete actions
  discouraged and explicitly described.

The platform provides UI and CLI authoring, authentication schemes, input and
output schemas, sample/test data, HTTP hooks, automated validation, immutable
versions, semantic versioning, promotion, legacy-version continuity, private
sharing, app-directory publication, and human review. Public integrations must
meet ownership, API permission, privacy, HTTPS, credential, functionality,
listing, support, and live-test requirements.

Zapier also lets a user build a private integration and offers AI-assisted
Custom Actions over an existing app's public API. This matters strategically:
catalog breadth is not only a labor problem. A useful open platform needs a
fast path from API description to a private typed adapter, followed by a
separate trust path to public discovery.

### Data, UI, design, and agent products

Zapier now bundles several composition surfaces around the workflow runtime:

| Product | Current role | Architectural interpretation |
|---|---|---|
| Tables | Automation-first typed record storage with workflow triggers/actions | Durable workflow state and a user-facing record view |
| Forms (formerly Interfaces) | No-code multi-page operational UI with forms, buttons, Tables, Kanban, chatbots, checklists, embeds, payments, and navigation | An input/view artifact bound to records and workflow actions |
| Canvas | Visual map of people, apps, manual steps, Zaps, agents, tables, forms, and documentation | A design/projection of the automation system, not its execution truth |
| Agents | Instruction-, trigger-, tool-, and knowledge-driven agents with versions | A goal-directed workflow actor with capability grants |
| Chatbots | Embedded or standalone model UI with knowledge and Zap-backed actions | A conversational host and view over knowledge and effects |
| MCP | A per-client Streamable-HTTP server giving AI clients selected app actions | An interoperability adapter over the integration/action catalog |
| Copilot/AI authoring | Natural-language construction across products | A graph/artifact authoring assistant, not a separate runtime |

Two newer developer-facing surfaces need cautious treatment. The open-beta
Zapier SDK provides generated TypeScript actions, connection discovery, direct
authenticated API access, and experimental approvals. Powered by Zapier offers
embedded editors, a Workflow API, and limited-beta stateless Action Runs. They
show demand for headless capability invocation and embedding, but beta or
“coming soon” features are not parity requirements until they are actually
available.

Zapier Functions is being deprecated in favor of Code by Zapier in 2026, so an
equivalent design should benchmark bounded JavaScript/Python code execution,
not reproduce a retiring product.

### Execution, history, and replay

Zapier keeps per-run and per-step history, including the workflow version used.
Users can filter and inspect runs, replay errored steps, enable autoreplay, or
replay an entire run. Autoreplay retries errors up to five times on a widening
schedule. Ordinary failed-step replay does not recompute earlier Filters or
Paths; full replay creates a new run, applies the current published workflow,
and may repeat already successful effects. Deleting a completed history record
cannot undo the external action. History displays at most 10,000 runs and is
only guaranteed for up to 60 days. This is a useful warning for TinyAssets:
generic “replay” is unsafe unless each effect exposes idempotency and
compensation semantics, and short troubleshooting retention cannot substitute
for durable provenance.

Polling, webhooks, plans, and third-party APIs impose distinct limits. Polling
triggers deduplicate by unique record identity inside a Zap; instant webhook
triggers do not provide that same deduplication guarantee. Zapier may hold work
when task allowances or controls prevent execution, and users can later replay
held runs. Instant webhooks may be accepted with `200` but delayed under burst
pressure. TinyAssets should similarly distinguish accepted, queued,
running, waiting, held, interrupted, failed, and terminally accepted work
without promising impossible global exactly-once delivery.

### Pricing and task accounting

Zapier primarily meters successful action steps as tasks. Many built-in control
steps are zero-task; a Zapier MCP tool call currently counts as two tasks; code
and AI work have additional accounting rules; BYOM users also pay their model
provider. Replay can charge successful steps again.

TinyAssets should learn from the transparent unit and avoid importing the
business model. Paid execution belongs in the existing paid-market commercial
envelope. A provider quote should disclose the execution unit, included retries,
external API/model charges, and settlement evidence before a user authorizes a
paid route.

### Enterprise and trust controls

Zapier offers account roles, shared assets, SAML SSO, SCIM, audit logs, custom
retention, analytics, app/action access policies, domain controls, and broad
administrator visibility. Its app directory has automated validation plus
publication review and version lifecycle rules.

Zapier's controls also have instructive gaps: raw/API-style surfaces can escape
ordinary app controls, triggers cannot always be prohibited individually, and
some policy resolution favors broader access. TinyAssets needs equivalent
governance outcomes but should express them through
identity, ownership, grants, gates, immutable artifacts, signed provenance, and
auditable receipts. A central super-admin reading every private asset conflicts
with TinyAssets' private host-resident posture and should not be copied.

## TinyAssets mapping

The mapping below separates existing substrate from gaps. “Existing” means a
current behavioral spec or implementation, not that a polished Zapier-like UX
already exists.

| Zapier concept | TinyAssets substrate | Assessment |
|---|---|---|
| Zap / workflow | Branch definitions, graph nodes/edges, compile validation, checkpointed runs | Strong existing core |
| Trigger | Persisted schedule/subscription definitions exist | Not operational: scheduler has no production startup caller; event queue is in-memory with no production producer |
| Filters / Paths | Conditional graph edges and branch topology | Existing core; current fallback behavior needs careful authoring |
| Loop / Sub-Zap | Validated cycles plus synchronous/asynchronous version-pinned child branches | TinyAssets is structurally stronger |
| Delay / Schedule | Generic branch schedule definitions and checkpoint recovery exist | No first-class durable wait/delay node; generic scheduler is unwired; boundary-layer standing-goal/timezone schedule does not exist in code |
| Human in the Loop | Gates, approval claims, interrupted-run resume guards | Strong conceptual fit |
| Zap history | Rich run/event/receipt/checkpoint evidence | Strong backend evidence; user-facing effect ledger, retry, and replay controls are gaps |
| App connection | Boundary-layer resource-ledger grants are specified; credential vault is provider-specific | Major implementation gap: reusable OAuth/scoped/revocable app connections do not exist |
| App integration | Boundary-layer commons connectors/OpenAPI-to-MCP adapters are specified | Major implementation gap: no outbound MCP or general adapter runtime |
| Trigger/search/action catalog | Nodes and capabilities can represent the operations | Versioned typed connector catalog and public composition surface remain gaps; do not add three MCP verbs |
| Webhook ingress | Addressable webhook/email inboxes are required by boundary-layer | Missing: HTTP/MCP front doors are not external-event inboxes and no production ingress producer exists |
| Code by Zapier | `source_code` graph nodes | Unsafe for parity today: in-process execution is explicitly an as-built limitation |
| Tables | Artifacts/brain/state fields plus community views | Mostly community-build; typed artifact compatibility is specified but unimplemented and current state schema is weakly validated |
| Forms | Chatbot questions, MCP Apps, or community web artifacts | Community-build after a safe public input binding exists |
| Canvas | Branch graph projection plus documentation/wiki | Community-build projection, not a new source of truth |
| Agents | Daemons, goals, branches, provider routing, knowledge/artifacts | Existing native model is broader |
| Chatbots | Tier-1 chatbot connector and conversational authoring | Native strategic surface; embeddable standalone view may be community-built |
| Zapier MCP | Existing inbound Streamable-HTTP server; boundary layer requires outbound MCP | Inbound live; outbound connection runtime is spec-only |
| App directory/templates | Commons discovery, wiki, remix, immutable versions | Strong strategic fit; integration-specific trust metadata is missing |
| Zapier SDK / Powered by Zapier | API/MCP surfaces plus graph authoring | Useful headless pattern; current Zapier beta surfaces are not stable requirements |
| Enterprise app policy | Access control, ownership, grants, policy gates | Partial; connector/action allow/deny policy and audit UX need proof |
| Usage billing | Paid-market request/bid/claim/settlement | Strong fit after domain-specific execution evidence is defined |

### As-built evidence and contradictions

The repository audit found these implementation facts at `0bc841aa`:

- `tinyassets/branches.py` and `tinyassets/graph_compiler.py` already model the
  expressive core: typed state/reducers, conditional routing, validated cycles,
  nested branches, concurrency, effects, versions, and publication.
- `tinyassets/runs.py` already records asynchronous execution, events,
  cancellation, checkpoint recovery, receipts, judgments, lineage,
  provider/model/token evidence, and immutable version binding.
- `tinyassets/scheduler.py` persists schedule and subscription definitions, but
  `get_or_create_scheduler()` has no production caller. Its event queue is
  process-memory-only, `emit_event()` has no production producer, and the
  process-global singleton captures the first base path.
- Event dispatch marks an identity delivered before calling the run launcher,
  so a crash can lose it. Schedule dispatch records `last_fired_at` after the
  launch, so a crash can duplicate it.
- `NodeDefinition.retry_policy` is editable but neither graph compilation nor
  run execution consumes it.
- `tinyassets/idempotency.py` caches results after the external function
  returns; concurrent calls can both effect before either result is inserted.
  Existing GitHub/desktop/wiki/Twitter effectors have stronger domain-specific
  reservation patterns, but there is no generic intent/result effect ledger.
- General app connections, outbound MCP, auth-withholding transport, generated
  OpenAPI adapters, typed artifacts, and addressable webhook/email inboxes are
  requirements in `openspec/specs/boundary-layer/spec.md`, not implemented
  runtime behavior.
- The credential vault resolves selected provider/GitHub credentials but is not
  a general OAuth grant, scope, refresh, reconnect, ownership, and revocation
  lifecycle.
- Canonical public MCP graph handles can inspect, patch, and launch existing
  branches, but branch creation, schedules/subscriptions, connection binding,
  and run resume/cancel/replay remain hidden behind legacy extension surfaces.
- The public website graph is a read-only commons projection, not an automation
  editor. Conversational authoring remains the right primary direction, but the
  chatbot lacks the required canonical controls.

An older design note (`2026-04-26-minimal-primitive-set-proposal.md`) says
Zapier is linear and lacks first-class branching. Current Zapier has Paths,
Filters, Looping, Delay, and Sub-Zaps; that historical comparison must not guide
new implementation.

## Minimal automation contract

Zapier's terms map cleanly onto the binding boundary-layer roles. The labels
below clarify lifecycle responsibilities and must be implemented through
existing branches, nodes, artifacts, capabilities, grants, and ledgers rather
than promoted into new MCP tools by default.

```text
Public commons
  ConnectorDefinition@immutable-version
    auth requirements (never credentials)
    trigger/search/action capability schemas
    input/output/event schemas + fixtures
    side-effect, idempotency, rate, and privacy metadata
    implementation artifact + provenance + review status

Private authorized host
  ResourceLedgerGrant
    owner + integration version + external account identity
    secret reference + scopes + expiry/revocation
    allowed capabilities + data residency/egress policy

Runtime
  TriggerSubscription -> EventEnvelope -> existing Branch/Run
  existing Branch/Run -> EffectIntent -> authorized capability
  authorized capability -> EffectReceipt -> existing Run/Artifact/Gate
```

These roles create one stable boundary:

- A manifest says **what an adapter can do** and how to validate its shapes.
- A grant says **who authorized which private connection** and where its secret
  is held.
- An event says **what happened once**, with source identity, cursor/dedup key,
  schema version, observed time, and payload reference.
- An effect intent says **what external mutation is requested**, under which
  run, approval, integration version, grant, and idempotency key.
- A receipt says **what the provider reports happened**, including response
  identity, attempt, timestamps, billable usage, error class, and evidence.

This is not a universal execution protocol. Each domain adapter retains its own
polling, webhook, search, and effect protocol. The shared contract is the
authorization, lifecycle, evidence, and composition envelope.

## Scoping Rules pass

### 1. Irreducibility

Do not add `create_zap`, `make_form`, `create_table`, `build_chatbot`, or one MCP
tool per connector action. Those are conveniences composable from graphs,
artifacts, gates, and adapters.

The irreducible boundary is already identified in the binding `boundary-layer`
spec: a versioned commons connector definition bound through a resource-ledger
grant to authenticated transport and a durable effect ledger. The remaining
question is how to implement that requirement through existing capability,
artifact, branch, and claim records with the least new code.

### 2. Community-build

Integrations, templates, forms, tables, canvases, chatbots, field mappers, and
business workflows should be commons artifacts that users and chatbots can
remix. The platform should ship the safe composition and execution boundary,
not the catalog's content.

### 3. Commons-first private data

Public connector definitions, schemas, tests, and workflow patterns belong in
the commons. Credentials, private payloads, private records, and private run
details remain on an authorized host. Public artifacts may carry hashes,
redacted receipts, aggregate reliability, and discoverable metadata, never
private secrets or content.

### 4. Architectural placement

- OpenSpec owns behavioral requirements.
- `PLAN.md` continues to own the why and must not be amended without host
  approval.
- Graph runtime owns workflow state transitions.
- Domain adapters own external API semantics.
- Identity/grants own authority.
- Daemons own execution and private custody.
- Commons artifacts own discovery, remix, provenance, and public reputation.
- Paid market owns optional commercial selection and settlement.

### 5. Runtime tier

Public workflows may run on eligible community or paid daemons. Private
automation requires an explicitly authorized host that can access the relevant
credentials and payload. If no authorized host is online, work must remain
queued/held with a truthful status. “Zero hosts online” cannot mean that the
public TinyAssets service silently takes custody of private SaaS credentials.
It also cannot mean falling back to founder/maintainer Claude or OpenAI quotas:
execution is requester BYOC/BYOM or an explicitly accepted market offer only.

## Reliability semantics TinyAssets should require

An automation platform fails at the boundaries, not in the happy-path graph.
The existing boundary-layer spec plus any implementation-conformance change
should define or preserve at least:

- stable integration and operation keys across versions;
- polling cursors and event deduplication windows;
- signed webhook verification and subscription lifecycle;
- bounded payload size and schema versioning;
- rate-limit classification, retry-after handling, exponential backoff, and
  dead-letter/held states;
- idempotency keys scoped to run, effect, adapter version, and target account;
- explicit side-effect classes: read-only, idempotent write, non-idempotent
  write, destructive, and compensatable;
- per-attempt records and one immutable terminal receipt;
- replay modes that distinguish retrying the failed effect, resuming from a
  checkpoint, and starting a wholly new run;
- an explicit branch-decision replay policy: reuse recorded decisions or
  recompute them, never silently mix old Paths with new downstream effects;
- compensation instructions where the external system supports them, without
  pretending rollback is universal;
- concurrency and lease fencing for subscription ownership and effect workers;
- observable cost/usage attribution across TinyAssets compute, provider API
  charges, and paid-daemon settlement.

The external side effect is at-least-once unless the target system honors an
idempotency key or exposes authoritative reconciliation. TinyAssets can
guarantee exactly-once **acceptance of an event identity per subscription** and
exactly-once **recording of a terminal receipt under a fenced attempt**, but it
cannot guarantee exactly-once mutation in an arbitrary third-party API.

This reveals a binding-spec correction that must be resolved before build.
`boundary-layer` requires a deterministic key plus intent-before-call and
result-after-call journal to guarantee exactly-once effects. The journal alone
does not close the crash/timeout ambiguity between the external mutation and
the result write. For a target without provider idempotency or a status query,
an unresolved intent must become `unknown/held-for-reconciliation`, never be
blindly retried. The safety objective—no automatic duplicate effect and no
partial-silent batch—should remain hard; the universal external exactly-once
claim should be narrowed to providers that can prove it.

The scheduler has a second truth mismatch: its OpenSpec scenario is titled
“exactly once,” while the implementation writes the delivered marker before
launch and is therefore at-most-once with a loss window. Schedule launch has
the opposite duplicate window because `last_fired_at` is written after launch.
These are conformance blockers, not connector UX details.

## Security and connector trust

An open connector ecosystem is also an executable-code and credential supply
chain. Publication should therefore be staged:

1. **private draft:** owner-scoped, visibly unreviewed, limited to explicit
   grants;
2. **shared test:** immutable version, fixtures and contract tests, narrow
   invite scope;
3. **public candidate:** provenance, API permission, auth/egress declaration,
   static checks, sandbox proof, live tests, maintainer identity, and security
   review;
4. **public promoted:** discoverable default with old immutable versions kept
   runnable for pinned workflows;
5. **legacy/revoked:** no new binding; existing use either continues under an
   explicit risk posture or fails closed for a security revocation.

Required controls include least-privilege scopes, secret references instead of
secret values, revocation, egress allowlists, dependency locking/SBOM,
provenance signatures, destructive-action labeling, output-size limits,
malicious-payload handling, tenant isolation, and connector-specific rate
limits. Public reputation cannot substitute for sandboxing or authority checks.

Testing write capabilities against live connections is itself an effect. The
platform should prefer fixtures, provider sandboxes, and dry-run validation,
and must make any live or destructive contract test conspicuous and separately
authorized.

The current `source_code` node executes in-process behind a fail-closed approval
gate; the spec explicitly calls the standalone sandbox disconnected from the
compile path. That is a P1 blocker for arbitrary community connector code and
Code-by-Zapier parity. Do not broaden executable integrations until OS/container
isolation, egress control, resource limits, and secret boundaries are proven.

## Interoperability strategy

TinyAssets should not force every service into a custom connector SDK. A single
manifest can point to multiple adapter implementations:

- native HTTP/OpenAPI adapter;
- MCP client adapter;
- provider-maintained SDK/code adapter;
- webhook-only or polling-only adapter;
- local desktop/CLI adapter for apps that have no network API;
- paid daemon capability for specialized custody or infrastructure.

MCP is especially important because Zapier now exposes selected app actions to
AI clients through per-client MCP servers. TinyAssets already exposes an MCP
server; outbound MCP-client support would let community workflows consume
Zapier or any other MCP provider as one adapter source. It must still enforce
TinyAssets grants, schemas, effect classes, receipts, and private-host policy.
MCP transport interoperability is not authority interoperability.

OpenAPI or natural-language import should generate a **draft** manifest and
fixtures, never auto-promote an integration. A chatbot can propose mappings;
tests, review gates, and user grants establish trust.

### Zapier bridge/import posture

Outcome parity does not imply lossless Zap import. Any bridge should classify
each source element as `SUPPORTED`, `EMULATED`, `MANUAL`, or `BLOCKED` and
explain the difference before activation. A portable import record needs the
trigger kind, event identity/dedup scope, pinned connector operation versions,
field mappings, filters, Paths, loops, queues, delays, subflows, error branches,
retry and replay mode, connection references, data classification, approvals,
retention, budget ceiling, and effect/idempotency semantics. Credentials and
captured private sample payloads are never imported into a public node.

Zapier-specific behavior that cannot be preserved—stale Path decisions during
failed-step replay, bearer-secret catch-hook URLs, a 30-day delay ceiling, or a
proprietary product step—must be surfaced as an explicit adaptation or blocker,
not silently reinterpreted.

## Relationship to the compute and model market

The compute-market report and this automation report are complementary:

```text
Automation layer
  discovers an event, composes a workflow, requests effects
        |
        v
Existing TinyAssets graph / run / gate / artifact substrate
        |
        +--> external service adapter (Zapier-like action)
        |
        +--> paid-market envelope (optional compute/task/fabrication provider)
```

An automation can request inference, tuning, training, hosting, fabrication, or
ordinary SaaS actions. The paid-market selector prices optional commercial
execution; it does not replace the workflow runtime or connector protocol. A
user or chatbot chooses whether to use a free/community/local route before any
paid selector runs.

## Adopt / adapt / avoid / defer

### Adopt

- one-trigger/many-action mental model as an approachable authoring view;
- typed trigger, search, and action schemas;
- polling plus webhook event sources with deduplication;
- immutable connector and workflow versions;
- live fixtures, contract validation, and staged publication;
- run/step history, held states, selective retry, and explicit full replay;
- reusable subgraphs, human approval, schedules, delays, filters, paths, loops;
- connection-scoped auth and organization policy over integrations/actions;
- MCP as an adapter and client interoperability path.

### Adapt

- Zapier's centralized app directory into an open commons with signed
  provenance and plural execution providers;
- centrally stored connections into private host-resident grants;
- central task pricing into transparent provider quotes and the existing paid
  market;
- Tables, Forms, Canvas, Agents, and Chatbots into remixable compositions over
  shared primitives;
- “exactly once” product language into precise event, attempt, effect, and
  receipt guarantees;
- AI-generated integrations into draft manifests requiring tests and review.

### Avoid

- cloning every Zapier product surface;
- one platform-owned connector implementation per app;
- a fat action-router MCP tool or thousands of advertised MCP tools;
- secrets or private payloads in public platform storage;
- silent fallback to paid execution;
- generic replay that repeats non-idempotent effects without warning;
- automatic selection of any accessible connection for a write;
- a raw HTTP/SDK escape hatch that bypasses capability policy;
- unreviewed community code running in the daemon process;
- treating a successful HTTP response as sufficient settlement evidence;
- making one proprietary workflow JSON format the interoperability standard.

### Defer

- a first-party spreadsheet/database competitor;
- a first-party hosted form/site builder beyond minimal bindings;
- a proprietary embedded chatbot product;
- platform custody of external credentials;
- public promotion of arbitrary executable connectors before isolation lands;
- broad enterprise feature cloning until the underlying grants, audit, and
  policy primitives are stable.

## Gap assessment and sequence

### P0: research/design gate

1. Opposite-provider review this report against current official Zapier sources
   and TinyAssets specs.
2. Host decides whether “Zapier-equivalent outcomes” becomes an approved
   architecture direction in `PLAN.md`.
3. Resolve the boundary-layer universal-exactly-once contradiction and the
   scheduler spec/implementation delivery mismatch.
4. If approved, propose an OpenSpec implementation/conformance change for the
   existing boundary layer; do not start with a Forms or Canvas feature or a
   competing connector model.

### P1: safety and runtime prerequisites

1. Close the existing executable-code isolation gap before community connector
   code can run.
2. Replace the unwired process-global scheduler/event queue with hostless,
   multi-tenant due-work claims, leases, persistence-before-ack ingress, and
   truthful held states.
3. Implement the specified private resource-ledger grants, authenticated
   transport, scope/revocation, and authorized-host selection.
4. Generalize the existing adapter-specific effect reservations into the
   required intent/result ledger with unknown-state reconciliation, attempt
   fencing, receipts, whole-batch holds, and safe replay.
5. Apply declared per-node retry/error policy only after effect safety exists.
6. Prove signed webhook subscriptions, polling cursors, deduplication, durable
   timers, and rate-limit behavior under the required concurrency/load gate.

### P2: ecosystem substrate

1. Versioned commons connector definition and contract-test kit.
2. Private draft/import path for HTTP/OpenAPI and MCP adapters.
3. Commons discovery, compatibility, provenance, reputation, promotion,
   legacy, and revocation lifecycle.
4. Route trigger, connection, and run controls through the existing canonical
   graph handles, then let chatbots compose connectors into branch graphs.
5. User-facing run/effect history and safe replay controls.

### P3: community compositions

Publish reference patterns for forms, tables, canvases, reusable subflows,
chatbots, agents, approvals, schedules, and common app categories. Promote these
through use and remix rather than freezing them as platform products.

## Builder pickup packet

Any implementation lane derived from this report should begin with:

- approved `PLAN.md` direction or an explicit note that no architecture change
  is required;
- an OpenSpec change with proposal, design, delta specs, tasks, and all
  `applyRequires` artifacts complete;
- exact mapping of proposed fields into existing branch, node, trigger, gate,
  artifact, identity, capability, and paid-market records;
- threat model covering connector code, secrets, egress, webhook forgery,
  malicious payloads, confused deputy, replay, SSRF, dependency compromise,
  tenant crossing, and destructive actions;
- state-machine and concurrency proof for subscriptions, attempts, leases,
  receipts, timers, retries, and revocation;
- contract fixtures for one polling trigger, one signed webhook trigger, one
  search, one idempotent write, one non-idempotent write, and one MCP action;
- load tests satisfying full-platform architecture §14 for webhook bursts, poll fleets,
  delayed work, worker failover, and duplicate delivery;
- a real rendered chatbot acceptance conversation and post-fix clean-use watch
  before a public-surface claim is considered proven.

### Candidate implementation-lane landing packet

This is a handoff proposal, not an active claim or build authorization:

- lane source: this audit plus its Claude review;
- proposed branch: `spec/boundary-layer-conformance`;
- proposed worktree: `../wf-boundary-layer-conformance`;
- base: freshly fetched `origin/main` at claim time, recorded in `_PURPOSE.md`;
- first write-set: `openspec/changes/boundary-layer-conformance/`, plus the
  exact `STATUS.md`, `ideas/PIPELINE.md`, and `.agents/worktrees.md` coordination
  edits needed to claim it;
- first slice: reconcile universal exactly-once wording and scheduler delivery
  truth, then specify the smallest hostless multi-tenant due-work/ingress proof;
- later code write-set: selected only after proposal/design/delta specs/tasks and
  threat/concurrency artifacts pass review—never pre-claim all of `tinyassets/`;
- review gates: this opposite-provider research review, host approval for any
  `PLAN.md` direction, strict OpenSpec validation, independent implementation
  review, §14 concurrency/load proof, rendered chatbot acceptance, and clean-use
  watch;
- foldback: draft PR first, no live push or deployment, sync specs and archive
  the OpenSpec change only when the verified implementation lands.

## Source provenance

All external product claims were checked against official Zapier sources:

- Current overview and app count:
  <https://help.zapier.com/hc/en-us/articles/37518970271245-What-is-Zapier>
- Key concepts and workflow model:
  <https://help.zapier.com/hc/en-us/articles/8496181725453-Learn-key-concepts-in-Zap-workflows>
- Flow controls and conditional logic:
  <https://help.zapier.com/hc/en-us/sections/41011221634445-Flow-controls>
- Schedule and delay behavior:
  <https://help.zapier.com/hc/en-us/articles/8496288648461-Schedule-Zaps-to-run-at-specific-intervals>,
  <https://help.zapier.com/hc/en-us/articles/8496288754829-Add-delays-to-Zap-workflows>, and
  <https://help.zapier.com/hc/en-us/articles/8496061204621-Common-Problems-with-Delay>
- Trigger behavior:
  <https://help.zapier.com/hc/en-us/articles/8496244568589-How-Zap-triggers-work>
- Webhooks and rate limits:
  <https://help.zapier.com/hc/en-us/articles/8496288690317-Trigger-Zap-workflows-from-webhooks>
  and
  <https://help.zapier.com/hc/en-us/articles/29972220283789-Webhooks-by-Zapier-rate-limits>
- Workflow limits:
  <https://help.zapier.com/hc/en-us/articles/8496181445261-Zap-limits>
- Replay and history:
  <https://help.zapier.com/hc/en-us/articles/8496241726989-Replay-Zap-runs>
  and
  <https://help.zapier.com/hc/en-us/articles/8496291148685-View-and-manage-your-Zap-history>
- Duplicate-effect behavior:
  <https://help.zapier.com/hc/en-us/articles/8496260269965-How-Zapier-handles-duplicate-data-in-Zap-workflows>
- Developer trigger/action/auth/CLI/version model:
  <https://docs.zapier.com/integrations/build/trigger>,
  <https://docs.zapier.com/integrations/build/action>,
  <https://docs.zapier.com/integrations/build/auth>,
  <https://docs.zapier.com/integrations/build-cli/overview>, and
  <https://docs.zapier.com/integrations/manage/versions>
- Publishing and validation:
  <https://docs.zapier.com/integrations/publish/integration-publishing-requirements>
  and
  <https://docs.zapier.com/integrations/publish/integration-checks-reference>
- Tables:
  <https://help.zapier.com/hc/en-us/articles/29712888250509-Zapier-Tables-quick-start-guide>
- Forms:
  <https://help.zapier.com/hc/en-us/articles/27310207159053-Zapier-Forms-quick-start-guide>
- Canvas:
  <https://help.zapier.com/hc/en-us/articles/19880280846221-Create-a-canvas-to-visualize-your-automated-system>
- Agents:
  <https://help.zapier.com/hc/en-us/articles/24393442652557-Build-an-agent-in-Zapier-Agents>
- Chatbots:
  <https://help.zapier.com/hc/en-us/articles/21960697323533-Set-up-a-chatbot>
- Zapier MCP:
  <https://help.zapier.com/hc/en-us/articles/36265392843917-Use-Zapier-MCP-with-your-client>
- Zapier SDK and Powered by Zapier:
  <https://docs.zapier.com/sdk> and
  <https://docs.zapier.com/powered-by-zapier>
- Code/Functions transition:
  <https://help.zapier.com/hc/en-us/articles/45230540637453-Important-update-Zapier-Functions-is-being-deprecated>,
  <https://help.zapier.com/hc/en-us/articles/45230556598157-Migrate-from-Zapier-Functions-to-Code-by-Zapier>, and
  <https://help.zapier.com/hc/en-us/articles/45405528551181-Using-Code-by-Zapier>
- Task accounting and pricing:
  <https://zapier.com/pricing/rates> and
  <https://help.zapier.com/hc/en-us/articles/8496196837261-How-is-task-usage-measured-in-Zapier>
- Roles, app policy, retention, and enterprise controls:
  <https://help.zapier.com/hc/en-us/articles/39698983334797-User-roles-and-permissions-in-Team-and-Enterprise-accounts>,
  <https://help.zapier.com/hc/en-us/articles/8496307974541-App-access-policies-in-Zapier>, and
  <https://help.zapier.com/hc/en-us/articles/8496327478413-Customize-data-retention-in-Zapier>

Primary TinyAssets evidence:

- `PLAN.md` Scoping Rules, Cross-Cutting Principles, privacy, daemon, provider,
  runtime, market, and uptime/load-test sections;
- `openspec/specs/graph-execution-substrate/spec.md`;
- `openspec/specs/boundary-layer/spec.md`;
- `openspec/specs/daemon-runtime-and-dispatch/spec.md`;
- `openspec/specs/identity-auth-and-access-control/spec.md`;
- `openspec/specs/live-mcp-connector-surface/spec.md`;
- `openspec/specs/provider-routing/spec.md`;
- `openspec/specs/paid-market-economy/spec.md`;
- `openspec/specs/paid-market-training/spec.md`;
- `openspec/specs/paid-market-price-index-and-forwards/spec.md`.
