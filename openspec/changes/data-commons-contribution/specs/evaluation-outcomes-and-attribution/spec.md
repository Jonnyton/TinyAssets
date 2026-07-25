## MODIFIED Requirements

### Requirement: Contribution and attribution are append-only ledgers with idempotent, bounded provenance
The contribution ledger (`tinyassets.contribution_events`) SHALL be a single append-only table whose `weight` is a signed real value (positive for credit, negative for regression), SHALL be idempotent on a caller-supplied `event_id` via insert-or-ignore, and SHALL be emitted from the run-completion, rollback, and graph-compilation paths. Attribution edges (`tinyassets.api.market` record-remix) SHALL record parent-to-child provenance with `credit_share` clamped into `[0, 1]`, SHALL reject a cycle by walking up to 50 ancestor hops before insert, and SHALL derive each edge's generation depth as the parent's maximum depth plus one.

Attribution edges SHALL additionally admit a **dataset-manifest** endpoint kind alongside the existing branch and node kinds, so that derivation between content-addressed commons artifacts is recorded on this same substrate rather than in a second lineage store. The endpoint kind SHALL remain a closed, explicitly enumerated set — widening it is a schema change with a migration, never an unchecked free-text column — and every existing guarantee SHALL apply unchanged to a manifest edge: the same clamped `credit_share`, the same bounded ancestor walk and cycle rejection before insert, the same parent-maximum-plus-one generation depth, and the same append-only uniqueness on the parent/child pair. An edge whose endpoint kind is not in the enumerated set SHALL be rejected rather than coerced, stored as an untyped identifier, or written under a substituted kind. This modification widens the endpoint domain only; it changes no clamp, cycle, depth, idempotency, or append-only semantics, and adds no second provenance table.

#### Scenario: duplicate contribution event is ignored
- **WHEN** two contribution events are recorded with the same caller-supplied `event_id`
- **THEN** only the first is inserted and the second is silently skipped

#### Scenario: credit share is clamped to the unit interval
- **WHEN** a remix edge is recorded with a `credit_share` outside `[0, 1]`
- **THEN** the persisted credit share is clamped into `[0, 1]`

#### Scenario: an attribution cycle is rejected
- **WHEN** a remix edge would make the child an ancestor of the parent
- **THEN** the edge is rejected with a cycle-detected error and no edge is written

#### Scenario: a manifest-to-manifest derivation records on the same substrate
- **WHEN** a derived dataset manifest is recorded as a child of the manifests it was derived from
- **THEN** the edges are written on the existing attribution-edge substrate with the dataset-manifest endpoint kind
- **AND** no dataset-specific lineage table is created to hold them

#### Scenario: manifest edges inherit every existing guarantee
- **WHEN** a manifest edge is recorded with an out-of-range credit share, or would close a cycle, or duplicates an existing parent/child pair
- **THEN** the clamp, the bounded ancestor walk and cycle rejection, and the append-only uniqueness behave exactly as they do for a branch edge
- **AND** its generation depth is the parent's maximum depth plus one

#### Scenario: an unenumerated endpoint kind is rejected
- **WHEN** an edge is submitted with an endpoint kind outside the enumerated set
- **THEN** the edge is rejected
- **AND** it is not coerced to a branch edge, stored under a substituted kind, or written as an untyped identifier
