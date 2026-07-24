## ADDED Requirements

### Requirement: Capacity runs declare one complete topology adapter
The harness SHALL execute every capacity or isolation run through one
versioned topology adapter whose manifest identifies the exact source, image,
configuration, region, gateway replicas, authority stores, queues, realtime
transport, pools, executor classes, credential/provider availability class,
fault controls, isolated namespace, and unsupported operations. It SHALL
validate claimed features with preflight probes and SHALL refuse an incomplete,
unisolated, or internally contradictory manifest.

#### Scenario: Adapter omits an authority store
- **WHEN** an adapter cannot identify the authority store used by a requested write
- **THEN** the run is refused before load begins
- **AND** no default local, production, or vendor store is inferred

#### Scenario: Unsupported topology feature stays explicit
- **WHEN** a scenario requires a second origin or durable queue that the adapter does not provide
- **THEN** the affected result is recorded as `unknown`
- **AND** the operation is neither skipped as success nor simulated by changing scenario meaning

### Requirement: Dated baseline adapters probe and preserve observed topology
Every baseline adapter SHALL name the dated source/deployment observation it
expects, probe and fingerprint the topology actually selected at run time, and
refuse the baseline when those facts differ. A mutable `current` label SHALL
NOT force a future deployment to report historical topology facts. The
baseline fixture for `origin/main` `412a876a` SHALL expect one MCP origin over
one shared host-volume/process-local coordination class, with
requester-authorized public execution and a usable OS-isolating
`SandboxBackend` unavailable. Source-defined fixed cloud-worker processes
sharing provider auth homes SHALL NOT be classified as requester-authorized
executors or eligible load-test capacity without separate authority evidence.

#### Scenario: Dated baseline reports no public executor
- **WHEN** the selected topology probes match the dated `412a876a` baseline fixture
- **THEN** requester-authorized and OS-isolated executor dimensions are unavailable
- **AND** their capacity-envelope cells are `unknown` unless a later adapter actually supplies and proves them

#### Scenario: Selected topology changed after the observation
- **WHEN** source, deployment, configuration, origin count, authority store, queue, executor, or another topology probe differs from the dated baseline fixture
- **THEN** the adapter refuses to run under that baseline identity
- **AND** the harness requires a new dated fixture and reviewed evidence rather than publishing the old topology as current

#### Scenario: Shared-auth workers are discovered
- **WHEN** deployment inspection finds fixed workers sharing provider auth homes
- **THEN** the manifest records their existence as a separate ineligible topology fact
- **AND** the harness neither invokes them nor counts them as public capacity

### Requirement: Scenario profiles distinguish targets from accepted gates
The harness SHALL require a versioned workload profile that binds tenant and
request mix, dataset size, payload distribution, hot-key distribution,
steady/burst/saturation durations, fault schedule, thresholds, repetition
rule, and freshness window. Every numerical threshold SHALL be labeled
`historical_target`, `unapproved_hypothesis`, or `accepted_gate`; only an
`accepted_gate` SHALL participate in a verified-envelope decision.

#### Scenario: Legacy Track J number is supplied
- **WHEN** a profile imports a Section 14 or Track J target that has not been freshly accepted
- **THEN** the threshold remains `historical_target`
- **AND** passing it does not produce a `verified` capacity cell

#### Scenario: Profile lacks an approved gate
- **WHEN** an otherwise successful run has no `accepted_gate` for a reported dimension
- **THEN** that dimension is `unknown`
- **AND** raw measurements remain available as non-authoritative baseline evidence

### Requirement: Historical Track J candidates remain source scoped
The workload-profile catalog SHALL register the historical Section 14 / Track J
S1-S7 and S11-S14 scenarios as source-scoped `historical_target` candidates,
not accepted gates. Each candidate SHALL carry its source document, source
revision, source-local scenario ID, canonical semantic name, workload shape,
and original threshold provenance. Conflicting historical uses of the same
bare `S#` identifier SHALL remain distinct and SHALL NOT be silently aliased.
The candidate set SHALL cover subscriber fan-out, bid/claim storms, cascade or
discovery read storms, heartbeat steady state, hot-node write contention,
cold-start end-to-end, auto-healing/recovery, parallel request fan-out,
autoresearch budget fan-out, evaluator-cache deduplication, and evaluator-chain
early termination.

