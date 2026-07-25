## 1. Review and Ownership Gates

- [x] 1.1 Obtain and durably record the Opus 5 current-main ADAPT verdict.
- [x] 1.2 Obtain Opus 5 exact-artifact review of this proposal, design, deltas, and tasks; Opus 5 returned **APPROVE — spec/review-only** on exact adapted head `4fa0dc4e` after the owner-resolution ADAPT, with independent Codex exact-head approval.
- [ ] 1.3a Obtain draft PR #1691 (`constrain-set-engine-provider-authority`) owner acceptance, bound to an exact post-#1727/rebased head SHA, that it owns the generic `setup_required`/held assignment-state contract, provider-destination ceilings, reference-ready assignment CAS/generation, and frozen `ProviderInvocation -> ProviderLaunchHandle` barrier. This change owns the `llm_api_key`-typed refusal and writes no provider-routing delta; landed Slice A0/provider-auth isolation owns the general no-maintainer-route invariant.
- [ ] 1.3b Require #1691 to resolve its `ProviderInvocation` material-versus-reference ambiguity: requester-owned local invocation carries only an opaque binding reference and credential/auth provenance, and only executor-local `start()` resolves native secret material.
- [ ] 1.4 Obtain `openspec/specs/distributed-execution/spec.md` and B2 production-authority owner acceptance that `runner/v1` remains an opaque nine-field carrier, requester-owned local invocation uses draft PR #1691's launch barrier, accepted-market execution uses its production B2 authority, and fake-only/production-denied D0 is not ordinary requester-provider authority.
- [ ] 1.5a Obtain PR #1736 owner acceptance that its account refresh-token lifecycle, stable account-token namespace, native-backend allowlist, and client-side `OriginClient` protocol remain unchanged and may be consumed rather than duplicated.
- [ ] 1.5b Keep the disjoint random provider-secret namespace, bounded local pending index, pending/committed/tombstoned state, commit-token acknowledgement, split-brain compare-clear, wired deletion, and safe rotation owned by this change.
- [ ] 1.5c Create and obtain owner acceptance for `bind-host-principal-to-account`, which owns the authenticated production server-side principal-to-host route, stable server-attested host principal, idempotent re-registration/revocation, and authenticated binding read without claiming PR #1736's desktop files.
- [ ] 1.6 Record #1469 as source-only/non-adoptable and #1606 as predecessor context only in every implementation handoff.
- [ ] 1.7 Obtain explicit acceptance from `openspec/changes/universe-creation/`, `openspec/changes/retire-legacy-live-mcp-tools/`, and the live-interface owner for one non-secret successor setup route before hidden `universe/set_engine` unregistration.
- [ ] 1.8 Obtain `openspec/changes/test-identity-and-reset/` owner acceptance that global reset cannot clear, normalize, or delete a legacy `llm_api_key` outside this retirement saga.
- [ ] 1.9 Obtain `openspec/changes/retire-legacy-live-mcp-tools/` live-MCP owner and production gateway/deployment owner acceptance of an inventory for every TinyAssets-controlled gateway/access log, MCP middleware/request capture, trace, ledger, exception, and crash sink; explicitly exclude client-owned upstream chatbot transcript bytes that TinyAssets cannot redact.

## 2. Canonical Setup Surface

- [ ] 2.1 Present typed provider-binding setup through `write_graph(target=universe)` as the preferred successor candidate—not current behavior—and have the owning changes specify operation discrimination, auth/scope, idempotency, create-vs-update semantics, typed response, and malformed/unknown-op refusal without a new MCP verb.
- [ ] 2.2 Claim `tinyassets/api/prompts.py` and its packaged mirror after current owners release them; remove every instruction to supply a raw bring-your-own API key through MCP while preserving separately owned subscription setup guidance.
- [ ] 2.3 Add RED prompt/schema tests proving requester-facing guidance contains no request for a raw API key and contains only authenticated local setup and accepted market/self-host routes; preserve separately owned subscription setup guidance.

## 3. RED Runtime and Migration Proofs

