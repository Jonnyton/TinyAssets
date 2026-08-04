## ADDED Requirements

### Requirement: Authenticated evidence is sealed and sender-specific

The system SHALL construct mapping evidence only from a verifier-produced, process-sealed app event that snapshots the authenticated provider, installation, workspace, event, and external sender identifiers. The evidence payload SHALL be deeply immutable, and a persisted replay receipt SHALL NOT satisfy the evidence requirement.

#### Scenario: Slack event exposes a stable sender snapshot

- **WHEN** the Slack verifier authenticates an event callback containing a valid `event.user`
- **THEN** the resulting evidence exposes the exact sender ID separately from the message payload and later payload mutation cannot change it

#### Scenario: Receipt data cannot mint evidence

- **WHEN** a caller passes a persisted app-event receipt, a deserialized copy, or an unsealed event-shaped object to mapping
- **THEN** mapping rejects it before reading or writing any mapping state

### Requirement: Provisioning resolves one founder-owned target without caller-selected authority

The system SHALL provision a mapping only from a sealed authenticated event and a trusted server-owned setup resolver that receives an external-principal key containing provider, installation, workspace, and sender IDs but no payload or request metadata. The resolver SHALL select the TinyAssets subject, founder-home universe, agent binding, and expected binding revision; no caller-provided external IDs, subject IDs, universe IDs, binding IDs, roles, generations, message text, mentions, channels, or display names SHALL select authority.

#### Scenario: Current founder target is provisioned

- **WHEN** the trusted resolver returns one target whose founder home, admin ACL, binding creator, configured status, and expected revision all match current stores
- **THEN** the system atomically creates one active mapping with a content-free digest and current membership/mapping generations

#### Scenario: Missing or ambiguous setup fails closed

- **WHEN** the resolver returns no target, multiple targets, a cross-tenant target, a non-founder role, a missing home, a non-admin ACL, or a binding not owned by the subject
- **THEN** provisioning returns a typed denial and persists no active mapping

### Requirement: Active mapping resolution revalidates current authority

The system SHALL resolve an active mapping only when the authenticated event tuple exactly matches one active record and the current founder home, admin ACL, ACL-derived membership generation, binding owner/status, and binding revision still match the record. It SHALL fail closed on missing, revoked, stale, ambiguous, or cross-tenant state.

#### Scenario: Exact current mapping resolves

- **WHEN** a fresh sealed event matches one active mapping and every current authority check matches
- **THEN** the system returns the subject, universe, agent binding, binding revision, membership generation, and mapping generation without message content

#### Scenario: Revocation or regrant fences old evidence

- **WHEN** the mapping is revoked, the admin ACL is removed or regranted, the founder home changes, or the binding revision/owner/status changes
- **THEN** resolution refuses the old mapping and emits no target authority

### Requirement: Mapping lifecycle is atomic and generation-aware

The system SHALL use a crash-safe SQLite transaction and uniqueness fence for mapping creation, duplicate replay, conflicting target detection, and revocation. One external tuple SHALL have at most one active mapping; same-target retries SHALL return the existing record, while conflicting targets SHALL fail without overwriting it.

#### Scenario: Concurrent same-target provisioning has one winner

- **WHEN** concurrent processes provision the same authenticated external tuple and same current target
- **THEN** exactly one active record is stored and all equivalent callers receive the same mapping generation

#### Scenario: Conflicting target cannot replace an active mapping

- **WHEN** concurrent or repeated provisioning proposes a different subject, universe, binding, revision, or membership generation for an active tuple
- **THEN** the system raises a conflict and preserves the original active record

#### Scenario: Revocation is idempotent and generation-fenced

- **WHEN** revocation names the active mapping and expected mapping generation
- **THEN** the mapping becomes inactive exactly once; a repeated revocation is stable, and a stale generation cannot revoke or replace a newer mapping

### Requirement: Mapping remains downstream-authority neutral

The mapping capability SHALL NOT issue custody, runtime, workflow, outbound, Slack reply, route, or MCP authority. It SHALL add no public MCP handle and SHALL persist no provider secret, signature, raw body, message text, token, or bearer material.

#### Scenario: Mapping result cannot activate execution

- **WHEN** a mapping is provisioned or resolved
- **THEN** the result contains only typed identity/binding references and generations, with no invocation grant, custody token, route, or external effect