#### Scenario: Historical scenario number has conflicting meanings
- **WHEN** two source documents assign different workloads to the same bare `S#`
- **THEN** the catalog keeps separate source-scoped candidate IDs and records the conflict
- **AND** neither candidate becomes an `accepted_gate` until a named authority accepts one exact semantic profile

#### Scenario: Historical candidate passes without fresh acceptance
- **WHEN** a run passes an unchanged S1-S7 or S11-S14 historical candidate
- **THEN** its measurements remain historical baseline evidence
- **AND** no current capacity or complete-platform readiness cell becomes `verified`

### Requirement: The harness composes but never replaces domain-owned proofs
The harness SHALL consume accepted workload drivers and assertions from the
owners of live MCP/SSE/session behavior, commons/discovery/collaboration,
webhook/external ingress, export/GitHub projection, storage/retention,
moderation/abuse, operator requests, paid-market workflow, live-price
discovery, universe authority, identity/reset, visibility, distributed
execution, credential/provider routing, graph and long-running workflow
execution, node authoring/remix, goals/gates, learning/retrieval/evaluation,
autoresearch, organization/shared-universe administration, connector and
Zapier-style automation, inference, training/fine-tuning, model serving, other
published compute capability classes, and uptime behavior. It SHALL NOT define,
weaken, synthesize, or bypass those domains' sessions, grants, identities,
visibility decisions, transitions, prices, claims, settlements, provider
routes, executor authority, migrations, effects, moderation, retention,
activation gates, or recovery authority.

#### Scenario: Paid-market owner is unavailable
- **WHEN** the generic mixed workload requests paid-market settlement but no accepted paid-market driver and assertion suite exists
- **THEN** the paid-market path is `unknown`
- **AND** the harness does not create a synthetic settlement and call it domain proof

#### Scenario: Domain assertion is stricter than the common gate
- **WHEN** a domain-owned suite imposes an additional conservation, authority, or latency requirement
- **THEN** that requirement remains necessary for the domain result
- **AND** a passing generic scenario cannot override it

#### Scenario: Complete-system owner has no accepted driver
- **WHEN** MCP connection, collaboration, webhook, export, storage-growth, or moderation/abuse coverage lacks an accepted owner-published driver and assertion suite
- **THEN** that domain's capacity and isolation cells remain `unknown`
- **AND** the harness does not implement the missing state machine or omit the gap from the complete-system envelope

### Requirement: Domain plug-ins expose a versioned owner ABI
Every domain plug-in SHALL publish a manifest that pins its capability and
owner, canonical spec revision, implementation SHA, plug-in ABI version,
supported scenario and lifecycle-stage IDs, assertion IDs and result schema,
permitted artifact kinds, required trace/correlation fields, required topology
features, authority and effect classes, setup and run-scoped teardown contract,
workload-driver entry point, independent observer/oracle entry point, required
metrics and evidence schema, zero-capacity semantics, privacy classification,
source/dependency fingerprints, and compatible harness/adapter versions. The
harness SHALL reject an incomplete, incompatible, unowned, unpinned,
stage-ambiguous, or fingerprint-drifted plug-in. Driver return values alone
SHALL NOT satisfy durable-state, conservation, receipt, or isolation
assertions.

#### Scenario: Driver reports success without an independent oracle
- **WHEN** a domain driver returns success but its accepted observer cannot prove the required durable state, conservation, receipt, or isolation invariant
- **THEN** the domain cell is `failed` or `unknown` according to applicability
- **AND** the driver response is not promoted as proof

#### Scenario: Plug-in revision drifts after a passing run
- **WHEN** the owner spec, implementation SHA, ABI, or compatibility range changes
- **THEN** prior cells that depend on that plug-in become `unknown`
- **AND** the historical packet remains attributable to its original manifest

### Requirement: Path envelopes and complete-platform readiness are distinct
The publisher SHALL maintain a fixed, versioned required-readiness matrix for
every enabled Forever Rule surface and every public capability class. A
path-level envelope MAY report independently `verified`, `failed`, or `unknown`
cells, but the aggregate complete-platform readiness result SHALL NOT be green
while any required applicable cell is `failed` or `unknown`. Workload profiles
SHALL NOT reclassify a required public surface as optional. A capability that
is intentionally not applicable SHALL require an owner-published applicability
decision distinct from `unknown`.

