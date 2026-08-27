## MODIFIED Requirements

### Requirement: Agent definitions support verified portable interchange
The platform SHALL expose a canonical `agent-definition/v1` document containing no binding-private data, SHALL preserve its normalized public content and content fingerprint exactly through export-import-export even when no parent exists in the destination commons, SHALL keep immutable portable lineage declarations separate from locally verified ledger projections, SHALL identify portable parents by stable definition-content and component-content fingerprints, and SHALL grant verified lineage credit only for parent components resolvable and fingerprint-matched in the local commons.

#### Scenario: Export excludes universe-private state
- **WHEN** a caller reads the portable form of a public definition that has private universe bindings or runtime activity
- **THEN** the export contains the public components, fingerprint, and immutable portable lineage declarations
- **AND** it contains no universe ID, binding ID, role, resource reference, channel address, conversation, credential, effect payload, execution record, or runtime state

#### Scenario: Multi-parent child round-trips through an empty commons
- **WHEN** an actor exports a child whose portable lineage declares components from several parents and imports it into a commons containing none of those parents
- **THEN** the imported definition retains byte-equivalent normalized portable content and the same content fingerprint
- **AND** a second export retains every parent-definition fingerprint, parent-component fingerprint, component key, and credit share
- **AND** no unresolved declaration is promoted to a verified ledger edge or verified credit

#### Scenario: Stable fingerprints resolve unique local verification
- **WHEN** a portable lineage declaration names a parent-definition fingerprint and parent-component fingerprint that match exactly one immutable local public definition and component
- **THEN** publication writes the corresponding server-local verified lineage projection
- **AND** the server-local projection does not alter the immutable portable declaration or child fingerprint

#### Scenario: Ambiguous fingerprint remains informational
- **WHEN** zero or multiple local definitions match a portable parent's definition and component fingerprints
- **THEN** publication preserves the immutable portable declaration as informational provenance
- **AND** it writes no verified lineage projection or verified credit for that declaration

#### Scenario: Tampered import is rejected
- **WHEN** an import supplies a definition fingerprint, parent-definition fingerprint, or parent-component fingerprint that does not match its normalized portable content or resolved local parent
- **THEN** the import fails validation
- **AND** no local definition, lineage projection, binding, stage, or receipt is written
