## 1. Evidence boundary

- [x] 1.1 Harden `tinyassets/app_event_ingress.py` so `AuthenticatedAppEvent` is verifier-sealed, deeply immutable, and snapshots Slack `event.user` as `external_sender_id`; preserve existing authentication and replay behavior with red/green regressions in `tests/test_app_event_ingress.py`.
- [x] 1.2 Add mapping-domain types and validation in `tinyassets/app_principal_mapping.py`, including trusted target shape, typed denial/conflict errors, canonical membership-generation derivation, and a result that contains no message or credential material.

## 2. Durable mapping lifecycle

- [x] 2.1 Implement `tinyassets/storage/app_principal_mappings.py` with a lazy SQLite schema, canonical record digest, active-tuple uniqueness fence, exact-target idempotency, conflicting-target rejection, generation-aware revocation, and integrity checks.
- [x] 2.2 Add `AppPrincipalMappingService` provisioning and resolution that consumes only sealed events, calls a trusted setup resolver, revalidates founder-home/admin-ACL/binding-owner/status/revision and ACL-derived membership generation, and fails closed on ambiguity or staleness.
- [x] 2.3 Add `tests/test_app_principal_mapping.py` covering forged/deserialized evidence, message-field irrelevance, missing/cross-tenant/non-founder targets, ACL revoke/regrant, binding revision/owner changes, same-target replay, conflicting target, revocation, and 64-way concurrent duplicate races.

## 3. Verification and handoff

- [x] 3.1 Focused app-event/mapping tests (31), adjacent custom-agent/interlocutor regressions, Ruff, compile, diff check, strict OpenSpec, and no-route/no-MCP/no-mirror scope all passed on exact head `0f5b95aeb2e66a88355f2ce81d854c053a204e60`.
- [x] 3.2 Independent Claude/Sonnet exact-head security review approved `0f5b95aeb2e66a88355f2ce81d854c053a204e60`; the review found no blocking or non-blocking findings.
- [x] 3.3 PR #2256 merged as `6b65b3fc`; the capability spec was synced and this change archived on 2026-08-04. STATUS/worktree retirement and the V1 custody/governed-reply handoff are recorded by this foldback.