#### Scenario: Partial path evidence is green
- **WHEN** MCP admission cells are verified but required execution, collaboration, market, moderation, storage, or recovery cells are failed or unknown
- **THEN** those verified path cells remain visible
- **AND** complete-platform readiness remains non-green with the exact missing or failed cells listed

#### Scenario: Profile omits a required surface
- **WHEN** a selected profile omits a required applicable readiness-matrix cell
- **THEN** the omitted cell is `unknown`
- **AND** the profile cannot publish a green complete-platform result

### Requirement: The common suite covers capacity, isolation, and recovery dimensions
The harness SHALL support versioned scenarios for steady load, burst,
saturation, topology failure and recovery, noisy-neighbor pressure,
cross-tenant isolation, hot-key contention, zero-host mode, reconnect/replay,
backlog recovery, and mixed execution-authority isolation. Each executed
scenario SHALL report both correctness and resource behavior; a latency-only
or throughput-only result SHALL be incomplete.

#### Scenario: Noisy tenant saturates its allowance
- **WHEN** one synthetic tenant reaches its accepted stream, queue, fan-out, or write allowance while ordinary tenants continue
- **THEN** the packet records per-tenant throughput, wait, and error distributions plus dominant-tenant share
- **AND** any cross-tenant disclosure or accepted-SLO violation fails the applicable gate

#### Scenario: All requester-authorized executors are offline
- **WHEN** a zero-host scenario admits work that requires execution
- **THEN** authoring/read behavior is measured separately from executable work
- **AND** executable work remains truthfully pending, held, unavailable, or unknown according to its domain owner with zero maintainer/provider/market fallback

#### Scenario: Topology fails during a measured run
- **WHEN** an adapter-supported origin, connection, queue, worker, or authority fault is injected at a declared boundary
- **THEN** the packet records loss, duplication, backlog, retry, reconciliation, and recovery timing
- **AND** an unsupported fault is `unknown` rather than inferred from a successful steady run

### Requirement: Execution-path capacity cells are stage typed
Every request-capacity packet SHALL represent admission, durable enqueue and
epoch assignment, internal scheduling claim/heartbeat/expiry/reclaim,
provider/executor eligibility and authority resolution, signed external
execution lease, execution start/progress/cancellation/completion, delivery,
and settlement/receipt as separate stage-typed cells. Evidence SHALL correlate
request ID, task ID, epoch, attempt ID, internal scheduling lease, external
execution lease, and receipt IDs without treating one identifier or stage as
another. A pass at an earlier stage SHALL NOT promote a later stage.

#### Scenario: Canonical admission succeeds without execution authority
- **WHEN** a canonical request admission and admission receipt succeed but no requester-authorized provider, executor, or market grant exists
- **THEN** admission may be `verified` while authority, external execution, completion, and settlement remain `unknown` or the domain owner's truthful unavailable state
- **AND** no maintainer credential, quota, worker, provider, market, or hardware fallback occurs

#### Scenario: Epoch-2 internal lease is acquired
- **WHEN** the epoch-2 queue adapter grants an internal scheduling claim or lease
- **THEN** only the scheduling-claim stage may be proved
- **AND** that lease is not classified as a signed B2/provider/market execution lease and cannot prove execution, completion, delivery, or settlement

#### Scenario: Later stage lacks correlated evidence
- **WHEN** a packet cannot correlate a claimed execution, completion, delivery, or settlement event to the required prior authority and lease receipts
- **THEN** that stage is `unknown` or `failed` according to the accepted owner assertion
- **AND** evidence from another stage cannot fill the gap

### Requirement: Isolation proof covers every authority and storage boundary
Each accepted isolation profile SHALL declare and exercise a positive/negative
matrix across account, user, organization, universe, node, branch, goal, run,
daemon/worker, artifact, session, Realtime channel, queue row, scheduling
lease, external execution lease, result, wallet or ledger, billing/cost
attribution, provider credential, market grant, cache, idempotency/replay key,
blob, log/event, evidence namespace, network/region, and topology boundaries.
Every applicable pair SHALL have explicit disclosure, mutation, authority,
cost-attribution, and resource-starvation assertions. The matrix SHALL test RLS
and channel isolation, ownership and replay collisions, tenant-specific BYOC
custody, noisy-neighbor resource fairness, scoped teardown, and residue absence
across every participating store.

