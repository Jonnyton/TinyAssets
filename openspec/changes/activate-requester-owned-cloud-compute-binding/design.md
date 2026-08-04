## Context

`ProviderWorkBindingService.issue` already requires a trusted `ProviderWorkBindingResolver`, and the cloud continuation refuses missing or stale bindings. The missing production seam is the resolver's source of requester-owned assignment facts. `install_test_binding` is intentionally test-only and `set_engine`'s raw API-key path is not an acceptable phone surface.

## Goals / Non-Goals

**Goals:**

- Make one exact owner/universe/provider assignment available to a phone request without exposing credentials or allowing caller-authored authority.
- Reuse the existing binding service, deterministic IDs, generation/digest checks, and cloud continuation validation.
- Make the action idempotent and safe under concurrent requests.

**Non-Goals:**

- Do not add market fallback, maintainer substitution, raw chat secret deposit, or a second provider-authority model.
- Do not claim provider enrollment is complete for users without an explicit deployment-owned enrollment entry.
- Do not activate the cloud worker or change tray cutover in this change.

## Decisions

### 1. Use a server-only explicit enrollment manifest

The deployment provides `TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON` as a server secret/config value. It is a JSON array of entries containing only `owner_user_id`, `universe_id`, `provider`, `credential_reference_digest`, `allowed_operations`, `allowed_roles`, assignment generation/digest, budgets, and expiry. The resolver rejects unknown fields, wildcard owners, duplicate keys, malformed digests, expired entries, and non-positive budgets. The actual credential remains in the existing server-side custody path and is never serialized into the enrollment or MCP response.

An explicit manifest is a temporary provider-independent enrollment seam: a future provider OAuth/host enrollment may implement the same resolver without changing the cloud API. It is not a maintainer fallback because every entry is owner- and universe-scoped and no entry means no authority.

### 2. Add an owner-only bind/reconcile operation

`cloud_automations(action="bind_provider")` derives the actor from authenticated request context and requires `universe_id` plus a canonical provider name. It ignores any owner, credential, budget, binding ID, or assignment data in the payload. The resolver finds exactly one matching enrollment, then `ProviderWorkBindingService.issue` persists the deterministic binding. A replay returns the same redacted binding projection; concurrent different assignments return a typed conflict/held result.

`read_graph target=automations` includes redacted provider-binding state and a setup action only; it never returns the manifest or credential reference.

### 3. Keep activation fail-closed until binding and destination are ready

The existing create/rebind path continues to require an active binding and exact destination grant. `bind_provider` does not activate or resume an automation. This preserves single-active cutover and makes the next phone step explicit and reversible.

## Risks / Trade-offs

- **Manifest drift or accidental broad entry** → strict schema, exact owner/universe matching, no wildcard, digest validation, and fail-closed parsing.
- **Concurrent bind requests** → deterministic binding identity and existing store transaction/replay semantics; no caller-generated binding IDs.
- **Credential reference points to missing custody** → provider execution's existing broker/custody check remains authoritative and returns held.
- **Shared deployment needs per-user enrollment** → this first slice requires explicit operator provisioning of a server-only entry; it does not pretend generic users are ready until their own enrollment exists.

## Migration Plan

1. Land resolver and phone operation dark, with the manifest unset by default.
2. Deploy and verify the public canary remains unchanged.
3. Add one explicit requester-owned enrollment entry through the deployment secret/config path, then reconcile it through the authenticated phone client.
4. Create the ordinary cloud automation, verify health, and only then perform single-active cutover and PC-off acceptance.
5. Roll back by removing the enrollment entry and stopping the automation; the binding and continuation fail closed on the next read/claim.

## Open Questions

- Which provider-host/OAuth enrollment will replace the deployment manifest for self-service users? It must implement the same server-owned resolver contract.
