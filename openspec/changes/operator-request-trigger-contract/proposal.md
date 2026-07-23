## Why

Permission consolidation made priority submission capability-based and emits `operator_request`, but the durable queue rejects that trigger and the dispatcher neither enables nor scores it. The submission path catches the rejection after writing `requests.json`, so it can report pending work with no BranchTask and strand an authorized user's request.

This is a complete-system uptime break: accepted work must remain durably visible with zero hosts online and become claimable when eligible capacity returns.

## What Changes

- Define `operator_request` as the canonical BranchTask tier for a positive-weight request admitted by an authenticated subject holding ordinary submit authority, universe write/admin ACL, and a live universe-scoped `submit_priority_request` grant; weight zero is an explicit ordinary opt-out, and host/runtime identity alone grants no priority.
- Define issuance, expiry, revocation, and generation semantics for that priority grant. Only a universe administrator who also holds the capability-management action scope may grant or revoke it, and wildcard priority grants are forbidden.
- Require the task source, accepted priority weight, actor, tenant/universe, and authorization evidence to derive from one request-scoped admission decision. Callers cannot select a trigger tier or provide their own evidence.
- Put the accepted-write boundary in a transactional protocol-v2 aggregate that atomically creates the existing canonical Request entity, its admission receipt, and its v2 BranchTask. Legacy JSON queues remain the v1 epoch; new v2 work is stored in a namespace v1 binaries cannot open or claim.
- Make operator tasks valid, enabled, scored, and disclosed consistently by queue validation, dispatcher configuration, queue/status reads, cloud wakeup, and runtime selection. A forged or receipt-less operator row is quarantined individually without poisoning valid queue rows.
- Stop new submission paths from emitting identity-derived `host_request`; keep already-persisted host rows readable/pickable at the legacy top band until an inventory-backed retirement or repair handles them without fabricating operator authorization evidence.
- Preserve requester-directed daemon assignments as `owner_queued`; a positive bounded boost requires the same live priority grant, while zero remains ordinary and unboosted.
- Require a scope-bound, body-bound admission key on the canonical request-write surface. Retries return the original committed pair without duplication, while changed-body reuse conflicts.
- Replace the current FIFO claims with an exact admission result containing committed state, both IDs, tier, accepted weight, cap, and policy version. The response exposes no request-file position or promise that work is “next.”
- Preserve zero-host behavior: accepted tasks remain durable and visibly pending without using platform-maintainer compute, then enter the transactional single-winner epoch-2 claim path when an eligible daemon is available.
- Define the epoch-2 claim as internal scheduling reservation only; distributed execution still requires the active B2 signed owner/daemon/job/capsule/lease/fence authority and cannot treat an admission or heartbeat row as positive execution authority.
- Gate operator writes behind readers-first protocol-v2 deployment evidence while allowing pinned legacy workers to coexist on the isolated v1 epoch. Require bounded priority values plus authorization, revocation, ordering, transaction recovery, mixed-version, and the exact §14 500-daemon/1,000-request proof before activation.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: Add the authenticated operator trigger tier, transactional admission aggregate and queue epoch, row-wise quarantine, consistent dispatcher observability, mixed-version behavior, signed-execution handoff, and zero-host/concurrency requirements.
- `identity-auth-and-access-control`: Define the composed admission verdict and the lifecycle and administration of exact-universe `submit_priority_request` grants.
- `live-mcp-connector-surface`: Define the canonical `write_graph(target="request")` admission-key input and honest result schema without FIFO scheduling claims.

## Impact

Planning in this lane affects the future contract for the shared SQLite schema/storage boundary, target Postgres `request_inbox`, `tinyassets/api/permissions.py`, `tinyassets/api/universe.py`, `tinyassets/universe_server.py`, epoch-2 BranchTask storage, `tinyassets/dispatcher.py`, `tinyassets/api/status.py`, `tinyassets/cloud_worker.py`, capability administration, generated runtime mirrors, and focused tests. Runtime implementation depends on the active `distributed-execution` signed B2 authority contract, must reconcile open PR overlap (#1606, #1472, and #1464), and must re-claim exact implementation files. This proposal changes no live route, feature flag, provider credential, compute source, or deployment state.
