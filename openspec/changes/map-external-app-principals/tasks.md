## 1. Evidence boundary

- [x] 1.1 Harden `tinyassets/app_event_ingress.py` so `AuthenticatedAppEvent` is verifier-sealed, deeply immutable, and snapshots Slack `event.user` as `external_sender_id`; preserve existing authentication and replay behavior with red/green regressions in `tests/test_app_event_ingress.py`.
- [x] 1.2 Add mapping-domain types and validation in `tinyassets/app_principal_mapping.py`, including trusted target shape, typed denial/conflict errors, canonical membership-generation derivation, and a result that contains no message or credential material.

## 2. Durable mapping lifecycle

- [x] 2.1 Implement `tinyassets/storage/app_principal_mappings.py` with a lazy SQLite schema, canonical record digest, active-tuple uniqueness fence, exact-target idempotency, conflicting-target rejection, generation-aware revocation, and integrity checks.
- [x] 2.2 Add `AppPrincipalMappingService` provisioning and resolution that consumes only sealed events, calls a trusted setup resolver, revalidates founder-home/admin-ACL/binding-owner/status/revision and ACL-derived membership generation, and fails closed on ambiguity or staleness.
- [x] 2.3 Add `tests/test_app_principal_mapping.py` covering forged/deserialized evidence, message-field irrelevance, missing/cross-tenant/non-founder targets, ACL revoke/regrant, binding revision/owner changes, same-target replay, conflicting target, revocation, and 64-way concurrent duplicate races.

## 3. Verification and handoff

- [ ] 3.1 Run focused app-event/mapping tests, adjacent outbound/interlocutor/custom-agent regressions, Ruff, compile/import, `git diff --check`, strict OpenSpec validation, and confirm no new route/MCP handle or packaged mirror change.
- [ ] 3.2 Obtain an independent fresh-context exact-head security/domain review, resolve all blocking findings, and record the verification evidence in the PR before foldback.
- [ ] 3.3 On verified land, sync the new capability spec into `openspec/specs/external-app-principal-mapping/spec.md`, archive the change, retire this STATUS/worktree claim, and update the V1 monitor to the custody/governed-reply handoff.
