## ADDED Requirements

### Requirement: A resolve operation proposes a connection policy without depositing

The connector surface SHALL expose an operation that accepts the non-secret
shape of pasted credential material plus an optional intent string, and returns
a proposed connection policy. The operation SHALL be a pure proposal: it creates
no vault record, no connection, and no grant, and it is not a deposit path.

#### Scenario: Resolving a paste

- **WHEN** an authenticated owner submits credential shape and an intent line
- **THEN** the response carries a proposed destination, auth scheme, host, path
  template, and methods
- **AND** no ledger or vault state changed

#### Scenario: The operation is offered secret material

- **WHEN** a caller submits a payload containing full credential values
- **THEN** the operation refuses the payload rather than forwarding it, so the
  no-transmission guarantee cannot be bypassed by a careless caller

#### Scenario: Resolution is not possible

- **WHEN** the shape is insufficient to identify a service
- **THEN** the response says so explicitly and carries no partial policy
  presented as confident

### Requirement: The resolve operation is owner-gated like the deposit it precedes

The operation SHALL require an authenticated principal holding an explicit
`admin` ACL row on the target universe, matching the gate on `connect_http`, and
SHALL return the same uniform absent-resource envelope on denial.

#### Scenario: A non-owner calls resolve

- **WHEN** an authenticated principal without an admin row calls the operation
- **THEN** it returns the uniform not-found envelope, disclosing nothing about
  whether the universe exists

#### Scenario: An anonymous caller

- **WHEN** the request carries no authenticated principal
- **THEN** the operation returns an authentication-required error and performs
  no inference
