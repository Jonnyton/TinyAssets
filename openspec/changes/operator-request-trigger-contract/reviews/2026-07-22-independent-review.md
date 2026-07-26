# Independent review — operator request trigger contract

- Reviewed: 2026-07-22 PT / 2026-07-23 UTC
- Scope: proposal, design, daemon/identity/live-MCP deltas, and tasks
- Runtime code changed: no
- Final verdict: APPROVE from all three reviewers; no Critical or Important findings remain

## Review lanes

1. `openspec_coverage_residuals` reviewed Request/admission/task domain
   ownership, SQLite bridge behavior, Postgres mapping, OKF separation,
   migration entry points, and implementation paths.
2. `openspec_change_ownership_review` reviewed identity composition, grant
   lifecycle, replay non-enumeration, public MCP schema, dispatcher preservation,
   soul-affinity behavior, and signed distributed-execution handoff.
3. `provider_routing_gap_audit` reviewed epoch isolation, worker protocol
   evidence, rollout enforceability, quarantine, zero-capacity behavior, and
   the literal §14 load-proof denominator.

## Material findings resolved

- Replaced impossible dual-JSON atomicity with one transactional logical
  Request/admission/epoch-2 task aggregate.
- Isolated epoch 2 from v1 claim code; v2 workers drain both epochs.
- Reconciled the existing local `user_requests` entity and the hosted
  Postgres `request_inbox` one-row Request/BranchTask mapping.
- Preserved the canonical ordinary fine-grained-or-coarse scope rule while
  making priority elevation and capability administration exact-grant
  exceptions.
- Made weight zero an explicit ordinary opt-out; positive/no-grant,
  positive/gate-off, revocation, and exclusive expiry outcomes are exact.
- Restored every unchanged canonical dispatcher clause/scenario and retained
  soul affinity as advisory, bounded, and fail-open.
- Defined epoch-2 claim as internal scheduling only; signed B2
  owner/daemon/job/capsule/lease/fence authority remains mandatory before
  distributed execution.
- Required continuous compatible capacity and durable claims for all 1,000
  canonical storm requests, with full-denominator dispatch p99 below three
  seconds.
- Corrected the active schema initializer and restart-registration file paths.

## Fresh evidence

```text
openspec status --change operator-request-trigger-contract
  4/4 artifacts complete

openspec validate operator-request-trigger-contract --strict
  Change 'operator-request-trigger-contract' is valid

openspec validate --all --strict
  Totals: 35 passed, 0 failed

git diff --check
  clean
```

Publication remains planning-only. Runtime application still requires the
tasked collision checks, inventory, signed distributed-execution composition,
tests, exact §14 evidence, public chatbot verification, and host-approved
cutover.
