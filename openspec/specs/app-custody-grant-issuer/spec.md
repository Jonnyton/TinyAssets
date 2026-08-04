# app-custody-grant-issuer Specification

## Purpose
TBD - created by archiving change issue-app-custody-grants. Update Purpose after archive.
## Requirements
### Requirement: Issue only from current founder mapping
The authority SHALL require sealed authenticated app evidence and SHALL revalidate the external principal through the current founder-owned mapping before issuing a grant.

#### Scenario: stale mapping is denied
- **WHEN** the mapping is absent, revoked, or no longer matches founder home, exact admin ACL, binding status/revision, or membership generation
- **THEN** no custody grant is issued

### Requirement: Minimize and protect grant authority
The authority SHALL resolve storage from server-owned state, SHALL exclude event payload/message content and credentials, SHALL sign canonical grant evidence with the configured private key, and SHALL return only a content-free signed handoff for the existing custody domain's opaque one-use mint.

#### Scenario: payload cannot influence storage resolution
- **WHEN** authenticated evidence contains arbitrary message text or payload fields
- **THEN** the storage resolver receives only the mapped binding record

### Requirement: Bound custody requests
The authority SHALL allow-list custody actions, require canonical request and mutation idempotency digests, enforce a bounded future expiry, and use the mapping generation as the grant selection generation.

#### Scenario: malformed or overlong grant request
- **WHEN** the action, digest, TTL, or storage roots are invalid
- **THEN** issuance fails closed without creating a grant

### Requirement: Preserve one-use semantics
The signed handoff SHALL preserve the exact grant identity and canonical evidence needed for the existing custody store to enforce one-use, replay, serialization, cross-process, and signature checks.

#### Scenario: grant replay
- **WHEN** a caller consumes the same grant twice
- **THEN** the first exact operation may proceed and the second is denied

