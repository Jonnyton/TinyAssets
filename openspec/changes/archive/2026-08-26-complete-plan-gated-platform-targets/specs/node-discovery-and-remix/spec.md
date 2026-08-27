## ADDED Requirements

### Requirement: Discovery answers a build question in one call with a complete signal block

The discovery surface SHALL accept an intent description with optional structural, domain, and inclusion hints and SHALL return ranked candidates in a single response, so a caller can choose between reuse, remix, collaboration, and new authoring without follow-up calls. Each candidate SHALL carry its identity, a semantic-match signal, a structural-match signal, quality signals, provenance references, active-work signals, and negative signals including deprecation and known failure modes. The response SHALL carry a stable query identifier usable to register standing interest. Signals SHALL be returned as values rather than as a single opaque score, and a signal the system cannot compute SHALL be reported as absent rather than defaulted to a value that reads as evidence. Discovery SHALL be dispatched as an action under `read_graph` per the cross-capability handle invariant and SHALL NOT add an advertised MCP handle.

#### Scenario: Discovery adds no handle

- **WHEN** the connector's advertised tool list is inspected after discovery ships
- **THEN** no discovery handle appears
- **AND** discovery is reachable as an action under `read_graph`

#### Scenario: One call returns everything needed to choose

- **WHEN** a caller submits an intent with optional structural and domain hints
- **THEN** the response returns ranked candidates each carrying identity, match signals, quality signals, provenance references, active-work signals, and negative signals
- **AND** a stable query identifier is returned

#### Scenario: Missing signals are absent, not defaulted

- **WHEN** a candidate has no recorded outcome history or no computable structural match
- **THEN** those signals are reported as absent
- **AND** they are not reported as zero, neutral, or any value that could be read as measured evidence

#### Scenario: Negative signals are returned alongside positive ones

- **WHEN** a candidate is deprecated or carries recorded failure modes
- **THEN** those signals are present in its block rather than causing silent exclusion

### Requirement: Discovery ranking is delegated to a user-buildable selector with a seeded default

The system SHALL NOT fix a platform weighting formula as the discovery ordering authority. Ordering SHALL be produced by a bound selector Branch as with the existing quality-leaderboard selector contract; the platform SHALL ship signals, retrieval, and a seeded default selector used when none is bound. A bound selector SHALL be pure: a Branch carrying node effects or invoking child Branches SHALL be rejected at bind time so ranking cannot cause side effects. Unbinding a selector SHALL fall back to the seeded default rather than failing discovery, and the seeded default SHALL be replaceable by a user without platform involvement.

#### Scenario: Default selector orders discovery when none is bound

- **WHEN** discovery runs with no selector bound
- **THEN** the seeded default selector produces the ordering
- **AND** the response identifies which selector produced it

#### Scenario: Impure selector is rejected at bind time

- **WHEN** a caller binds a Branch that carries node effects or invokes child Branches as the discovery selector
- **THEN** the bind is rejected and the previous selector remains in effect

#### Scenario: Unbinding falls back rather than failing

- **WHEN** a bound selector is unbound
- **THEN** discovery continues using the seeded default selector

### Requirement: Discovery never reveals content the caller cannot read, including through derived blocks

Every candidate and every derived block within a candidate — provenance parents and children, related artifacts, collaborator and active-work counts, negative signals, and superseded-by references — SHALL be filtered by the same visibility and ownership predicate that governs a direct read of the referenced artifact. A restricted artifact SHALL NOT appear by identifier, path, title, summary, snippet, or count. Its existence SHALL NOT be inferable from rank gaps, result totals, or pagination cursors.

Timing is bounded rather than absolutely denied, because an absolute no-timing-inference claim is not checkable. The requirement is a stated **noninterference bound with an executable test model**: for a query whose candidate set differs only by the presence of one restricted artifact, the response-latency distributions of the two cases SHALL be statistically indistinguishable at a documented sample size, statistic, and significance threshold, measured by a repeatable test harness that fixes the query, the visible candidate set, and the environment. The bound and its parameters SHALL be recorded with the implementation, and a measured violation SHALL be treated as a defect in the surface rather than as an accepted limitation. Filtering SHALL therefore be structured so that suppression work does not scale with the number of suppressed candidates in a way that is observable at the stated bound.

