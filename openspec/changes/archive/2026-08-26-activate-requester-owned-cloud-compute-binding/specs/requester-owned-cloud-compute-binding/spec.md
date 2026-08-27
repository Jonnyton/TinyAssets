## ADDED Requirements

### Requirement: Server-owned enrollment is explicit and fail-closed

The system SHALL resolve provider authority only from a server-owned, owner/universe/provider-scoped enrollment entry with bounded operations, roles, budgets, credential-reference digest, assignment generation/digest, and expiry. It MUST reject caller-authored authority fields, wildcard owners, malformed or duplicate entries, expired entries, and missing enrollment without mutation.

#### Scenario: Missing enrollment holds setup

- **WHEN** an authenticated owner requests a provider bind and no exact enrollment exists for that owner, universe, and provider
- **THEN** the system returns a redacted setup-required/held result and writes no provider binding

#### Scenario: Caller cannot widen enrollment

- **WHEN** the request includes an owner, credential reference, budget, role, assignment digest, or binding ID that differs from the server enrollment
- **THEN** the system ignores or rejects the assertion and never widens or creates authority from it

### Requirement: Owner can idempotently bind enrolled compute

The system SHALL derive the authenticated owner from request context, require an exact universe and canonical provider, and issue a deterministic `ProviderWorkBinding` through `ProviderWorkBindingService` without returning a credential or activating an automation.

#### Scenario: First bind returns redacted binding

- **WHEN** an authenticated owner binds one valid enrolled provider
- **THEN** the system persists one active binding with server-derived identity, returns only its redacted ID/generation/provider/budget projection, and leaves the automation stopped until the owner explicitly creates or resumes it

#### Scenario: Concurrent/replayed bind is stable

- **WHEN** two identical owner bind requests overlap or the same request is replayed
- **THEN** both return the same deterministic binding projection and at most one binding record is persisted

### Requirement: Cloud setup consumes only requester-owned binding

The cloud automation SHALL remain held unless its current binding is active, owner/universe exact, within expiry and budgets, and paired with an exact requester-owned destination grant; it MUST never substitute maintainer or market compute.

#### Scenario: Binding and destination are both required

- **WHEN** the owner attempts to create or resume an automation with either provider binding or destination grant missing, revoked, stale, or expired
- **THEN** setup returns actionable prerequisites and no cloud slice is claimed

#### Scenario: Binding revoke fences future work

- **WHEN** an enrolled provider binding is revoked after an automation is prepared
- **THEN** the next cloud claim fails closed with provider-binding-unavailable and no provider call or external effect occurs
