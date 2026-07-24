## Context

The integrated architecture's Section 14 and the 2026-04-18 Track J plan
describe useful target workloads, but they predate the deployed topology and
have never produced a complete public capacity envelope. The 2026-07-21
user-growth audit correctly classified the public service as an edge proxy
feeding one origin and one shared host volume, with process-local/file/SQLite
correctness seams. Its Claude review returned `ADAPT`, not implementation
approval, and requires a fresh current-main review before any prescription is
used.

A 2026-07-24 repository check against `origin/main` `412a876a` preserves the
source-defined mismatch precisely:

- the Cloudflare Worker forwards `/mcp` to one tunnel origin, performs no edge
  rate limiting, and has no origin failover
  (`deploy/cloudflare-worker/README.md`, "Limitations");
- one daemon container and four fixed Codex/Claude cloud-worker services share
  `tinyassets-data` and provider auth homes
  (`deploy/compose.yml`, daemon environment/volume and cloud-worker service
  definitions);
- the canonical `distributed-execution` spec says the only built-in
  `SandboxBackend` is unavailable and no production execution path invokes the
  runner (`openspec/specs/distributed-execution/spec.md`, "The only built-in
  backend is unavailable and the seam is unwired"); and
- there is therefore no requester-authorized public executor or usable
  OS-isolating distributed runner proven by those sources, even though fixed
  worker processes exist.

A separate bounded live probe reported deployed release SHA `519fb2ea`, while
also recording that its worker evidence lacked build/config/protocol fields and
could not prove even a build-bound active-worker count
(`docs/ops/operator-request-v2-inventory.md`, "Live/runtime evidence"). That
probe is a deployment observation, not a throughput, isolation, failover, or
public-executor envelope.

The current truth must be measurable without pretending it is the target
PostgreSQL topology. Conversely, a future topology should reuse the same
scenario/evidence contract rather than fork a new "Section 14" implementation.
Draft PR #1670 currently includes its own broad PostgreSQL load-proof plan. It
remains the owner of the PostgreSQL control plane, while this change becomes
the owner of the topology-neutral harness and evidence envelope.

This is a planning-only change. Its proposal, design, delta spec, and unchecked
tasks may land. No implementation or baseline execution follows until a fresh
Claude opposite-provider verdict is accepted. PLAN or product-boundary
changes, budgets, production access/effects, first-write/activation, and
numerical public-launch SLOs remain explicit host/product-owner decisions;
ordinary factual or spec adaptations close through accepted re-review.

## Goals / Non-Goals

**Goals:**

- Run one versioned capacity/isolation scenario catalog through replaceable
  topology adapters.
- Baseline the dated `412a876a`
  single-origin/shared-volume/no-public-executor observation honestly before
  selecting optimizations.
- Publish only freshness-stamped, reproducible, measured lower bounds; report
  unproved paths as `unknown`.
- Exercise steady load, burst, saturation, recovery, noisy-neighbor,
  cross-tenant, zero-host, and execution-authority boundaries.
- Make unsafe production/external/provider/market effects impossible by
  default and observable if a fixture attempts them.
- Preserve domain ownership while letting domain suites contribute workloads
  and assertions to one run packet.
- Make PR #1670 implement and consume a PostgreSQL topology adapter instead of
  copying the generic scenario catalog or envelope machinery.

**Non-Goals:**

- Implement or run the harness in this lane.
- Approve a launch workload, SLO, capacity number, vendor tier, or Track J
  threshold.
- Treat historical targets, vendor quotas, unit/race tests, skipped jobs, or
  one successful run as current capacity evidence.
- Authorize production writes, deployments, migrations, failover, provider
  invocation, market purchases, payments, moderation effects, or first writes.
- Define identity, visibility, universe ownership, execution grants, provider
  routing, operator-request admission, paid-market transitions, live-price
  authority, or uptime activation.
- Reclassify maintainer cloud workers as public/requester-authorized executors.
- Move private content, credentials, or production data into a test system.

## Decisions

### One harness owns scenarios and evidence; adapters own topology mechanics

The future harness has three logical layers:

```text
accepted workload profile + domain workload/assertion plug-ins
                            |
              versioned scenario catalog
                            |
       topology adapter + isolated run namespace
                            |
 raw measurements -> validated evidence packet -> verified envelope
```

A topology adapter describes and drives one concrete environment without
changing scenario meaning. Its manifest includes a stable topology ID and
revision, source/image/config revisions, region, gateway replica count,
authority stores, queues, realtime transport, pools, executor classes,
credential/provider availability class, fault controls, and explicitly
unsupported operations. Its operations cover bounded setup/seed, request and
workload driving, telemetry capture, supported fault injection, and scoped
teardown.

The harness validates the manifest and refuses an adapter that omits a required
field, claims a feature without a probe, or cannot prove that its namespace is
isolated. Unsupported operations stay explicit and make the affected envelope
cell `unknown`; they do not become no-ops or skipped successes.

Alternatives rejected:

- **One script suite per topology:** scenario and percentile semantics drift,
  and draft PR #1670 becomes a second Track J owner.
- **A vendor-specific Supabase harness:** it cannot baseline the deployed
  single-origin system or prove the stock-PostgreSQL exit.
- **Mocks only:** useful for safety and deterministic failure injection, but
  insufficient for topology capacity.

### The scenario catalog composes domain-owned assertions

The shared catalog owns cross-cutting scenario shape: steady state, burst,
saturation, recovery, topology loss, noisy neighbor, tenant isolation,
zero-host mode, and execution-authority isolation. A workload profile binds
dataset sizes, tenant mix, request mix, durations, payloads, hot-key
distribution, fault schedule, thresholds, and provenance.

Domain plug-ins supply only their accepted command drivers and assertions.
They do not grant new authority or let the generic harness reinterpret a
domain state machine:

| Concern | Owning capability/change | Harness role |
|---|---|---|
| MCP connection, SSE/session, cancellation and reconnect | `live-mcp-connector-surface` and its accepted runtime owner | Drive only accepted session workloads and preserve owner resume/error semantics |
| Commons discovery, remix and live collaboration | `wiki-commons`, discovery/collaboration owners, and PLAN-gated successors | Measure owner-published reads/writes/presence assertions; do not invent missing collaboration state |
| Webhook and external ingress/effects | `external-effect-adapters`, boundary/receipt owners, and real-world-handoff successor | Orchestrate accepted duplicate/reorder/recovery cases; never emit an effect directly |
| Export and GitHub projection | canonical export/projection owner | Measure accepted cadence/drift behavior; never target production repositories by default |
| Storage growth, retention, deletion and recovery | owning storage/lifecycle/uptime capabilities | Collect owner assertions; do not choose retention, deletion, or durability policy |
| Moderation and abuse response | moderation owner and PLAN-gated successor | Schedule accepted abuse workloads; never moderate or reserve funds directly |
| Operator request admission, epochs, claim and zero-capacity states | `daemon-runtime-and-dispatch` / `operator-request-trigger-contract` | Schedule the accepted storm and collect its owner assertions |
| Paid inbox, bid, claim, delivery, accounting and zero-host behavior | `paid-market-economy` / `paid-market-track-e-wave-2-transport` | Orchestrate its accepted suite; never mutate or settle directly |
| Quote eligibility, price freshness and forward authority | `paid-market-price-index-and-forwards` / `paid-market-live-price-discovery` | Measure owner-defined reads/decisions; never invent a quote or purchase |
| Universe creation, founder binding and soul lifecycle | `universe-lifecycle-and-soul` / `universe-creation` | Invoke only accepted test fixtures and assert owner results |
| Request identity and operator-scoped test reset | `identity-auth-and-access-control` and `test-identity-harness` | Consume identities/reset plans; never select or reset a principal itself |
| Existence, metadata and page visibility | `universe-visibility` | Exercise accepted reads and assert no cross-scope disclosure |
| Executor isolation and authority | `distributed-execution`, credential/provider owners | Consume capability/receipt evidence; never manufacture a grant |
| Serving recovery and alarms | `uptime-and-alarms` | Record outcomes; never authorize production failover or activation |

If a required owner has no accepted implementation or test driver, that domain
path is `unknown`. A generic synthetic substitute may test harness mechanics
but cannot establish that domain's envelope.

### Evidence is typed, attributable, and conservative

Each run emits an immutable evidence packet containing:

- run/scenario/profile IDs and schema versions;
- exact source, image, configuration, adapter, topology, dependency, and
  environment fingerprints;
- isolated namespace and dataset manifest;
- threshold values plus provenance (`historical_target`,
  `unapproved_hypothesis`, or `accepted_gate`);
- exact commands, start/end timestamps, warm-up/measurement durations, and
  successful repetition count;
- raw sample/artifact digests and locations;
- request/stream/transaction counts; p50/p95/p99/max; throughput; errors,
  timeouts, retries, cancellations, disconnects, duplicates, loss, deadlocks,
  and conflicts;
- CPU, memory, disk/fsync/WAL where applicable, handles, network, pool/queue
  occupancy, backlog/oldest age, realtime catch-up, and recovery timings;
- per-tenant throughput/wait/error distributions and dominant-tenant share;
- credential/provider/market/external-effect sentinel results;
- unsupported, unavailable, omitted, and failed dimensions; and
- reviewer verdict, review date, landing SHA, and caveats.

Envelope publication is a deterministic projection over accepted packets. A
cell is:

- `verified` only for the exact topology/profile/fault dimension with current
  passing evidence, an accepted threshold, the required successful repetition
  count, raw evidence, and independent review;
- `failed` when an applicable executed proof violates an accepted gate; or
- `unknown` when evidence, applicability, threshold approval, telemetry,
  repetition, review, or freshness is absent.

`stale` is explanatory metadata, not a green state: an expired packet or
changed source/image/config/topology fingerprint makes the current cell
`unknown` while retaining the historical result. The profile must define its
freshness window and repetition rule before execution; the harness supplies no
convenient universal default. Published numbers are measured lower bounds, not
extrapolations to DAU or vendor ceilings.

### Safety is deny-by-default and part of the evidence

The runner starts with production target/network/store/read access, production
mutation, provider/model invocation, market purchase, payment, wallet,
external-effect, founder/maintainer credential, and founder/maintainer hardware
access disabled. It requires an isolated, run-scoped namespace and synthetic
accounts/data. Deterministic fakes are the default execution dependency.

A separately reviewed workload may use requester-scoped test capacity or an
explicitly budgeted market sandbox only when the owning capability supplies
the authority and receipt contract. That exception cannot expose production
credentials or widen other effects. Any production target, network, store,
read, destructive fault, or write access requires a dedicated change and
host/product-owner approval; none is authorized here. A separately authorized
bounded live observation is scrubbed context and cannot become capacity
evidence unless that dedicated production-test change explicitly permits it.

The implementation must scrub ambient credential/provider variables and auth
homes from load generators, install canary/sentinel values for forbidden
routes, fail before a run if isolation cannot be established, and fail the run
if any provider, billing, market, wallet, or external-effect sentinel is
touched. Evidence and logs contain no secrets or private payloads.

### Dated baseline adapters probe topology instead of freezing "current"

The first baseline fixture targets the isolated shape observed at
`origin/main` `412a876a`. Its expected manifest names one origin, the
shared-volume/process-local coordination class, and no requester-authorized
public executor. Before any run, the adapter must probe and fingerprint the
selected source/deployment/topology and compare it with that dated
expectation. If the selected topology differs, the adapter refuses the
baseline rather than forcing the old facts; a new dated baseline fixture and
reviewed evidence are required. No timeless `current` label may preserve a
mutable deployment fact.

After an accepted review, an exactly matched isolated clone may exercise
control-plane reads/writes with deterministic fakes. The clone retains its own
topology/environment ID. It cannot publish a public-deployment cell unless
capacity-relevant image/configuration, hardware/resource limits,
worker/process contention, gateway/region/network, and storage fingerprints
match through separately safe evidence; otherwise public cells remain
`unknown`.

Scenarios requiring a second origin, a durable shared queue, PostgreSQL
transactions, requester-authorized OS-isolated execution, or production
failover remain `unknown` unless an adapter actually supplies and proves those
features. Fixed shared-auth cloud-worker processes do not satisfy the public
executor dimension and are unavailable to the harness.

### PR #1670 supplies a PostgreSQL adapter to this contract

After both planning changes pass their review gates, the PostgreSQL
control-plane lane implements a `postgres-control-plane` topology adapter using
its own accepted baseline, roles, migration runner, transaction, Realtime,
backup/restore, and stock-PostgreSQL exit behavior. It consumes this change's
scenario catalog, evidence schema, envelope projection, and safety sentinels.

PR #1670 continues to own PostgreSQL authority, migrations, role isolation,
cutover, and database recovery. This change does not copy those requirements.
Conversely, #1670 must not maintain a parallel generic Section 14 catalog or
publish capacity outside the shared evidence validator. Its stricter
PostgreSQL-specific and downstream-domain gates remain additional assertions,
not replacements for the common suite.

### Harness evidence never grants activation or domain authority

A passing packet is evidence consumed by an owning capability's activation
gate. It cannot create identity, visibility, grant, provider, market,
settlement, universe, migration, deployment, or failover authority. The
harness must refuse an invocation whose requested operation is not already
authorized by the selected adapter and domain plug-in.

The planning artifacts themselves grant nothing. Implementation and even the
first isolated dated-baseline run remain blocked on accepted opposite-provider
re-review and any applicable named host/product-owner decision.

## Risks / Trade-offs

- **[Adapters make incomparable runs look comparable]** → fingerprint every
  topology/profile dimension and compare only identical accepted dimensions.
- **[Historical Track J targets become accidental SLOs]** → type threshold
  provenance and require `accepted_gate` before `verified`.
- **[Skipped or unsupported paths turn green]** → map them to `unknown` and
  make required CI unavailability fail visibly.
- **[The harness duplicates domain state machines]** → keep drivers/assertions
  with owners and treat missing owners as unknown.
- **[Load testing leaks credentials or causes effects]** → isolated namespaces,
  scrubbed environments, deterministic fakes, sentinels, and fail-before-run
  safety probes.
- **[The dated baseline is mistaken for public-executor proof]** → represent
  fixed maintainer workers and requester-authorized executors as distinct
  topology classes.
- **[PR #1670 and this lane drift]** → #1670 implements one adapter and depends
  on the shared schema; remove duplicate generic tasks during its accepted
  adaptation.
- **[A fresh result ages into fiction]** → profile-defined freshness and exact
  topology fingerprints downgrade stale evidence to `unknown`.
- **[A load gate pressures unsafe production testing]** → isolated
  production-shaped environments are the default; production testing needs a
  separate explicit authorization.

## Migration Plan

0. Obtain a fresh Claude opposite-provider review of this complete change
   against current source, deployment, active domain changes, and PR #1670.
   Incorporate every required adaptation and obtain accepted re-review. Stop
   before implementation or baseline execution otherwise. Obtain explicit
   host/product-owner decisions only for PLAN or product-boundary changes,
   budgets, production access/effects, first-write/activation, and numerical
   public-launch SLOs.
1. Define versioned adapter, workload-profile, run-packet, and envelope schemas
   plus contract tests that fail on missing topology truth, unknown suppression,
   stale promotion, unsafe effects, and domain-owner bypass.
2. Implement the scenario orchestrator, safety preflight/sentinels, raw evidence
   validator, and deterministic envelope projector using only synthetic
   adapters.
3. Implement the dated `412a876a` single-origin baseline adapter against an
   isolated clone, proving its supported dimensions and explicitly publishing
   unsupported replica/executor paths as `unknown`.
4. Let accepted domain changes register their own drivers and assertions.
   Generic harness tests may not substitute for unimplemented owner suites.
5. Publish the adapter interface and acceptance checklist for the #1670 owner.
   Any #1670 edits occur only in a separately claimed adaptation by that owner;
   the shared harness then consumes its PostgreSQL adapter and evidence while
   preserving the lane's stricter database gates.
6. Approve workload profiles and thresholds separately, run isolated baselines,
   obtain independent review, and publish a freshness-stamped envelope.
7. Add CI/operational consumption only through separately accepted changes.
   Sync the capability and archive this change after implementation and proof.

Before any implementation exists, rollback is deletion/reversion of planning
artifacts only. After implementation, adapters remain dark unless selected by
an accepted test command; removing an adapter or envelope publication cannot
authorize fallback to a different topology.

## Open Questions

- Which durable, access-controlled artifact store owns raw evidence without
  making results or private payloads public?
- Which named authority accepts each workload profile, numerical gate,
  repetition count, freshness window, and fingerprint field? The host/product
  owner accepts public-launch SLOs and budgets unless PLAN assigns a narrower
  owner.
- Which exact configuration inputs form each topology fingerprint?
- What isolated environment can reproduce the current shared-volume topology
  without maintainer auth homes or production data?
- Which accepted test-identity/reset implementation will provision repeatable
  tenants before multi-tenant rendered proof?
- Which #1670 database/Realtime/queue features are present in its first adapter,
  and which must remain `unknown` pending separately owned adapters?
