## ADDED Requirements

### Requirement: Authoring sessions are authenticated, owner-scoped drafts
The system SHALL let an authenticated user begin an authoring session from exactly one of a natural-language sketch, an accessible published node/evaluator version, or an unexpired prior draft. Each session SHALL have an immutable owner, explicit artifact kind, base/parent lineage, status, creation/update timestamps, and retention boundary. Reads and mutations SHALL fail closed for non-owners; resuming from a published artifact SHALL copy only the definition and permitted public provenance, never another user's execution data, credentials, or instance state.

#### Scenario: User starts from a natural-language sketch
- **WHEN** an authenticated user starts a node draft from a non-empty sketch and no other seed
- **THEN** the system creates an owner-scoped active session preserving that sketch and an empty valid structural skeleton

#### Scenario: User starts from an accessible evaluator version
- **WHEN** an authenticated user starts an evaluator draft from a version they may read
- **THEN** the draft copies the evaluator definition, records that version as lineage, and copies no execution instance data

#### Scenario: Multiple or inaccessible seeds are refused
- **WHEN** a request supplies multiple seed modes or a base artifact/session the actor cannot access
- **THEN** no draft is created and authorization/validation fails without revealing the inaccessible object

### Requirement: Every authored definition remains inspectable at full, diff, and summary fidelity
The system SHALL render the current draft definition at full, anchored-diff, and summary views from the same authoritative structure. The full view SHALL expose every state field, tool/effect declaration, graph edge, loop guard, sub-artifact composition, I/O manifest, evaluator binding, and resource policy that can affect execution. The summary MAY adapt terminology to the user but SHALL NOT hide a side effect, external destination, required credential class, or unresolved validation error. A diff SHALL be anchored to an immutable session event/version and fail explicitly when that anchor is unavailable.

#### Scenario: Technical user requests the full definition
- **WHEN** the owner asks to inspect the full current draft
- **THEN** the response contains a reversible representation of every execution-affecting declaration and its unresolved validation state

#### Scenario: Casual user requests a summary
- **WHEN** the owner requests a summary
- **THEN** the response explains inputs, outputs, main stages, effects, providers/capabilities, and known blockers without presenting a false no-effect simplification

#### Scenario: Diff anchor expired
- **WHEN** a requested diff anchor is outside retained session history
- **THEN** the system reports the missing anchor and does not invent a diff against another version

### Requirement: Draft edits are atomic structural operations with an escape hatch
The system SHALL support atomic batches that add, change, or remove typed state, reducers, tools, graph nodes/edges/entry/terminal points, guarded cycles, sub-artifact composition, declared inputs/outputs, evaluator bindings, and bounded generic definition fields. All operations in one batch SHALL either commit as one session event or leave the draft unchanged. Validation SHALL reject unknown references, incompatible signatures/types, undeclared write fields, unguarded cycles, invalid reducers, and composition cycles with machine-readable reasons.

#### Scenario: Valid edit batch commits atomically
- **WHEN** every operation in a batch is valid against the same pre-edit draft
- **THEN** all changes become one ordered authoring event and the resulting draft version advances once

#### Scenario: One operation is invalid
- **WHEN** one operation in a multi-edit batch introduces an unknown subnode or invalid graph cycle
- **THEN** the whole batch is rejected and the pre-edit draft remains authoritative

### Requirement: Files are typed execution-scoped inputs and deliverables
An authored node SHALL be able to declare scalar, structured-object, file, and file-bundle inputs and outputs with names, accepted media types, cardinality, size bounds, and filename policy. Invocation SHALL bind client attachments or authorized host files to execution-scoped opaque handles rather than embedding unrestricted local paths in a shared definition. Returned file outputs SHALL carry declared media type, bounded size, safe filename, and downloadable or connector-effect disposition. File handles SHALL expire or be revoked according to their declared lifetime and SHALL NOT grant access to sibling users, universes, or undeclared host paths.

#### Scenario: Attached PDFs satisfy a declared bundle input
- **WHEN** an invocation supplies the allowed number and size of PDF attachments for a file-bundle input
- **THEN** the node receives execution-scoped handles and metadata without receiving an unrestricted client filesystem path

#### Scenario: Attachment violates the manifest
- **WHEN** an attachment has a disallowed media type, exceeds bounds, or is missing for a required input
- **THEN** invocation fails before execution with field-level validation evidence

#### Scenario: Node emits a named file deliverable
- **WHEN** execution returns bytes satisfying a declared file output
- **THEN** the user receives a bounded deliverable with safe declared filename and media type
- **AND** no connector push occurs unless separately declared and authorized

### Requirement: Test execution is isolated, budgeted, and side-effect-free by default
Every authoring test run SHALL execute the selected immutable draft version in a fresh isolation boundary with explicit CPU, memory, wall-time, output-size, network, filesystem, model-spend, and external-call budgets. The default mode SHALL replace all declared external effects, connector pushes, host-file writes, subprocesses, and irreversible operations with structured simulated-effect evidence. Network access SHALL be denied except through declared/approved destinations; secrets SHALL be vended only to a declared adapter and SHALL not enter draft-visible output or logs.