#### Scenario: Tenant credential or lease crosses scope
- **WHEN** tenant A's credential, grant, queue row, lease, result, wallet entry, or private event is observable or usable by tenant B
- **THEN** the applicable isolation gate fails
- **AND** no throughput or latency success can mask the failure

#### Scenario: Scoped teardown leaves residue
- **WHEN** a run-scoped teardown completes but its rows, blobs, cache entries, channels, logs, events, leases, or evidence remain visible to a later namespace
- **THEN** teardown and isolation cells fail
- **AND** the affected run cannot publish verified capacity

### Requirement: Every run emits complete immutable evidence
The harness SHALL emit a schema-versioned evidence packet containing run,
scenario, profile, adapter, topology and environment fingerprints; exact
commands and timestamps; accepted and historical threshold provenance; raw
artifact locations and digests; request/transaction/stream counts;
p50/p95/p99/max and throughput; errors, timeouts, retries, conflicts,
deadlocks, disconnects, duplicates and loss; resource and pool/queue occupancy;
tenant fairness; catch-up and recovery timings; unsupported dimensions; safety
sentinel outcomes; repetition count; caveats; and independent-review metadata.
Missing required telemetry or raw evidence SHALL invalidate the affected
capacity claim.

#### Scenario: Percentile summary lacks raw evidence
- **WHEN** a run reports p95 and p99 without the raw sample artifact and digest required by its profile
- **THEN** the affected result cannot become `verified`
- **AND** the packet identifies the missing evidence rather than accepting the summary

#### Scenario: Required test dependency is unavailable
- **WHEN** a required database, queue, realtime service, identity fixture, or adapter probe cannot start
- **THEN** the run fails visibly or records the affected optional dimension as `unknown` according to the accepted profile
- **AND** it never reports a skipped pass

### Requirement: Load measurements are scientifically valid
Every performance profile SHALL declare open-loop offered-load and/or
closed-loop concurrency semantics, arrival schedule, generator count and
placement, minimum generator headroom, required full concurrent population,
concurrent principals/sessions/streams, host/executor and capability mix,
payload and cache/dataset state, retry/timeout/error accounting, warm-up and
measurement windows, and saturation search. The evidence SHALL include
coordinated-omission correction where applicable, load-generator
CPU/memory/network/event-loop health, clock synchronization and error bounds,
achieved throughput versus offered load, backlog growth and drain slope,
repetition variance or confidence, and the rule used to establish steady
state. A saturated generator, unbounded clock error, omitted offered load,
uncorrected coordinated omission, population drop, hidden client queuing,
telemetry loss, uncontrolled background contention, or offered-versus-
completed denominator drift SHALL invalidate affected latency and throughput
cells.

#### Scenario: Closed-loop result hides queueing delay
- **WHEN** a closed-loop run reports favorable latency while offered load, queue age, or coordinated-omission-corrected latency is absent
- **THEN** the affected latency and saturation cells are `unknown`
- **AND** the closed-loop samples remain non-authoritative diagnostic evidence

#### Scenario: Load generator becomes the bottleneck
- **WHEN** a load generator exceeds its accepted resource or scheduling-health gate
- **THEN** the affected capacity cells are invalidated
- **AND** the system under test is not blamed or credited from that run

### Requirement: Evidence reports stage and user-perceived service metrics
Applicable packets SHALL report admission latency, enqueue-to-claim and
capacity-available-to-claim time, queue-age and starvation distributions by
tenant/priority/capability/price class, authority-resolution time,
executor-start time, MCP/SSE first-event latency and inter-event gap,
reconnect catch-up and cancellation cleanup, execution/completion/delivery/
settlement latency, and recovery RTO/RPO plus backlog drain. They SHALL also
report the required and achieved active concurrent population, unique users,
per-user and per-tenant throughput/wait/error/cost distributions,
dominant-user and dominant-tenant share, and budget/rate-limit outcomes. Each
metric SHALL use the full applicable denominator and retain timeout,
cancellation, failure, and uncompleted attempts rather than measuring
successful survivors only.

#### Scenario: Percentile excludes uncompleted requests
- **WHEN** a stage percentile omits timed-out, cancelled, failed, or still-pending attempts from its declared denominator
- **THEN** that metric cannot become `verified`
- **AND** the packet reports the complete outcome distribution and denominator mismatch