Where a visible artifact's lineage passes through a restricted ancestor, the chain SHALL be presented as truncated at an opaque boundary rather than naming the restricted artifact.

#### Scenario: Restricted candidate is fully suppressed

- **WHEN** a candidate matching the query is not readable by the caller
- **THEN** it is absent from the results with no identifier, path, title, summary, or snippet
- **AND** result totals, rank sequence, and pagination give no indication that a candidate was withheld

#### Scenario: Provenance truncates at a restricted ancestor

- **WHEN** a visible candidate's parent chain includes an artifact the caller cannot read
- **THEN** the chain is returned truncated at an opaque boundary marker
- **AND** the restricted ancestor's identifier and metadata are absent

#### Scenario: Active-work signals do not expose restricted activity

- **WHEN** editing or request activity on restricted artifacts would contribute to a returned count
- **THEN** that activity is excluded from the count rather than aggregated into it

#### Scenario: Timing noninterference is measured against a stated bound

- **WHEN** the test harness runs the same query against a corpus that contains a restricted matching artifact and against one that does not, at the documented sample size
- **THEN** the two response-latency distributions are indistinguishable under the documented statistic and significance threshold
- **AND** a measured difference outside the bound is reported as a defect rather than accepted

### Requirement: Commons content ranks as equal first-class content

Discovery SHALL NOT apply a ranking preference, placement boost, badge, or default filter that favors platform-authored or platform-affiliated content over community-authored content of equivalent signals. Provenance SHALL be surfaceable as a signal the selector may consider, but platform origin SHALL NOT be an input the platform itself weights outside the selector. Cross-domain matches SHALL be surfaceable and labelled rather than excluded by default, so a structurally strong match outside the caller's domain hint remains reachable.

#### Scenario: Equivalent signals rank equivalently regardless of origin

- **WHEN** a platform-authored and a community-authored candidate carry equivalent signals
- **THEN** neither receives a placement advantage from its origin

#### Scenario: Cross-domain matches remain reachable

- **WHEN** a candidate outside the caller's domain hint is a strong structural match
- **THEN** it is returned and labelled as cross-domain rather than filtered out by default

### Requirement: Remix from N parents records every parent atomically

Creating a derivative from multiple sources SHALL record one derivation edge per parent and the accompanying contributor credit in a single atomic operation, so a partial failure cannot produce a derivative with incomplete lineage or credit.

The operation SHALL additionally **introduce** aggregate credit enforcement: the recorded credit shares for one artifact SHALL sum to no more than one across all contributors, checked transactionally within the same operation that writes them. This is new enforcement, not preservation of an existing guarantee. As-built, the store constrains each individual `credit_share` to the range `[0, 1]` per row and uniquely per `(artifact_id, actor_id)`; **the aggregate sum across an artifact's contributors is not enforced anywhere** — the ≤ 1.0 aggregate exists only as a schema-module design comment and an advisory `is_credit_valid` helper that no write path is required to consult. An implementing lane SHALL NOT treat the aggregate bound as already held by the substrate, and SHALL specify what happens to pre-existing rows that already violate it rather than assuming there are none.

The operation SHALL reject a derivation that would create a lineage cycle, SHALL be idempotent under retry with the same derivation identity, and SHALL record the caller-supplied derivation rationale. Each parent's derivative count SHALL reflect the derivation. This capability adds no new lineage primitive and no advertised MCP handle: multi-parent derivation edges are already expressible on the shipped substrate, and the operation SHALL be dispatched as an action under `write_graph` per the cross-capability handle invariant.

#### Scenario: All parent edges land or none do

- **WHEN** a derivation from N parents fails partway through recording edges or credit
- **THEN** no derivation edge and no credit row from that operation is persisted
- **AND** the derivative is not left with partial lineage

#### Scenario: Aggregate credit enforcement is added, not assumed

