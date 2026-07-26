# Test Identity Harness

## ADDED Requirements

### Requirement: Test founders use ordinary external identities and grants

The test harness SHALL exercise at least two distinct authorization-server-issued subjects through
the same OAuth, connector, and grant path used by ordinary founders. Its operator roster SHALL map
aliases to exact subject IDs, remain access-controlled and operator-private, and never be committed or
logged. It SHALL NOT contain or synthesize bearer tokens, refresh tokens, cookies, provider
credentials, caller-forged identity headers, or privileged grants.

#### Scenario: Two test founders authenticate normally

- **WHEN** the multi-founder acceptance flow runs
- **THEN** two distinct external subjects authenticate through ordinary connector OAuth and ordinary
  founder grants
- **AND** neither request uses a fake provider, direct request-context injection, shared secret, or
  impersonation mechanism.

#### Scenario: Unknown roster identity fails closed

- **WHEN** an operator names an alias absent from the allowlisted test roster or a roster entry lacks
  an exact external subject
- **THEN** the harness refuses to run or reset that identity
- **AND** it does not fall back to anonymous, a maintainer identity, or a platform credential.

### Requirement: Durable acceptance evidence redacts stable identity subjects

The test harness SHALL establish each live caller's deployment-scoped, non-reversible principal
fingerprint during the rendered session while persisting only that fingerprint or its non-secret alias
in logs, third-party chatbot transcripts, traces, and screenshots. It SHALL NOT send or persist raw
bearer material or a raw stable subject through the public status or durable acceptance surfaces.

#### Scenario: Rendered proof identifies both callers without leaking identifiers

- **WHEN** a rendered chatbot acceptance run records the two test founders and their status responses
- **THEN** the live assertions distinguish both principal fingerprints
- **AND** the saved evidence names only roster aliases or redacted fingerprints and contains no bearer,
  refresh token, cookie, provider credential, or raw subject.

### Requirement: Acceptance uses only requester-authorized compute

The test harness SHALL permit model execution only through a complete requester-owned BYOC authority
bundle or an accepted-market compute/model grant already authorized by the canonical first-contact
execution contract. Platform or maintainer hardware, local model routes, quota, accounts, credentials,
auth homes, provider limits, and ambient process configuration SHALL never be eligible. When neither
requester nor market authority is complete, the harness SHALL prove birth and identity with zero
provider invocation and require a structured held/setup-required result.

#### Scenario: Missing requester authority proves identity without model execution

- **WHEN** an external test founder reaches first contact without complete requester BYOC or an
  accepted-market compute/model grant
- **THEN** the acceptance run verifies home birth and the principal fingerprint without invoking any
  provider
- **AND** it records the structured held/setup-required state rather than borrowing a maintainer or
  platform route.

#### Scenario: Authorized requester compute is attributable

- **WHEN** a rendered acceptance run invokes a model
- **THEN** its evidence identifies a complete requester-owned BYOC bundle or accepted-market grant as
  the authority
- **AND** no platform or maintainer resource is present in the eligible route set.