- [ ] 3.1 Add a non-vacuous mutation test proving an unsupported `llm_api_key` field returns the existing setup-required hold before config, vault, assignment, ledger, or provider mutation.
- [ ] 3.2 Add regression guards proving TinyAssets stops eliciting, rejects without echo, and omits a raw-key canary from every inventoried TinyAssets-owned response, prompt, gateway/access log, MCP middleware/request capture, ledger, structured log, exception, trace, and crash artifact; do not claim control over client-owned upstream chatbot transcripts.
- [ ] 3.3 Add tests proving no production path can create a new `llm_api_key` while preserving the canonical Codex `auth_json_b64` non-empty strict-base64 valid-JSON write-time `ValueError`, exact Claude effective-service `claude` first-record/direct-field/token_b64/secret_b64 permissive-decoder behavior, VCS, and social behavior.
- [ ] 3.4 Add binding tests for missing/empty/wrong principal/wrong universe/wrong provider/wrong host/wrong scope/stale generation/expired/tombstoned references, each with zero provider calls and no ambient fallback.
- [ ] 3.5 Add a table-driven test for every legal and illegal saga edge across `discovered`, `held`, `notified`, `replacement_pending`, `replacement_verified`, `rotation_required`, `revoked_upstream`, `cutover_committed`, `artifacts_deleted`, `record_deleted`, `closed`, `closed_without_replacement`, and `held_ambiguous`; test `failed_held(last_state, failure_class)` only as a non-advancing overlay, crash-inject every legal edge, and prove monotonic idempotent resume.
- [ ] 3.6 Add opaque dual-loader tests proving retained `llm_subscription`/`vcs`/`social` one-record, bulk, and empty operations remain usable under draft PR #1691's exclusive assignment lock while every legacy `llm_api_key` object byte slice/order/slot/digest remains exact; malformed, unclassifiable, or ambiguously spliceable existing state blocks every ordinary write/replacement before the fixed sibling.
- [ ] 3.7 Add metadata-only inventory, expected-digest/generation CAS, replacement verification, cutover, compare-and-delete, and no-raw-rollback tests.
- [ ] 3.8 Add artifact tests requiring canonical path, owner, slot, generation, digest, and reference count; changed, shared, mixed-owner, mixed-generation, or ambiguous artifacts remain held and no provider home is recursively deleted.
- [ ] 3.9 Add shared-universe confused-deputy tests proving ACL admin cannot attach or use another principal's binding and concurrent ACL/member changes cannot substitute another credential.
- [ ] 3.10 Add background/resume/retry tests proving the credential principal comes from persisted verified request/assignment authority rather than ambient HTTP, daemon, workspace, or current-member identity.
- [ ] 3.11 Add a named local multi-process pending-enroll/commit-token/local-ack/local-tombstone/late-control-plane-binding/split-brain-compare-clear/rotate/dereference/revoke/delete/retry/stale-host/#1691-launch-barrier proof with one usable binding and no torn read, deadlock, lost rotation, orphaned active reference, or tombstone resurrection.
- [ ] 3.12 Consume and regression-test PR #1736's `tinyassets/desktop/credentials.py` `NativeCredentialStore` allowlist and fail-closed behavior rather than authoring a second backend policy: Windows Credential Manager, macOS Keychain, and Linux Secret Service/libsecret when available; unsupported/headless backend availability yields setup-required with no file/env fallback.
- [ ] 3.13 Add global-reset tests proving `test-identity-and-reset` cannot bypass the saga and malformed or unclassifiable existing vault state blocks reset before any vault, artifact, assignment, or native-store mutation.

## 4. Blocked Runtime Implementation

- [ ] 4.1 **Blocked on draft PR #1691, #1484, and `openspec/changes/universe-creation/`:** remove the supported `llm_api_key` input shape, reject a supplied raw key at ingress, and return #1691's typed `setup_required/held` shape; mirror in lockstep.
- [ ] 4.2 **Blocked on `bind-host-principal-to-account`, PR #1736's accepted client/native-store boundary, and #1691's accepted binding-reference CAS:** implement requester-local API-key enrollment with disjoint random references, an atomic secret-free local pending index, commit-token publication and local acknowledgement, `pending -> committed -> tombstoned` local state, bounded indexed reconciliation, late-binding split-brain compare-clear, wired deletion, and safe rotation.
- [ ] 4.3 **Blocked on distributed-execution/B2 acceptance and draft PR #1691:** implement requester-owned local dereference behind #1691's frozen invocation/launch barrier; keep accepted-market execution blocked on owner-accepted production B2 authority, keep fake-only D0 out of ordinary authority, and keep `SandboxRunner` an opaque carrier.
- [ ] 4.4 **Blocked on tasks 4.1-4.3 and `test-identity-and-reset` adaptation:** implement the replacement-first legacy `llm_api_key` saga, opaque dual loader, exact artifact inventory/refusal, cutover CAS, reset fence, and compare-delete without decode, export, automatic migration, ordinary-write/reset bypass, or raw-material rollback.
- [ ] 4.5 Preserve Slice A0's empty-base child environment and fail closed on any missing custody/authority element with no founder, maintainer, alternate-host, host-home, environment, or market substitution.
- [ ] 4.6 Fix `check_primitive_exists.py` recognition of `_action_<verb>` and action-map entries in a separate narrow tooling lane.

## 5. Verification and Foldback

- [ ] 5.1 Pass all focused RED/GREEN custody, vault, routing, identity, execution-authority, prompt, and migration suites plus mutation probes.
- [ ] 5.2 Pass the named local multi-process concurrency/GC proof and freshness-stamp its environment/date; keep the real full-platform §14/Track J obligation explicitly deferred.
- [ ] 5.3 Prove canonical/plugin byte parity, Ruff/compile/import checks, `git diff --check`, and strict OpenSpec validation.
- [ ] 5.4 Obtain independent exact-head security/correctness/diff review and resolve every finding.
- [ ] 5.5 Sync accepted deltas into canonical specs and archive only after the complete implementation lands; never archive while draft PR #1691's accepted assignment/launch adaptation, the named owner adaptations, or any runtime dependency remains blocked.
- [ ] 5.6 Prove deployed SHA, exact-seven `https://tinyassets.io/mcp`, rendered local-setup/held behavior through the installed TinyAssets connector, and post-fix organic use or leave a dated watch row.