#### Scenario: Default test reaches an external effect
- **WHEN** a default dry test reaches a declared connector push or other effect
- **THEN** no external mutation occurs and the result contains a redacted structured `would_execute` record

#### Scenario: Draft attempts undeclared network access
- **WHEN** draft code connects to a destination outside its approved declaration
- **THEN** the isolation boundary denies the call and reports the policy violation without exposing network credentials

#### Scenario: Draft exceeds a hard budget
- **WHEN** test execution exceeds CPU, memory, wall-time, output, or spend budget
- **THEN** the runtime terminates it, records which budget fired, and does not publish or partially apply effects

### Requirement: Real test effects require explicit per-run authority
A non-simulated authoring test MAY execute only reversible effects or explicitly approved irreversible effects through the canonical external-effect authority and receipt boundary. The system SHALL show destination, effect class, payload summary, credential class, and idempotency key before requesting confirmation. Consent from an earlier run, a node definition, or a general connector grant SHALL NOT substitute for per-run confirmation where the effect is irreversible. A refused or expired confirmation SHALL leave the draft and external systems unchanged.

#### Scenario: Owner confirms a reversible effect test
- **WHEN** the owner confirms the exact destination and payload summary and the canonical effect boundary authorizes it
- **THEN** execution uses the normal receipt/idempotency path and attaches the result to the test event

#### Scenario: Irreversible effect lacks fresh confirmation
- **WHEN** a real test reaches an irreversible effect without valid per-run confirmation
- **THEN** execution pauses or refuses before the adapter call and records no successful receipt

### Requirement: Testing never publishes and publication is an explicit versioned transition
Test success, evaluator success, or optimization improvement SHALL NOT publish a draft. Publication SHALL require an explicit owner-authorized transition of one immutable draft version after structural validation, effect/credential review, required tests, and unresolved-risk handling. It SHALL create a new version with parent lineage, author, timestamp, change message, definition hash, validation evidence, and provenance; later edits SHALL produce another version rather than mutating the published version in place. Failed publication SHALL leave both the published artifact and draft inspectable.

#### Scenario: Test passes without publish
- **WHEN** a draft test completes successfully and no publication request follows
- **THEN** no discoverable/published artifact version is created or changed

#### Scenario: Exact draft version publishes
- **WHEN** the owner explicitly publishes draft version N and every required gate passes
- **THEN** one immutable artifact version is created with hash, lineage, provenance, and evidence bound to version N

#### Scenario: Draft changes during publication
- **WHEN** the session advances after the user reviewed version N but before publication commits
- **THEN** the publication request fails its version/hash check and does not silently publish the newer draft

### Requirement: Node and evaluator authoring share one structural lifecycle
Evaluators SHALL be authorable, inspectable, testable, versioned, and attributable through the same session lifecycle as nodes while retaining the canonical evaluator input/result contract. An evaluator definition SHALL declare artifact/context inputs, verdict/score/rationale/evidence/cost outputs, determinism/cache policy, and any external or human stage. Authoring SHALL support ordered evaluator chains with explicit continuation/termination rules without making the surrounding moderation, convergence, or scheduling workflow itself an evaluator.

#### Scenario: User authors an evaluator
- **WHEN** a user publishes an evaluator draft satisfying the canonical evaluator contract
- **THEN** it becomes a versioned evaluator artifact with the same inspection, provenance, and lineage guarantees as a node

#### Scenario: Chain stage is incomplete
- **WHEN** an evaluator chain has no terminal rule for one possible verdict
- **THEN** publication is blocked with the uncovered verdict path identified

### Requirement: Authoring has equivalent browser, local-host, and contributor paths
Browser-only users SHALL be able to author and test through a real chatbot using the canonical connector handles. Local-app/tray users MAY run the same authoring protocol and tests on their authorized host capabilities, and OSS contributors MAY materialize definitions in code and contribute through reviewed git paths. All paths SHALL produce the same versioned definition/evaluator contracts and provenance semantics; no path may publish an opaque artifact unavailable for later user inspection.

#### Scenario: Browser-only user authors through chat
- **WHEN** a connector-authenticated browser user describes, inspects, tests, and publishes a supported artifact
- **THEN** the workflow completes without requiring a local checkout or hidden provider-specific tool

#### Scenario: Contributor imports a code-defined artifact
- **WHEN** reviewed source materializes an artifact definition through the contributor path
- **THEN** the resulting version is inspectable through the same full representation and records source/review provenance

### Requirement: Autoresearch separates intent, mutation surface, and fixed evaluation
Each optimization request SHALL bind three separately versioned inputs: an owner-approved optimization specification declaring objective/budgets/constraints/merge policy, an explicit editable field-path surface on one immutable baseline artifact version, and a fixed evaluator or evaluator chain plus fixture/reference revision. Optimization workers SHALL mutate only allowed field paths and SHALL NOT alter the fixed evaluator, fixture, budget, constraints, merge policy, or baseline evidence during the run.

