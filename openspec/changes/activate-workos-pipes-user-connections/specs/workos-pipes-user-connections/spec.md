## ADDED Requirements

### Requirement: Owners can connect GitHub from a phone

The server SHALL derive the authenticated WorkOS subject and SHALL return a WorkOS Pipes authorization URL without accepting a user ID, token, or secret from the caller.

#### Scenario: connect returns authorization
- **WHEN** an authenticated owner requests `write_graph target=connection operation=connect` for a writable universe
- **THEN** the server calls Pipes authorization for that owner and returns a redacted provider/action envelope containing the URL

#### Scenario: spoofed owner is ignored
- **WHEN** the payload contains a different `user_id` or owner field
- **THEN** the server ignores it and uses the authenticated subject

### Requirement: Connected accounts reconcile into opaque grants

The server SHALL accept a connection only when Pipes reports the authenticated owner’s GitHub account as connected, and SHALL persist no access token.

#### Scenario: connected account reconciles
- **WHEN** `operation=reconcile` observes a connected GitHub account
- **THEN** one idempotent destination resource and universe grant are returned with provider, repository, scopes, and opaque IDs only

#### Scenario: account needs authorization
- **WHEN** Pipes reports no account or `needs_reauthorization`
- **THEN** the response is a typed setup-required result with an authorization action and no grant

#### Scenario: duplicate grants
- **WHEN** a second reconciliation targets the same owner/universe/repository
- **THEN** it replays the existing grant rather than creating a second active grant

### Requirement: Broker-only credential vending

The production broker SHALL vend a current Pipes credential only inside the trusted child process, and SHALL reject malformed or cross-owner references.

#### Scenario: token is broker-only
- **WHEN** a granted GitHub operation executes
- **THEN** Pipes credentials are sent only to the trusted GitHub driver and never appear in MCP output, ledger projections, or adapter messages

#### Scenario: vending fails
- **WHEN** Pipes is unavailable, inactive, or returns malformed credentials
- **THEN** the operation fails closed with a secret-free outbound error

### Requirement: Automation setup exposes the next action

Cloud-automation prerequisite projections SHALL identify the connection action when no requester-owned destination grant exists.

#### Scenario: destination missing
- **WHEN** an owner inspects automations without a destination grant
- **THEN** the response includes a phone-usable connect/reconcile next action and remains not ready
