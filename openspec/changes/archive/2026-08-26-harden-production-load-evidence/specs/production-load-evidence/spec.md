## ADDED Requirements

### Requirement: Scenario ownership remains capability-local
The system SHALL maintain a versioned production-load scenario registry in which each entry names its owning capability, scenario identifier and version, applicability, required or optional status, classification justification, substrate requirements, adapter reference, invariant-oracle references, fault declaration, and threshold references. The shared evidence capability SHALL NOT redefine a capability owner's workload mix, population, threshold values, fault choices, adapter behavior, or invariant predicates. Changing required/optional status or applicability SHALL publish a new scenario version and record a justification.

#### Scenario: Capability registers a load scenario
- **WHEN** a capability owner adds a §14 scenario
- **THEN** the registry records the owner and evidence references without moving the scenario's workload or threshold semantics into the shared contract

#### Scenario: Breaking scenario semantics change
- **WHEN** a capability owner changes a population, threshold, invariant, or other result-defining behavior incompatibly
- **THEN** the owner publishes a new scenario version and historical runs retain their original interpretation

#### Scenario: Required scenario is downgraded to optional
- **WHEN** a capability owner changes a required scenario to optional or marks an applicable scenario inapplicable
- **THEN** the owner publishes a new scenario version with a recorded justification and historical required rollups retain the prior classification

### Requirement: Run manifests are immutable and content-addressed
The system SHALL write each completed run manifest once in canonical content-addressed form and SHALL record the schema version, run identifier, scenario identifier and version, owning capability, terminal verdict and reason, timestamps, exact commands, deterministic seed when applicable, operator identity, environment fingerprint, artifact digests, oracle outcomes, and any superseded run identifier.

#### Scenario: Completed evidence is corrected
- **WHEN** an operator discovers an error in a completed run manifest
- **THEN** the system preserves the original and writes a new manifest that references the original through `supersedes`

#### Scenario: Raw artifact is modified
- **WHEN** a raw metric, trace, timeline, or reconciliation artifact no longer matches its recorded digest
- **THEN** the validator rejects the manifest as conformant production evidence

### Requirement: Verdict vocabulary and rollup are deterministic
The system SHALL reuse the `uptime-and-alarms` terminal vocabulary `passed`, `failed`, and `not_run` for §14 scenario verdicts and SHALL NOT define a competing enum. Over required and applicable scenarios, any `failed` SHALL yield `failed`; otherwise any `not_run` SHALL yield `not_run`; otherwise the rollup SHALL be `passed`. An empty required-and-applicable set SHALL yield `not_run`. Optional or inapplicable entries SHALL NOT alter that rollup. Aggregate output SHALL retain each constituent scenario ID, verdict, substrate class, and manifest digest. A required rollup of `failed` or `not_run` SHALL NOT satisfy a Forever Rule §14 done-claim.

#### Scenario: Failure and unavailable substrate coexist
- **WHEN** one required applicable scenario is `failed` and another is `not_run`
- **THEN** the aggregate verdict is `failed`

#### Scenario: Required scenario did not run
- **WHEN** no required applicable scenario failed and at least one is `not_run`
- **THEN** the aggregate verdict is `not_run`

#### Scenario: Optional future scenario is unavailable
- **WHEN** every required applicable scenario passed and only an optional scenario is `not_run`
- **THEN** the aggregate verdict is `passed`

#### Scenario: Required set is empty
- **WHEN** a registry selection contains no required and applicable scenarios
- **THEN** the aggregate verdict is `not_run` rather than vacuously `passed`

#### Scenario: Mock-sourced failure is aggregated
- **WHEN** a required mock execution proves an invariant violation
- **THEN** the aggregate is `failed` and identifies that scenario's mock substrate and manifest digest

#### Scenario: Required rollup is not green
- **WHEN** a required rollup is `failed` or `not_run`
- **THEN** the owning feature cannot claim its §14 obligation is complete

### Requirement: Protocol conformance is distinct from scenario outcome
The system SHALL report evidence-protocol conformance independently from production-load scenario verdicts and SHALL NOT convert a conformant manifest or validator test into a passed capacity scenario.

