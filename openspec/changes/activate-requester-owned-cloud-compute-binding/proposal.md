## Why

The cloud automation is deployed with durable continuation and GitHub destination authority, but it correctly remains held because no production requester-owned provider binding can be created from the phone surface. The existing binding store only accepts trusted server-resolved assignment facts; test fixtures and maintainer credentials cannot activate the drain.

## What Changes

- Add a server-only provider enrollment manifest and resolver with explicit owner/universe/provider assignments, bounded operations, roles, budgets, credential-reference digests, and expiry.
- Add an owner-authenticated `bind_provider` cloud-automation operation that selects only the caller's exact enrolled assignment and issues an opaque `ProviderWorkBinding` through the existing service.
- Return a redacted binding projection and actionable setup state; reject caller-supplied owner, credential, budget, assignment, and binding fields.
- Keep missing, ambiguous, expired, revoked, or malformed enrollment fail-closed; do not fall back to maintainer or market compute.
- Add focused concurrency, ownership, redaction, and mirror tests.

## Capabilities

### New Capabilities

- `requester-owned-cloud-compute-binding`: phone-safe enrollment resolution and owner-scoped provider binding for cloud automations.

### Modified Capabilities

- `user-owned-cloud-automation`: activation setup may reconcile one exact requester-owned provider binding before preparing continuation.

## Impact

Affected modules are `tinyassets/provider_work_authority.py`, a new provider enrollment resolver/store, `tinyassets/api/cloud_automations.py`, `tinyassets/universe_server.py`, plugin mirror runtime files, and focused tests. Deployment must provide an explicit server-only enrollment manifest; no raw provider secret is stored in the manifest or accepted through chat.