### Requirement: The verified envelope is a conservative freshness-stamped projection
The publisher SHALL derive each capacity-envelope cell deterministically as
`verified`, `failed`, or `unknown` for one exact topology, profile, scenario,
lifecycle stage, actor/scope boundary, supply-provenance class, fault
dimension, and evidence freshness window. `verified` SHALL require an accepted
gate, applicable passing evidence, the profile's successful repetition count,
complete raw evidence, unchanged fingerprints, and required independent
review. Cells for the same request at different stages, scopes, or supply
classes SHALL remain distinct. Expired or mismatched evidence SHALL make the
current cell `unknown` while retaining its historical result and reason.

#### Scenario: Topology changes after a passing run
- **WHEN** the image, configuration, replica count, store, queue, pool, executor class, or other fingerprinted topology input changes
- **THEN** the prior current cell becomes `unknown`
- **AND** the historical result remains labeled with its original topology and date

#### Scenario: Isolated clone differs from the public deployment
- **WHEN** an isolated clone lacks an exact match for capacity-relevant public image/configuration, hardware and resource limits, worker/process contention, gateway/region/network, or storage fingerprints
- **THEN** its result is published only under the isolated-clone topology identity
- **AND** every corresponding public-deployment capacity cell remains `unknown`

#### Scenario: Vendor quota exceeds measured capacity
- **WHEN** a vendor advertises a larger connection or throughput limit than TinyAssets has proved
- **THEN** the published envelope remains at the measured reviewed lower bound
- **AND** it does not extrapolate to the vendor limit or a DAU claim

#### Scenario: Applicable accepted gate fails
- **WHEN** complete current evidence violates an accepted correctness, isolation, recovery, or resource gate
- **THEN** the exact cell is `failed`
- **AND** unrelated or unexecuted paths remain separately `unknown`

### Requirement: Runs deny production access, effects, and privileged resources by default
The harness SHALL begin with production target/network/store/read access,
production mutation, destructive production fault injection, provider/model
invocation, market purchase, payment, wallet, external effect,
founder/maintainer credentials, auth homes, quota, accounts, and hardware
disabled. It SHALL require an isolated run-scoped namespace, synthetic data,
scrubbed load-generator environments, and forbidden-route sentinels. It SHALL
fail before load when isolation cannot be established and fail the run when a
sentinel is touched. Evidence and logs SHALL contain no secret or private
payload. A separately authorized bounded live observation SHALL be scrubbed
and SHALL remain ineligible as capacity evidence unless a dedicated
production-test change explicitly authorizes the exact workload and evidence
use.

#### Scenario: Ambient maintainer credential is present
- **WHEN** safety preflight detects a maintainer provider environment variable, mounted auth home, token, or billing route in a load generator
- **THEN** the run is refused before any scenario request
- **AND** the credential value is neither read into evidence nor logged

#### Scenario: Fixture attempts an external effect
- **WHEN** a workload reaches a real provider, market purchase, payment, wallet, production write, or other forbidden effect
- **THEN** the sentinel blocks the call and fails the run
- **AND** no successful capacity claim is published from that run

#### Scenario: Runner targets production for a read-only probe
- **WHEN** a run attempts production endpoint, network, store, or read access without a dedicated production-test authorization
- **THEN** safety preflight refuses the run before the first request
- **AND** a separately authorized bounded observation cannot become capacity evidence by itself

#### Scenario: Separately authorized test capacity is used
- **WHEN** a later accepted profile uses requester-scoped test capacity or an explicitly budgeted market sandbox
- **THEN** the owning capability's authority and receipt contract binds every attempt
- **AND** the exception does not enable production credentials, maintainer resources, or unrelated effects

### Requirement: BYOC and market capacity prove provenance without platform subsidy
BYOC and market profiles SHALL prove for every attempt the requester or market
grant, credential-custody class, allowed-provider ceiling, capability class,
budget and expiry state, usage/cost attribution, provider-attempt receipt, and
completion or failure receipt. Required profiles SHALL include zero BYOC and
zero market grants, many tenants with distinct BYOC credentials, revoked or
expired credentials, exhausted budgets and provider quotas, and separately
authorized market execution. Evidence SHALL prove that founder/maintainer
credentials, subscription limits, quota, workers, accounts, funds, and
hardware were neither selected nor consumed.