#### Scenario: Validator passes before a production substrate exists
- **WHEN** the protocol conformance suite passes but a required Realtime scenario lacks its configured substrate
- **THEN** protocol conformance is `passed` and the Realtime scenario remains `not_run`

### Requirement: Substrate classification prevents false production proof
The system SHALL classify every run substrate as `real`, `shaped`, or `mock`. `real` SHALL mean the deployed service or an isolated environment satisfying the scenario owner's predeclared equivalence profile for all relevant released artifacts, engines and versions, service tier, topology, configuration, capacity envelope, and limits. `shaped` SHALL mean at least one relevant equivalence condition is scaled, omitted, or substituted. `mock` SHALL mean a production implementation is replaced by a simulator, stub, or in-memory stand-in. A shaped or mock execution of a production-evidence scenario MUST NOT emit `passed`; it SHALL emit `failed` when it proves a required invariant violation or otherwise `not_run` with at least one machine-readable blocking-substrate code.

#### Scenario: Mock generator completes within thresholds
- **WHEN** a production-evidence scenario runs only against a mock and observes no violation
- **THEN** its verdict is `not_run` with `substrate_absent` or a more specific blocking-substrate code

#### Scenario: Shaped environment completes within thresholds
- **WHEN** a production-evidence scenario runs in an environment that scales, omits, or substitutes a relevant declared equivalence condition and observes no violation
- **THEN** its verdict is `not_run` with the shaped condition identified in its blocking-substrate evidence

#### Scenario: Mock exposes an invariant defect
- **WHEN** a mock execution produces evidence that a required invariant was violated
- **THEN** the scenario may report `failed` and MUST retain the evidence showing the violation

#### Scenario: Not-run result is presented
- **WHEN** a scenario emits `not_run`
- **THEN** the result includes blocking-substrate codes and is never described as absence of risk or production readiness

### Requirement: Environment fingerprints make runs comparable
The system SHALL fingerprint the source SHA, image digest, configuration and rollout identity, topology, region, database engine/version/pool settings, queue or Realtime tier and configured connection envelope, participating compute resources, relevant network facts, clock-sync evidence, and substrate class for each production-load run without recording secret values or private payloads.

#### Scenario: Required fingerprint data is missing
- **WHEN** a scenario cannot record a required environment fact needed to interpret its result
- **THEN** it reports `not_run` unless available evidence already proves a required invariant violation

#### Scenario: Fingerprint would expose a secret
- **WHEN** an environment field contains credential material
- **THEN** the manifest records a safe identifier or digest and excludes the secret value

### Requirement: Metrics and traces are independently recomputable
The system SHALL retain raw or content-addressed source evidence sufficient to recompute operation counts and p50, p95, p99, and maximum latency, including declared populations, denominators, units, and exact commands. A percentile summary without its underlying denominator and evidence SHALL NOT satisfy production-load proof. Raw metrics and traces SHALL exclude user-authored content and SHALL pseudonymize actor, account, universe, and node identifiers.

#### Scenario: Reviewer recomputes reported latency
- **WHEN** a reviewer reads a conformant run manifest and its artifacts
- **THEN** the reviewer can reproduce the reported counts and percentile values from the recorded raw evidence

#### Scenario: Canonical population is incomplete
- **WHEN** admitted work is missing from the result denominator without a capability-declared expected classification
- **THEN** the scenario fails rather than reporting percentiles over only the surviving population

#### Scenario: Raw trace contains user content
- **WHEN** a raw event would include a prompt, page body, or other user-authored payload
- **THEN** the retained load artifact omits that content while preserving pseudonymous correlation needed for recomputation

### Requirement: Invariant-oracle outcomes are explicit
The system SHALL evaluate named, versioned capability-owned invariant predicates over recorded evidence and SHALL return `held`, `violated`, or `unevaluable` for each predicate. `unevaluable` MUST NOT count as `held`, and any violated required invariant SHALL make the scenario `failed`.

#### Scenario: Required invariant cannot be evaluated
- **WHEN** evidence is insufficient to evaluate a required invariant and no other required invariant is violated
- **THEN** the scenario is `not_run`

