## 1. Ownership and Frozen Security Contract

- [x] 1.1 Record the current owner/code/spec map and the no-overlap boundary with merged #1736, host-pool sessions, #1784 provider authority, and draft PR #1746 custody.
- [x] 1.2 Freeze the pre-RED protocol: exact sole `WORKOS_HOST_BINDING_RESOURCE`; interactive `auth_time` (never `iat`/refresh); `(issuer, sub)` ownership; per-operation scope/wire matrix; Ed25519/RFC 8037; RFC 8785 `HostProofV1`; separate one-use challenge/nonce limits; fresh-challenge idempotent retry; 90-day lifecycle; atomic recovery; generation fencing; privacy retention; mixed-version rollback; and reproducible numeric `docs/design-notes/2026-04-18-full-platform-architecture.md` §14 proof.
- [x] 1.3 Obtain the merged #1736 packaged-tray owner's acceptance to adapt its `OAuthConfig`, RFC 8707 resource handling, `OriginClient`, subject-pinned `bound` state, and onboarding protocol for challenge/signature/principal ID+generation while this lane does not claim desktop runtime files or account-token custody.
- [x] 1.4 Obtain identity/auth and daemon-host-pool owner acceptance for a route-local exact-audience validator, interactive-`auth_time` and personal/org scope provisioning, verified-subject ownership, stable storage, private inventory, and session-generation linkage.
- [x] 1.5 Obtain draft PR #1746 owner acceptance that custody separately checks host-principal and provider-assignment generations while retaining all provider-secret/reference lifecycle.
- [x] 1.6 Obtain Opus 5 current-main exact-artifact approval after resolving every ADAPT.
- [x] 1.7 Obtain independent latest-Codex security/domain/diff approval of the same exact artifact.
- [x] 1.8 Re-run claim collision checks and claim exact runtime/migration/test files only after tasks 1.3-1.7; until then runtime, canonical sync/archive, deployment, and rollout are unauthorized.

## 2. RED Contract and Security Proofs

- [x] 2.1 **Blocked on 1.3-1.8:** add failing tests proving only TLS `Authorization: Bearer` with the configured issuer + exact sole host-binding audience + non-empty WorkOS `sub` owns a principal; MCP-only, MCP+host, extra/wrong/missing/no-audience, cookie/query/CORS/ambient authority, missing/stale `auth_time`, fresh `iat` from refresh/non-interactive grants, malformed `org_id`, body owner, environment, process, universe ACL, anonymous, and maintainer identity fail before mutation.
- [x] 2.2 Add failing Ed25519/RFC 8037 and RFC 8785 `HostProofV1` tests covering exact DTO/route/scope/signature-role matrix, same-input dual-key rotation, missing/extra/duplicate/swapped/same-key signatures, signing bytes, domain separation, duplicate JSON keys, Unicode variants, invalid key material, algorithm confusion, TTL, one-use nonce, every bound field, separate challenge/nonce limits, replay, and non-enumerating timing/shape.
- [x] 2.3 Add failing retry/crash/concurrency tests proving fresh-challenge response-loss recovery, changed-body conflict, 24-hour idempotency expiry, one same-subject/key winner across server instances, distinct per-device principals, and non-enumerating cross-subject key-reuse refusal.
- [x] 2.4 Add failing private-inventory tests for subject-only bounded cursor pagination (25 default/100 maximum), lost-device discovery, owner/query injection, cross-subject cursor, MCP-audience refusal, management-field allowlist, and proof that results grant no device/consumer authority.
- [x] 2.5 Add failing lifecycle tests for 90-day expiry, final-30-day renewal, terminal key/ID rules, exact generation CAS, idempotent revoke, role-correct same-input dual-key rotation proof, atomic response-loss-safe recovery replacement, bounded device labels, and prospective in-flight fencing.
- [ ] 2.6 Add failing host-pool composition tests proving insert-always sessions, current principal+generation on authenticated register/heartbeat/exact-idempotent-deregister, heartbeat's fresh-nonce monotonic database-time `updated_at` update and inability to mutate any other authority, sibling-session preservation, mixed-version rollback, zero-host durability, and unattested legacy/dev ineligibility.
- [ ] 2.7 Add failing privacy tests for 24-hour challenge/idempotency deletion, 30-day terminal-key/account deletion, export, legal-hold visibility, RFC 7638 versus log-HMAC separation, log-secret rotation, and absence of tokens/keys/proofs/content from observability.
- [ ] 2.8 Add failing consumer tests proving a principal alone grants no downstream authority and #1746 must independently check host-principal generation and provider-assignment generation from trusted control-plane state.

## 3. Blocked Runtime Implementation

- [x] 3.1 **Blocked on section 1 and RED evidence:** implement a route-local WorkOS validator using `WORKOS_AUTHKIT_DOMAIN` plus mandatory `WORKOS_HOST_BINDING_RESOURCE`; never modify or reuse the global MCP provider.
- [ ] 3.2 Add typed principal/challenge/nonce/idempotency/tombstone storage and readers behind disabled writers with exact uniqueness, retention, account-export/deletion, and mixed-version behavior.
- [ ] 3.3 Implement authenticated challenge/register, bounded self-inventory, exact read, revoke, rotate, renew, and recovery routes with the frozen proof/scopes and no owner selector.
- [ ] 3.4 Link authenticated host-pool sessions to stable principal+generation without changing insert-always registration or exact deregistration; keep legacy/dev rows unattested.
- [ ] 3.5 Coordinate the accepted #1736 owner adaptation for resource-indicator authorization/refresh, challenge signing, native key custody, and principal-bearing response; never edit those desktop files from this lane.
- [ ] 3.6 Coordinate #1746 to verify both independent generations and trusted control-plane evidence; this lane never owns provider secrets/references or assignment state.
- [ ] 3.7 Regenerate packaged runtime mirrors only for canonical runtime files actually changed and prove byte parity.

## 4. Verification and Foldback

- [ ] 4.1 Pass focused identity, proof, inventory, lifecycle, host-pool, privacy, consumer-authority, migration, rollback, packaged-parity, and mutation tests.
- [ ] 4.2 In a separate Supabase test project with at least three server processes, pass 500 clients/subjects across 50 source-network partitions and the exact reproducible 1,000-request five-minute fixture (125 initial enrollment challenges + 225 operation nonces issued in the final 30 setup seconds and consumed in the first 60 timed seconds; 125 retry challenges issued only after simulated response loss; 175 timed operation nonces; 300/250/150/150/150 submix with 50/50/50 session register/heartbeat/deregister): successful-request p95 <1.5 s, p99 <3 s, zero unexpected responses or lost/duplicate authority, plus the separate one-over-limit `429` abuse phase and zero maintainer credential/quota/model/compute use.
- [ ] 4.3 Pass Ruff/compile/import, schema/migration, staged or committed `git diff --check`, strict target/all-item OpenSpec validation, and the canonical STATUS `<=60`-line budget without retiring unrelated steering.
- [ ] 4.4 Obtain exact-head approvals from current Claude Opus 5 and latest Codex after implementation; self-review alone is insufficient.
- [ ] 4.5 Sync accepted deltas into canonical specs and archive only with the complete landed implementation; never archive this planning lane while owner/runtime/load gates remain open.
- [ ] 4.6 Prove deployed SHA/receipt, packaged onboarding, and unchanged exact `TinyAssets`/seven-handle `https://tinyassets.io/mcp` surface, plus rendered tray-to-chatbot behavior and post-fix organic use or a dated monitoring row.