#### Scenario: No requester-authorized capacity exists
- **WHEN** admitted work has no active BYOC credential, accepted market grant, or requester-authorized executor
- **THEN** the work remains truthfully queued, held, unavailable, or unknown according to its owner
- **AND** all maintainer usage and cost sentinels remain unchanged

#### Scenario: Usage is charged to the wrong authority
- **WHEN** a provider attempt or market execution lacks matching requester/market provenance and cost attribution
- **THEN** BYOC/market execution and completion cells fail
- **AND** an otherwise successful provider response cannot verify capacity

### Requirement: Dynamic compute supply is not a static platform-capacity claim
Market and BYOC supply cells SHALL bind a freshness-stamped supply snapshot to
capability class, model or workload, inference/training/fine-tuning/serving
mode, hardware/resource class, region, unit and currency, price ceiling,
availability window, authority class, and executable receipt contract. It
SHALL measure offered depth plus eligible, reserved, started, delivered, and
settled quantities; fill rate, time-to-match, slippage, expiry, and failure
distributions. The publisher SHALL report control-plane admission capacity,
schedulable capacity, currently authorized executable supply, active execution
capacity, and completed/settled throughput separately. A stale quote,
advertised host, queue claim, vendor quota, or live-price observation SHALL NOT
become executable supply or end-to-end capacity.

#### Scenario: Live price exists without executable supply
- **WHEN** a fresh quote or price index exists but no eligible authorized provider/executor can accept the workload
- **THEN** price discovery may be verified while executable supply and completion capacity remain `unknown` or unavailable
- **AND** the quote does not authorize purchase or execution

#### Scenario: Supply snapshot expires
- **WHEN** the snapshot, quote, grant, availability window, or capability match expires
- **THEN** the current executable-supply cell becomes `unknown`
- **AND** its historical observation remains labeled with its original time and authority

### Requirement: PostgreSQL capacity proof consumes the shared adapter contract
The future PostgreSQL control-plane implementation SHALL provide a
PostgreSQL topology adapter that consumes this capability's scenario catalog,
workload profiles, evidence schema, safety sentinels, and envelope projection.
It SHALL retain ownership of PostgreSQL baseline, migrations, roles,
transactions, Realtime integration, backup/restore, stock-PostgreSQL exit, and
cutover, and SHALL NOT publish a parallel generic Section 14 envelope.

#### Scenario: PR 1670 runs PostgreSQL load proof
- **WHEN** the accepted PostgreSQL lane executes its production-shaped capacity suite
- **THEN** it selects its PostgreSQL adapter through the shared harness
- **AND** its stricter database/domain assertions augment rather than duplicate or replace the common evidence contract

#### Scenario: PostgreSQL adapter lacks a future queue
- **WHEN** the PostgreSQL topology does not yet include a durable queue required by one scenario
- **THEN** the queue-dependent cell remains `unknown`
- **AND** database success is not presented as complete control-plane capacity

### Requirement: Planning and evidence grant no runtime authority
The planning artifacts, harness, adapter, evidence packet, and passing envelope SHALL NOT themselves authorize implementation, baseline execution, production
access, deployment, migration, activation, identity, visibility, provider,
executor, universe, market, payment, or failover actions. Harness
implementation and the first baseline execution SHALL remain blocked until a
fresh Claude opposite-provider verdict is accepted. PLAN or product-boundary
changes, budgets, production access/effects, first-write/activation, and
numerical public-launch SLOs SHALL require an explicit host/product-owner
decision; factual/spec corrections SHALL close through accepted re-review.
Later operations SHALL still require their owning capabilities' normal
approvals.

#### Scenario: Planning artifacts land before review
- **WHEN** this proposal, design, spec, and unchecked tasks are merged before the required review is accepted
- **THEN** no harness code, baseline run, production probe, or infrastructure mutation is authorized
- **AND** every implementation task remains pending behind fresh Claude review and any applicable named host/product-owner decision

#### Scenario: Envelope passes without an owner activation gate
- **WHEN** a capacity packet passes but the affected domain or topology owner has not authorized activation
- **THEN** the system remains dark or in its prior state
- **AND** the harness cannot promote or activate it