#### Scenario: Latency passes but data is duplicated
- **WHEN** latency thresholds pass and a required no-duplicate invariant is `violated`
- **THEN** the scenario is `failed`

### Requirement: Declared faults produce a verifiable timeline
The system SHALL record ordered fault events containing time, fault kind, target, injected or observed state, and observed recovery time for scenarios that declare fault injection. A required declared fault with an empty or unverifiable timeline SHALL make the scenario `not_run`.

#### Scenario: Fault gate cannot go red
- **WHEN** a scenario declares a gateway outage but records no verifiable injection or observation
- **THEN** the scenario is `not_run` rather than `passed`

#### Scenario: Recovery exceeds an owner threshold
- **WHEN** a declared fault is injected and recovery violates the capability owner's threshold
- **THEN** the scenario is `failed`

### Requirement: Reconciliation accounts for terminal effects
The system SHALL record capability-applicable admitted, committed, claimed, delivered, and settled counts and SHALL classify every discrepancy as `expected`, `loss`, `duplicate`, or `unexplained`. A discrepancy that violates a capability-owned required invariant SHALL make the scenario `failed`. Reconciliation and diagnostic artifacts SHALL exclude user-authored content and SHALL pseudonymize actor, account, universe, and node identifiers.

#### Scenario: Terminal effect is unexplained
- **WHEN** reconciliation finds admitted work with no expected terminal classification
- **THEN** the scenario is `failed` and retains the affected identifiers in a non-secret diagnostic artifact

#### Scenario: Expected rejection is reconciled
- **WHEN** a capability owner declares and proves a rejected operation as an expected terminal class
- **THEN** the rejection does not count as loss

### Requirement: Live public-surface runs are authorized and isolated
The system SHALL require a production-load run against a live public surface to record explicit host authorization, a declared traffic envelope, blast radius, abort criteria, uptime-canary coordination, isolated test identities, and a cleanup path. Such a run SHALL NOT invoke a model/provider or consume maintainer quota.

#### Scenario: Connector baseline is authorized
- **WHEN** an operator runs a baseline against canonical `/mcp`
- **THEN** the manifest records authorization, bounded traffic and abort criteria, isolated identity scope, cleanup, and canary coordination

#### Scenario: Candidate flow would invoke a provider
- **WHEN** a proposed live load path would call a model/provider or consume maintainer quota
- **THEN** the production scenario is `not_run` until a provider-free adapter or separately authorized non-maintainer funding path exists

#### Scenario: Test identity cleanup fails
- **WHEN** a live run cannot prove cleanup of its isolated test identities and artifacts
- **THEN** the scenario is `failed` and subsequent live runs remain unauthorized until cleanup is restored

### Requirement: Baseline comparisons are predeclared and same-environment
The system SHALL require comparative scenarios to reference a compatible same-environment baseline run and to declare regression bounds before execution. Missing or incompatible required baselines SHALL yield `not_run`, and baseline regression measurements SHALL remain distinct from absolute §14 thresholds.

#### Scenario: Baseline is missing
- **WHEN** a scenario requires a comparative latency bound but provides no compatible baseline run
- **THEN** the scenario is `not_run`

#### Scenario: Baseline passes but absolute target fails
- **WHEN** a run stays within its allowed baseline regression and violates an absolute capability-owned §14 threshold
- **THEN** the scenario is `failed`

### Requirement: Current-system baseline precedes distributed capacity claims
The system SHALL establish a real baseline packet for the current single-origin connector/MCP and storage path before reporting later distributed capacity scenarios as passed. PostgreSQL, configured Realtime, fleet-storm, settlement-replay, and failure-injection scenarios SHALL remain `not_run` until their declared real substrates or real-equivalent isolated environments exist.

#### Scenario: Connector-first baseline runs on current deployment
- **WHEN** the canonical connector/MCP path and current storage substrate are available
- **THEN** the system can record their real measured envelope without claiming untested distributed capacity

#### Scenario: Distributed substrate is absent
- **WHEN** a registry entry requires a real PostgreSQL outbox or configured Realtime connection envelope that is not available
- **THEN** the scenario reports `not_run` with the applicable blocking-substrate code
