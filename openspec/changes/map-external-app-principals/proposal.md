## Why

The authenticated Slack event boundary now proves that an event came from the configured installation, but it intentionally produces no TinyAssets identity or conversation authority. The approved V1 cannot safely continue to custody, runtime, or a governed reply until one exact installation/workspace/sender tuple is mapped to the current founder account, private universe, and agent binding.

## What Changes

- Add a dark, server-authoritative mapping capability for authenticated external app principals.
- Consume only fresh authenticated provider evidence; callers cannot submit external identifiers, universe IDs, binding IDs, roles, or generations as authority.
- Resolve exactly one active installation/workspace/sender mapping to a TinyAssets subject, founder-owned universe, agent binding, binding revision, membership role, and mapping generation.
- Revalidate current founder ACL, founder-home binding, agent-binding ownership/revision, and mapping status at lookup time.
- Fail closed on missing, revoked, stale, ambiguous, cross-tenant, non-founder, or conflicting mappings, without using message text, mentions, channels, or display names to choose rights.
- Persist content-free mapping history with atomic single-winner creation and generation-aware revocation; do not add a route, MCP handle, custody issuer, runtime activation, or outbound reply.

## Capabilities

### New Capabilities

- `external-app-principal-mapping`: maps authenticated provider installation/workspace/sender evidence to a current founder-owned TinyAssets agent binding without granting downstream custody or execution authority.

### Modified Capabilities

- None. The existing authenticated app-event boundary remains authority-neutral; this change adds a consumer seam without changing its public MCP surface.

## Impact

- New mapping service and SQLite persistence under `tinyassets/` with focused security and concurrency tests.
- Small hardening change to the transient authenticated Slack evidence object so persisted receipts cannot be replayed as authority.
- Consumes existing `founder_home`, `universe_acl`, and `agent_bindings` stores and existing identity/interlocutor semantics.
- No external app activation, secret mutation, deployment, public route, production effect, or packaged mirror change.
