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

### Requirement: The harness composes but never replaces domain-owned proofs
The harness SHALL consume accepted workload drivers and assertions from the
owners of live MCP/SSE/session behavior, commons/discovery/collaboration,
webhook/external ingress, export/GitHub projection, storage/retention,
moderation/abuse, operator requests, paid-market workflow, live-price
discovery, universe authority, identity/reset, visibility, distributed
execution, credential/provider routing, and uptime behavior. It SHALL NOT
define, weaken, synthesize, or bypass those domains' sessions, grants,
identities, visibility decisions, transitions, prices, claims, settlements,
provider routes, executor authority, migrations, effects, moderation,
retention, activation gates, or recovery authority.

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

### Requirement: The verified envelope is a conservative freshness-stamped projection
The publisher SHALL derive each capacity-envelope cell deterministically as
`verified`, `failed`, or `unknown` for one exact topology, profile, scenario,
fault dimension, and evidence freshness window. `verified` SHALL require an
accepted gate, applicable passing evidence, the profile's successful repetition
count, complete raw evidence, unchanged fingerprints, and required independent
review. Expired or mismatched evidence SHALL make the current cell `unknown`
while retaining its historical result and reason.

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
