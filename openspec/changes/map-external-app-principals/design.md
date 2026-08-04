## Context

PR #2246 admits a Slack event only after verifying the exact raw body and recording content-free replay evidence. `AuthenticatedAppEvent` is currently transient but still carries a mutable payload and has no explicit process-local proof that it came from the verifier. The next V1 handoff needs a durable mapping from one authenticated Slack installation/workspace/sender tuple to the founder's current TinyAssets subject, home universe, and selected custom-agent binding, while preserving the boundary's no-authority contract.

Existing authority sources are already server-owned: `founder_home` binds a subject to a home universe, `universe_acl` grants `admin`, and `agent_bindings` records the binding creator and revision. The app mapping must compose those sources rather than copy or replace their authority.

## Goals / Non-Goals

**Goals:**

- Create, resolve, and revoke one exact external-principal mapping with SQLite atomicity and generation fencing.
- Consume a fresh verifier-produced event and snapshot only the authenticated provider identifiers needed for setup; never use message text, mentions, channel names, or display names.
- Require a trusted server-owned setup resolver for initial target selection, then independently revalidate founder-home, private/admin ACL, binding ownership, binding status, binding revision, and membership generation.
- Keep persisted records content-free and safe to inspect without replaying provider evidence as authority.
- Make duplicate creation idempotent only for the same target; conflicting active mappings fail closed.

**Non-Goals:**

- No Slack route, OAuth/install flow, public MCP action, eighth handle, custody issuer, runtime activation, workflow execution, or outbound reply.
- No non-founder conversation path or general external-identity directory.
- No production provider secret, app installation, or deployment mutation.

## Decisions

### 1. Seal verifier evidence in process and snapshot sender identity

`AuthenticatedAppEvent` will be constructed only through a module-private verifier factory, carry a process-local seal, and expose a deeply immutable JSON snapshot. The verifier will also snapshot Slack's authenticated `event.user` as `external_sender_id`; mapping code will not inspect mutable message payload content. A persisted admission receipt lacks the seal and therefore cannot be passed as mapping evidence.

Alternative rejected: accepting a receipt or caller-supplied `(installation, workspace, sender)` tuple. A self-consistent receipt is replayable data, not fresh provider authentication.

### 2. Use a trusted setup resolver, not client-selected target fields

`AppPrincipalMappingService.provision(event, resolve_target=...)` receives only the sealed event and a server-owned resolver callback. The callback returns the candidate TinyAssets subject/universe/binding tuple; it is not an HTTP/MCP input seam. The service validates the returned target shape and then re-reads current stores before persisting it.

Alternative rejected: adding `subject_id`, `universe_id`, `binding_id`, role, or generation parameters to a public operation. Those fields would let a caller mint a self-consistent but unauthorized mapping.

### 3. Derive membership generation from the current admin grant

The service computes a canonical `membership_generation` token from the current exact-universe admin ACL row's immutable-at-read `granted_at`, permission, and granting subject. Resolution recomputes the token and requires equality. Revocation/regrant therefore makes the old mapping stale even if the subject and universe IDs are reused.

Alternative rejected: an independent client-controlled generation or a timestamp supplied by the provider payload. Both can be replayed or forged.

### 4. Store append-oriented mapping history with an active uniqueness fence

The mapping store records provider/install/workspace/sender, target identity, binding revision, membership generation, mapping generation, status, and a canonical record digest. A partial unique index permits one active mapping per external tuple. Creation runs in `BEGIN IMMEDIATE`: identical active targets replay; conflicting active targets raise a conflict; a revoked tuple receives the next mapping generation. Revocation is idempotent and changes only the current active row's status under an expected-generation check.

Alternative rejected: an in-memory map or a read-then-insert sequence, both of which lose cross-process race safety.

### 5. Revalidate every authority edge at resolve time

Resolution checks the sealed event's exact provider/install/workspace/sender tuple, active mapping status/generation, founder home, current admin ACL, ACL-derived membership generation, binding existence/status/creator, and exact binding revision. Any missing, revoked, stale, ambiguous, malformed, or cross-tenant state returns a typed denial and no target is emitted.

## Risks / Trade-offs

- [Risk] Existing ACL rows do not expose a numeric generation. → Use a canonical digest of the current admin grant's `granted_at`, permission, and subject; any revoke/regrant changes it, and tests cover same-subject regrant.
- [Risk] A trusted setup resolver could be incorrectly wired. → Keep it an explicit dependency, never derive it from request payload, and require current-store revalidation before persistence.
- [Risk] Deep-freezing the event payload may break a future consumer that expects mutable lists. → Preserve mapping/list shape through immutable mapping proxies/tuples and keep the existing read-only indexing contract covered by regression tests.
- [Risk] A mapping is not yet conversation authority. → Keep the API dark and return only a typed mapping record; custody, interlocutor, runtime, and reply remain separate downstream gates.

## Migration Plan

This is additive dark state. The new table is created lazily in the existing TinyAssets SQLite database. No existing app-event receipt is migrated or treated as mapping evidence. Rollback is deleting the unused mapping module and table in a later explicitly reviewed migration; no live route or external state changes in this slice.

## Open Questions

- The later custody/reply slice must decide how its trusted conversation entry consumes the mapped founder record without widening the exact seven MCP handles. This change intentionally leaves that composition open.
