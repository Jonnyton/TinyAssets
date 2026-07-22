# Identity, Auth, and Access Control

## ADDED Requirements

### Requirement: Status reads expose self-only request identity evidence

The server SHALL return `request_identity` containing only `bearer_present` and a deployment-scoped,
non-reversible `principal_fingerprint` derived from the resolved request subject using a versioned,
domain-separated HMAC-SHA-256 or equivalent reviewed PRF under a dedicated high-entropy key, from the
shared status implementation used by both `get_status` and
`read_graph target=status`. It SHALL return that evidence on first-contact, anonymous, and normal
successful status reads; SHALL NOT return the raw subject or retain the bearer itself; and SHALL NOT
let a caller select or inspect another subject. It SHALL fail closed when the fingerprint key is
unavailable and SHALL NOT fall back to a plain hash or raw subject. The version SHALL change explicitly
when the key rotates, and the dedicated key SHALL remain separate from provider, maintainer, OAuth, and
roster credentials and logs.

#### Scenario: Authenticated caller establishes its own resolved identity

- **WHEN** a valid bearer resolves and the caller invokes either status read
- **THEN** `request_identity.bearer_present` is true and
  `request_identity.principal_fingerprint` is stable for that subject within the deployment
- **AND** the response contains no raw subject, bearer, refresh token, cookie, provider credential,
  email, or grant set.

#### Scenario: Missing fingerprint key cannot weaken privacy

- **WHEN** the dedicated fingerprint key is absent or invalid
- **THEN** identity evidence returns a structured unavailable failure and the acceptance check fails
- **AND** no plain hash, raw subject, provider credential, or ambient maintainer identity is used as a
  fallback.

#### Scenario: Anonymous first contact is explicit

- **WHEN** a request with no bearer reaches either status read before any founder home exists
- **THEN** `request_identity.bearer_present` is false and the principal fingerprint identifies the
  anonymous request class without encoding a subject
- **AND** the evidence is present even on an early first-contact response.

#### Scenario: Invalid bearer remains a transport failure

- **WHEN** a request presents an invalid bearer
- **THEN** the auth boundary returns `401 invalid_token` before tool dispatch
- **AND** no status response or echoed token is produced.
