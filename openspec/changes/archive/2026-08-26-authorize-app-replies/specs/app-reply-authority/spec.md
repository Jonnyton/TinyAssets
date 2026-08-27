## ADDED Requirements

### Requirement: Verify a current founder reply authority
The system SHALL accept a reply authorization only when the signed custody handoff uses the canonical custody signing domain, requests `append_message`, and matches a fresh current founder mapping in subject, universe, binding, revision, and mapping generation.

#### Scenario: stale or forged handoff is denied
- **WHEN** the signature, action, mapping, revision, membership generation, or handoff identity is invalid
- **THEN** no reply authorization is returned

### Requirement: Keep reply authorization content-free
The system SHALL resolve a destination from server-owned mapping state and SHALL return only destination references, identity references, response digest, and an authorization digest; it SHALL exclude body, payload, credentials, context, and effect tokens.

#### Scenario: message text cannot select destination
- **WHEN** an authenticated event contains arbitrary message text or channel fields
- **THEN** the destination resolver receives only the current mapping record and the result contains no message content

### Requirement: Fail closed before outbound effects
The reply authority SHALL add no route, MCP handle, runtime invocation, workflow mutation, or outbound effect and SHALL reject malformed digests, unsupported destinations, expired handoffs, and resolver errors.

#### Scenario: unavailable destination
- **WHEN** the server-owned destination resolver cannot produce one exact supported destination
- **THEN** authorization fails without an external call or persisted effect