#### Scenario: Candidate changes an allowed prompt field
- **WHEN** an optimization worker proposes a candidate changing only an allowed field and satisfying constraints
- **THEN** the candidate is eligible for evaluation against the fixed evaluator/fixture revision

#### Scenario: Candidate changes the evaluator
- **WHEN** a candidate alters the bound evaluator, fixture, budget, merge policy, or non-editable artifact field
- **THEN** it is rejected before evaluation and cannot become the winner

### Requirement: Optimization execution is leased, deduplicated, and budget-authoritative
The system SHALL assign experiment iterations through expiring exclusive leases, compute a deterministic candidate hash over baseline plus allowed changes, and prevent more than one authoritative evaluation of the same candidate within a request. Run-count, wall-clock, spend, token, external-call, and concurrency budgets SHALL be enforced at reservation and completion boundaries so concurrent workers cannot oversubscribe them. Terminal success, failure, timeout, cancellation, deduplication, and late-result rejection SHALL remain observable and attributable.

#### Scenario: Two workers propose the same candidate
- **WHEN** concurrent workers reserve or submit the same candidate hash
- **THEN** at most one evaluation is authoritative and the duplicate is recorded without spending another evaluation budget

#### Scenario: Lease expires during evaluation
- **WHEN** a worker returns after its lease has been reclaimed
- **THEN** the stale result cannot overwrite the current iteration state or consume winner authority

#### Scenario: Budget exhaustion races with reservation
- **WHEN** concurrent reservations would exceed any hard optimization budget
- **THEN** only the budget-fitting reservations succeed and remaining work becomes terminally unreserved/cancelled with evidence

### Requirement: Evaluator optimization is acyclic and explicitly layered
An evaluator MAY itself be optimized only against a distinct fixed meta-evaluator/reference revision. Submission SHALL reject a direct or transitive cycle in the evaluator-of-evaluator graph. Additional meta-evaluation depth SHALL require explicit owner declaration for every layer and bounded depth/budgets; implicit recursive optimization SHALL be refused.

#### Scenario: Evaluator is optimized against a gold-set agreement evaluator
- **WHEN** the target evaluator and distinct fixed meta-evaluator form an acyclic declared layer
- **THEN** the optimization may proceed under ordinary candidate and budget rules

#### Scenario: Optimization graph contains a cycle
- **WHEN** the proposed evaluator dependency reaches the target evaluator transitively
- **THEN** submission fails with the cycle path and starts no work

### Requirement: Merge-back follows declared policy and preserves all candidate evidence
At optimization completion, the system SHALL compare eligible candidates with the immutable baseline under the bound evaluator revision and direction. It SHALL retain top candidates, measurements, failures, costs, hashes, and producing-worker provenance. `human_review_always` SHALL never auto-merge; threshold policies SHALL auto-publish only when the winning improvement satisfies the exact declared bound and every publication gate. No-improvement, inconclusive, disputed, or budget-exhausted runs SHALL leave the baseline unchanged. Any accepted candidate SHALL publish as a normal new artifact version with the optimization request and evidence in provenance.

#### Scenario: Human review is mandatory
- **WHEN** the merge policy is `human_review_always`
- **THEN** completion presents bounded candidates and makes no publication until the owner explicitly selects one

#### Scenario: Threshold is not met
- **WHEN** the best valid candidate improves less than the exact declared threshold or the comparison is inconclusive
- **THEN** the baseline remains current and the run records `no_merge` with evidence

#### Scenario: Threshold winner is accepted
- **WHEN** the best candidate clears the declared threshold and all publication gates
- **THEN** one new immutable artifact version is published with baseline, candidate, evaluator, metric, cost, and worker provenance

### Requirement: Authoring completion includes adversarial isolation and concurrent optimization proof
The capability SHALL NOT be considered implemented until automated and rendered evidence proves owner isolation, full/diff fidelity, typed file transfer, simulated effects, explicit publication, evaluator authoring, sandbox denial, candidate leases, deduplication, hard budget stops, cycle rejection, and merge policy. The §14 proof SHALL exercise at least the declared 100 concurrent author-session target, 1,000 sequential cross-account sessions, concurrent duplicate candidates, evaluator cache contention, and failure injection without cross-user bleed, double evaluation, lost events, hidden effects, or budget oversubscription.

#### Scenario: Concurrent sessions and experiments run under declared load
- **WHEN** the §14 harness drives authoring, sandbox tests, and optimization workers concurrently across accounts
- **THEN** every event/result remains bound to its owner/session/request and all measured latency/resource/error bounds are reported

#### Scenario: Rendered chatbot acceptance
- **WHEN** a browser-only user completes describe, inspect, attach, dry-test, revise, and explicit-publish through the live connector
- **THEN** the transcript and trace show only canonical advertised handles, faithful code/effect evidence, and the exact published version
