## 1. Specification And Collision Gates

- [x] 1.1 Map full-coverage audit target groups 3, 4, 7, and 8 to their integrated-architecture and legacy-spec provenance.
- [x] 1.2 Compare current canonical and active OpenSpec owners; keep PLAN-gated portability/catalog/private-data work outside this change.
- [x] 1.3 Check candidate moderation, authoring, handoff, and attestation action verbs against `origin/main`; do not introduce standalone advertised MCP handles.
- [x] 1.4 Obtain independent opposite-family architecture-to-requirement review and resolve every overclaim, omission, and ownership collision. Claude Sonnet approved the corrected ownership model on 2026-07-22.

## 2. Moderation And Abuse Response

- [ ] 2.1 Add moderation persistence and invariants in `tinyassets/moderation/models.py`, `tinyassets/moderation/store.py`, and the next numbered storage migration.
- [ ] 2.2 Implement flag, queue, decision, appeal, recusal, moderator-eligibility, and audit services in `tinyassets/moderation/service.py` and `tinyassets/moderation/policy.py`.
- [ ] 2.3 Route moderation actions through existing canonical API handles in `tinyassets/api/` without adding an advertised MCP handle; add web-surface adapters only after the same service boundary exists.
- [ ] 2.4 Add `tests/test_moderation_service.py`, `tests/test_moderation_authority.py`, and `tests/test_moderation_concurrency.py`, including distinct-flagger races, two-reviewer deletion, appeal independence, rate limits, and fail-closed authorization.
- [ ] 2.5 Run §14 moderation proof with concurrent flag/decision/appeal traffic, queue-latency and write-contention bounds, anomaly-volume failure injection, and no lost or duplicated terminal decision.

## 3. Packaged Tray Installation

- [ ] 3.1 Add platform packaging definitions under `packaging/windows/`, `packaging/macos/`, and `packaging/linux/`, with reproducible artifact metadata and signing/notarization hooks.
- [ ] 3.2 Implement first-run account binding, OS-secret-store use, pending-registration recovery, autostart, uninstall, and updater services in `tinyassets/desktop/onboarding.py`, `tinyassets/desktop/credentials.py`, and `tinyassets/desktop/updater.py`.
- [ ] 3.3 Add `.github/workflows/desktop-release.yml` for Windows, macOS, and Linux artifact builds, provenance, signature/notarization verification, staged channels, and rollback evidence.
- [ ] 3.4 Add clean-machine and upgrade tests under `tests/desktop_install/`, covering offline first run, expired auth, double launch, second-machine identity, crash-safe update, rollback, and content-preserving uninstall.
- [ ] 3.5 Prove the <5-minute Tier-2 path and §14 fleet behavior on clean Windows, macOS, and Linux VMs, including concurrent update checks, origin outage, partial rollout, and signed-artifact rejection.

## 4. Node Authoring And Autoresearch

- [ ] 4.1 Add owner-scoped authoring session/event models in `tinyassets/authoring/models.py`, `tinyassets/authoring/store.py`, and the next numbered storage migration.
- [ ] 4.2 Implement inspect/edit/test/publish session behavior in `tinyassets/authoring/service.py`, typed file manifests in `tinyassets/authoring/io.py`, and sandbox policy in `tinyassets/authoring/sandbox.py`.
- [ ] 4.3 Route node and evaluator authoring through existing canonical API handles in `tinyassets/api/extensions.py`; preserve the then-current canonical advertised handle set.
- [ ] 4.4 Add optimization specifications, fixed-evaluator binding, experiment leases/deduplication, budget enforcement, cycle detection, and merge policy in `tinyassets/autoresearch/models.py` and `tinyassets/autoresearch/runner.py`; reuse `tinyassets/runtime/lease_store.py` if the landed distributed-execution contract is semantically compatible.
- [ ] 4.5 Add `tests/test_authoring_sessions.py`, `tests/test_authoring_sandbox.py`, `tests/test_authoring_file_io.py`, `tests/test_evaluator_authoring.py`, and `tests/test_autoresearch_runtime.py`, including adversarial isolation and no-effect dry runs.
- [ ] 4.6 Run §14 authoring/optimization proof: 100 concurrent author sessions, 1,000 isolated sequential sessions with no cross-user bleed, one execution per candidate lease, duplicate-candidate suppression, budget-stop races, and bounded evaluator-cache fan-out.
- [ ] 4.7 Complete a rendered chatbot authoring conversation through the live connector and capture full/diff inspection, file input/output, dry test, explicit publish, and post-fix clean-use evidence.

## 5. Real-World Handoffs And Outcomes

- [ ] 5.1 Add handoff-effect lifecycle models in `tinyassets/handoffs/models.py` and `tinyassets/handoffs/store.py`; extend the existing `outcome_event` registry/evidence history in `tinyassets/api/extensions.py` and the next numbered storage migration rather than creating a second generic outcome registry.
- [ ] 5.2 Implement consent/confirmation checks, receipt-bound handoff creation, deduplication, and provenance linkage in `tinyassets/handoffs/service.py`; route user attestations and handoff evidence transitions through the evolved `tinyassets/api/extensions.py` outcome owner while leaving `gate_events` specialized and separate.
- [ ] 5.3 Implement provider-budgeted polling, signed-webhook handling, backoff, orphan/retraction handling, and enrichment in `tinyassets/handoffs/verify.py`.
- [ ] 5.4 Integrate through `tinyassets/external_effects.py`, `tinyassets/external_write_receipts.py`, and existing API routers without bypassing generic effect authority or adding a standalone MCP handle.
- [ ] 5.5 Integrate handoff/outcome disputes through `tinyassets/moderation/service.py`; add `tests/test_handoff_authority.py`, `tests/test_handoff_receipts.py`, `tests/test_handoff_verification.py`, `tests/test_handoff_concurrency.py`, and focused `tests/test_outcome_events.py` coverage for registry migration, gate-event non-conflation, duplicate submissions, uncertain replies, webhook replay, polling races, provider budgets, disputes, and evidence downgrades.
- [ ] 5.6 Run §14 handoff proof with concurrent same-key submissions, webhook/poll overlap, provider outage/recovery, bounded polling volume at 10× projected load, and exactly one authoritative external effect.
- [ ] 5.7 Complete a rendered chatbot handoff conversation through the live connector and record confirmation, external receipt, linked outcome evidence, later verification transition, and post-fix clean-use evidence.

## 6. Foldback

- [ ] 6.1 Re-run collision checks immediately before every implementation write-set expansion and before canonical sync.
- [ ] 6.2 Strictly validate the full OpenSpec tree, run focused plus security/load suites, and obtain independent diff/code review.
- [ ] 6.3 Sync only capabilities whose implementation and acceptance evidence are complete; split any unfinished capability into a surviving active change.
- [ ] 6.4 Archive the completed change in the implementation landing lane and retire the STATUS claim.