- **WHEN** a derivation from N parents would record credit shares whose sum across the artifact's contributors exceeds one
- **THEN** the operation is refused by a transactional aggregate check introduced with this capability
- **AND** the refusal does not depend on any pre-existing store constraint, because the store enforces only the per-row `[0, 1]` range

#### Scenario: Remix adds no handle

- **WHEN** the connector's advertised tool list is inspected after remix ships
- **THEN** no remix or lineage handle appears
- **AND** the derivation is reachable as an action under `write_graph`

#### Scenario: Retry is idempotent

- **WHEN** the same derivation is submitted again with the same derivation identity
- **THEN** the existing lineage is returned unchanged and no duplicate edge or credit row is created

#### Scenario: Cycles are refused

- **WHEN** a proposed derivation would make an artifact its own ancestor
- **THEN** the operation is refused and no edge is written

### Requirement: Convergence is propose-then-ratify with recusal, and merging supersedes rather than deletes

Merging independently developed artifacts SHALL require a proposal naming its sources and rationale, followed by ratification from each source's authorized owner set, before a canonical successor is created. Ratifications SHALL be authenticated, append-only, and attributable; a proposer SHALL NOT ratify on behalf of a source they control as proposer. On completion the successor SHALL record all sources as parents and each source SHALL be marked superseded with a reference to the successor. Superseded artifacts SHALL remain readable and their lineage SHALL remain walkable. Ratification policy values — the required owner set shape, quorum, and proposal expiry window — SHALL be seeded remixable commons configuration; the authentication, one-ratification-per-source, recusal, and append-only properties SHALL be platform-enforced and SHALL NOT be configurable away. Both proposal and ratification SHALL be dispatched as actions under `write_graph` per the cross-capability handle invariant, and this behavior SHALL NOT add an advertised MCP handle.

#### Scenario: Merge completes only when every source ratifies

- **WHEN** a convergence proposal has ratifications from some but not all required sources
- **THEN** no successor is created and the response reports which sources remain
- **AND** when the final required ratification lands, the successor is created with all sources as parents

#### Scenario: Proposer cannot self-ratify

- **WHEN** the proposer attempts to supply the ratification for a source in their own proposal
- **THEN** the ratification is refused

#### Scenario: Superseded sources stay readable

- **WHEN** a convergence completes
- **THEN** each source is marked superseded with a reference to the successor
- **AND** each source remains readable and its lineage remains walkable

#### Scenario: Convergence adds no handle

- **WHEN** the connector's advertised tool list is inspected after convergence ships
- **THEN** no proposal or ratification handle appears
- **AND** both are reachable as actions under `write_graph`

#### Scenario: Policy is remixable but enforcement is not

- **WHEN** a community configuration changes the quorum shape or proposal expiry window
- **THEN** the new policy governs subsequent proposals
- **AND** authentication, one-ratification-per-source, recusal, and append-only ratification remain in force regardless of configuration

### Requirement: Standing similarity interest is a durable stored query read back through the read path

Registering interest in future similar work SHALL create a durable stored query bound to an authenticated owner, carrying its similarity threshold and the event kinds of interest. Matches SHALL accumulate durably and SHALL be retrievable through the ordinary read path, so a caller that was never connected still receives them. This capability SHALL NOT add an advertised MCP handle for subscription or delivery; live delivery is an optional transport enhancement over the same durable record. Match evaluation SHALL apply the owner's visibility authority, and SHALL scale with the number of outstanding stored queries rather than with the product of queries and total artifact changes. A stored query SHALL be revocable by its owner and SHALL expire under a stated policy.

#### Scenario: Matches survive disconnection

- **WHEN** a matching event occurs while the stored query's owner has no live connection
- **THEN** the match is recorded durably
- **AND** the owner retrieves it on their next read

#### Scenario: Stored queries do not see restricted work

- **WHEN** an event on an artifact the query owner cannot read would otherwise match
- **THEN** no match is recorded and no notification is produced

#### Scenario: Owner revokes a stored query

- **WHEN** the owner revokes a stored query
- **THEN** no further matches accumulate for it
