## Why

The cloud automation already persists owner-scoped destination grants, but production can only resolve legacy vault-backed GitHub credentials. A phone user therefore cannot connect GitHub or keep a cloud drain useful without a desktop secret, even though WorkOS Pipes is configured and its server-only key is deployed.

## What Changes

- Add an owner-authenticated canonical connection action that returns a WorkOS Pipes authorization URL without accepting secrets or caller-supplied user IDs.
- Add a completion/reconciliation action that verifies the authenticated user’s connected GitHub account and creates one opaque, universe-scoped destination connection/grant.
- Resolve WorkOS Pipes credentials inside the existing credential-blind broker child, never in MCP output, SQLite public state, or adapter processes.
- Make connection setup idempotent and fail closed on missing, revoked, ambiguous, or cross-user accounts.
- Advertise the connection prerequisite and next action from cloud-automation inspection/setup responses.

## Capabilities

### New Capabilities

- `workos-pipes-user-connections`: owner-scoped GitHub authorization, reconciliation, opaque ledger references, and broker-only token vending.

### Modified Capabilities

- `user-owned-cloud-automation`: cloud automation setup reports a phone-usable destination connection action and consumes only the resulting requester-owned grant.

## Impact

Affected surfaces are `write_graph target=connection`, `read_graph target=connections`, cloud-automation prerequisite projection, the outbound connection ledger/broker, the production HTTP environment’s `WORKOS_API_KEY`, and focused MCP/API/ledger tests. Existing vault and test-fixture paths remain unchanged.
