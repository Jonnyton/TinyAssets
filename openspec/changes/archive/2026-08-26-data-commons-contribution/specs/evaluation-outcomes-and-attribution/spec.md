## MODIFIED Requirements

### Requirement: Contribution and attribution are append-only ledgers with idempotent, bounded provenance
The contribution ledger (`tinyassets.contribution_events`) SHALL be a single append-only table whose `weight` is a signed real value (positive for credit, negative for regression), SHALL be idempotent on a caller-supplied `event_id` via insert-or-ignore, and SHALL be emitted from the run-completion, rollback, and graph-compilation paths. Attribution edges (`tinyassets.api.market` record-remix) SHALL record parent-to-child provenance with `credit_share` clamped into `[0, 1]`, SHALL reject a cycle by walking up to 50 ancestor hops before insert, and SHALL derive each edge's generation depth as the parent's maximum depth plus one.

Attribution edges SHALL additionally admit a **commons-artifact** endpoint kind alongside the existing branch and node kinds, so that derivation between content-addressed commons artifacts — a dataset manifest among them — is recorded on this same substrate rather than in a second lineage store. The kind is deliberately generic rather than dataset-specific: no irreducibility finding supports a dataset-only endpoint concept, so the widening admits the commons-artifact class once instead of one kind per artifact type. The endpoint kind SHALL remain a closed, explicitly enumerated set — widening it is a schema change with a migration, never an unchecked free-text column — and an edge whose endpoint kind is not in the enumerated set SHALL be rejected rather than coerced, stored as an untyped identifier, or written under a substituted kind. This modification widens the endpoint domain only; every other semantic in this requirement is unchanged, and no second provenance table is introduced.

#### Scenario: duplicate contribution event is ignored
- **WHEN** two contribution events are recorded with the same caller-supplied `event_id`
- **THEN** only the first is inserted and the second is silently skipped

#### Scenario: credit share is clamped to the unit interval
- **WHEN** a remix edge is recorded with a `credit_share` outside `[0, 1]`
- **THEN** the persisted credit share is clamped into `[0, 1]`

#### Scenario: an attribution cycle is rejected
- **WHEN** a remix edge would make the child an ancestor of the parent
- **THEN** the edge is rejected with a cycle-detected error and no edge is written

#### Scenario: a commons-artifact derivation records on the same substrate
- **WHEN** a derived commons artifact such as a dataset manifest is recorded as a child of the artifacts it was derived from
- **THEN** the edges are written on the existing attribution-edge substrate with the commons-artifact endpoint kind
- **AND** no artifact-specific lineage table is created to hold them

#### Scenario: an unenumerated endpoint kind is rejected
- **WHEN** an edge is submitted with an endpoint kind outside the enumerated set
- **THEN** the edge is rejected
- **AND** it is not coerced to a branch edge, stored under a substituted kind, or written as an untyped identifier
