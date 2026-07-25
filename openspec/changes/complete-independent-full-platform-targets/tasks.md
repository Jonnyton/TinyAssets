## 0. Premise Verification Record

This change is **target-only**: every requirement below section 1 describes
intended future behavior. Nothing in sections 2-5 is built. The notes attached
to each task are premise verification against `origin/main` at the stated date,
not implementation progress.

Note vocabulary:

- **unbuilt-target** — the named file/dir does not exist; the task is live work.
- **path-corrected** — the task named a file that does not exist; the real
  owner is named inline. Implementers MUST use the corrected path.
- **owner-corrected** — the task named a file that *does* exist but attributed
  the wrong responsibility to it; the correct owner is named inline. The old
  path stays valid for what it really owns.
- **in-flight external** — another lane is already writing the named files.
  Do not write them from this change.
- **blocked** — a named host action, credential, or unlanded change gates it.
  A `blocked` label states which *step* is gated, not the whole task, unless
  the whole task is a proof.

Section 0 records verification work only. **No implementation, proof, sync, or
archive task in sections 2-6 is checked by this lane**, and none may be checked
by annotation, delegation, or host-gating — only by landed code plus its named
acceptance evidence. Every one of those 28 tasks remains open.

- [x] 0.1 Premise-verify every unchecked task in sections 2-6 against `origin/main` and label each one unbuilt-target, path-corrected, owner-corrected, in-flight external, or blocked (this lane, 2026-07-24).
- [x] 0.2 Correct the misdirecting task premises, distinguishing absent paths from misattributed ownership: **path-corrected** — 4.4 named `tinyassets/runtime/lease_store.py` and 5.4 named `tinyassets/external_effects.py` / `tinyassets/external_write_receipts.py`, none of which exist; **owner-corrected** — 5.1/5.2 named `tinyassets/api/extensions.py`, which *does* exist and really does route the outcome actions, but is not the `outcome_event` storage owner (`tinyassets/outcomes/schema.py` is).
- [x] 0.3 Record that `moderation-and-abuse-response` implementation has started outside this change (draft PRs #1662, #1667) and fence its tasks so no second lane writes `tinyassets/moderation/`.
- [x] 0.4 Record the host-owned gates in section 3 (platform code-signing identities, Apple notarization account, clean-machine OS matrix) and scope them to the two steps they actually gate — signed publication and the final acceptance proof — so no lane treats buildable packaging work as blocked.
- [x] 0.5 Re-run the pre-claim collision guard for this change's write-set and strict-validate the change (evidence in 6.1/6.2 notes).

## 1. Specification And Collision Gates

- [x] 1.1 Map full-coverage audit target groups 3, 4, 7, and 8 to their integrated-architecture and legacy-spec provenance.
- [x] 1.2 Compare current canonical and active OpenSpec owners; keep PLAN-gated portability/catalog/private-data work outside this change.
- [x] 1.3 Check candidate moderation, authoring, handoff, and attestation action verbs against `origin/main`; do not introduce standalone advertised MCP handles.
- [x] 1.4 Obtain independent opposite-family architecture-to-requirement review and resolve every overclaim, omission, and ownership collision. Claude Sonnet approved the corrected ownership model on 2026-07-22.

## 2. Moderation And Abuse Response

**Fenced 2026-07-24 — do not write `tinyassets/moderation/` from this change.**
Implementation began outside this change on draft PRs #1662 (`codex/moderation-abuse-runtime`)
and #1667 (`codex/moderation-flag-planner`). Both are unmerged drafts. Because
partial moderation code is landing outside this change while its delta spec is
held here, the split obligation in 6.3 is now **live for this capability** and
must be executed before any moderation code merges (see 6.3 note).

- [ ] 2.1 Add moderation persistence and invariants in `tinyassets/moderation/models.py`, `tinyassets/moderation/store.py`, and the next numbered storage migration.
  - _in-flight external (PR #1662)_ — `models.py` and `__init__.py` are on the #1662 branch. `store.py` and the storage migration are still unowned by any open PR.
- [ ] 2.2 Implement flag, queue, decision, appeal, recusal, moderator-eligibility, and audit services in `tinyassets/moderation/service.py` and `tinyassets/moderation/policy.py`.
  - _in-flight external (PR #1662, #1667)_ — `policy.py` on #1662, `service.py` on #1667. Neither is merged; neither claims the full service surface above.
- [ ] 2.3 Route moderation actions through existing canonical API handles in `tinyassets/api/` without adding an advertised MCP handle; add web-surface adapters only after the same service boundary exists.
  - _unbuilt-target_ — no open PR touches `tinyassets/api/` for moderation. Unowned.
- [ ] 2.4 Add `tests/test_moderation_service.py`, `tests/test_moderation_authority.py`, and `tests/test_moderation_concurrency.py`, including distinct-flagger races, two-reviewer deletion, appeal independence, rate limits, and fail-closed authorization.
  - _in-flight external (PR #1662, #1667)_ — `test_moderation_authority.py` on #1662, `test_moderation_service.py` on #1667. `test_moderation_concurrency.py` is unowned; none of the three exists on `origin/main`.
- [ ] 2.5 Run §14 moderation proof with concurrent flag/decision/appeal traffic, queue-latency and write-contention bounds, anomaly-volume failure injection, and no lost or duplicated terminal decision.
  - _unbuilt-target_ — gated on 2.1-2.4.

## 3. Packaged Tray Installation

**Scope guard:** the source-installed tray that ships today is owned by the
canonical `desktop-host-runtime` capability. This section adds packaged
distribution alongside it and MUST NOT rewrite that owner.

**Host-owned gate — scoped to signed publication and final acceptance, not the
whole section.** A Windows Authenticode signing identity, an Apple Developer ID
plus notarization account, and a Linux package signing key are all absent from
the repository's provisioned secrets (`gh secret list`, 2026-07-24: no signing,
notarization, or Apple/Authenticode credential of any kind). What that actually
blocks is narrow: **publishing signed/notarized artifacts a user can install**
(the `SHALL publish` and signed-manifest requirements) and **3.5's final
acceptance proof**, which additionally needs a clean-machine OS matrix.

Buildable before those identities exist, and therefore NOT blocked: 3.1's
packaging definitions and signing/notarization hooks, 3.2's onboarding /
credential-store / updater implementation, 3.4's clean-machine and upgrade
tests (signature- and checksum-verification logic is exercisable with locally
generated test keys; only artifacts users install need production identities),
and a 3.3 release workflow whose signing/publication steps are gated on secret
presence. This is why 3.2 and 3.4 carry a plain `unbuilt-target` label — under
the earlier section-wide blanket that read as a contradiction; the blanket was
the error, not those two labels.

- [ ] 3.1 Add platform packaging definitions under `packaging/windows/`, `packaging/macos/`, and `packaging/linux/`, with reproducible artifact metadata and signing/notarization hooks.
  - _unbuilt-target; signed output only is blocked_ — none of the three platform directories exists. `packaging/` currently holds `claude-plugin/`, `conway/`, `mcpb/`, `registry/`, `INDEX.md`, and `PACKAGING_MAP.md`. The definitions and the signing/notarization hooks are writable now; what the missing host identities gate is emitting a signed artifact through those hooks, not authoring them. Scope note: this absence is specific to native-installer packaging. Connector/plugin packaging (including OAuth code nested under `packaging/claude-plugin/`) already exists and is a different concern — do not read this note as repo-wide absence of packaging or OAuth support.
- [ ] 3.2 Implement first-run account binding, OS-secret-store use, pending-registration recovery, autostart, uninstall, and updater services in `tinyassets/desktop/onboarding.py`, `tinyassets/desktop/credentials.py`, and `tinyassets/desktop/updater.py`.
  - _unbuilt-target_ — `tinyassets/desktop/` holds `__init__.py`, `app.ico`, `create_shortcut.py`, `dashboard.py`, `host_tray.py`, `icon_gen.py`, `launcher.py`, `notifications.py`, `tray.py`. None of the three named modules exists, and the package contains no keyring/Keychain/libsecret, OAuth-callback, notarization, or updater code.
- [ ] 3.3 Add `.github/workflows/desktop-release.yml` for Windows, macOS, and Linux artifact builds, provenance, signature/notarization verification, staged channels, and rollback evidence.
  - _unbuilt-target; depends on 3.1; signed publication is blocked_ — absent from the 31 workflows on `origin/main`. The workflow itself may be added before the signing secrets exist, provided its signing, notarization, and publication steps are gated on secret presence and stable channels are not advertised from unsigned builds. It does not become a red required check by existing: `main`'s protection requires exactly two contexts, `policy` and `Diff scope declared` (verified 2026-07-24), and required checks are an explicit allowlist — a new workflow is only gating if someone adds it.
- [ ] 3.4 Add clean-machine and upgrade tests under `tests/desktop_install/`, covering offline first run, expired auth, double launch, second-machine identity, crash-safe update, rollback, and content-preserving uninstall.
  - _unbuilt-target_ — `tests/desktop_install/` does not exist. Existing `tests/test_desktop.py`, `test_tinyassets_tray*.py`, `test_tray_singleton.py`, and `test_host_uptime_installers.py` cover the source tray, not packaged artifacts; do not extend them to claim packaged coverage.
- [ ] 3.5 Prove the <5-minute Tier-2 path and §14 fleet behavior on clean Windows, macOS, and Linux VMs, including concurrent update checks, origin outage, partial rollout, and signed-artifact rejection.
  - _blocked: host-action_ — requires a provisioned clean-machine OS matrix plus the signing identities above, and the spec forbids satisfying it by build success alone. This is the one section-3 task blocked end-to-end rather than at a step: it is entirely a proof, so it is not startable from a build lane.

## 4. Node Authoring And Autoresearch

- [ ] 4.1 Add owner-scoped authoring session/event models in `tinyassets/authoring/models.py`, `tinyassets/authoring/store.py`, and the next numbered storage migration.
  - _unbuilt-target_ — `tinyassets/authoring/` does not exist. Latest storage migration on `origin/main` is `prototype/full-platform-v0/migrations/008_market_ledger.sql`; take the next free number at implementation time, not now.
- [ ] 4.2 Implement inspect/edit/test/publish session behavior in `tinyassets/authoring/service.py`, typed file manifests in `tinyassets/authoring/io.py`, and sandbox policy in `tinyassets/authoring/sandbox.py`.
  - _unbuilt-target_ — see 4.1. The sandbox requirement interacts with the open universe-engine OS-sandbox concern (STATUS P1, proposal on draft PR #1573): the authoring sandbox must not assume an OS isolation boundary that the platform does not yet have.
- [ ] 4.3 Route node and evaluator authoring through existing canonical API handles in `tinyassets/api/extensions.py`; preserve the then-current canonical advertised handle set.
  - _unbuilt-target_ — `tinyassets/api/extensions.py` exists and is the correct router. The handle set to preserve is the canonical seven (`read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, `get_status`) asserted by `CANONICAL_HANDLES` in `scripts/mcp_public_canary.py` and owned by `openspec/specs/live-mcp-connector-surface/spec.md`.
- [ ] 4.4 Add optimization specifications, fixed-evaluator binding, experiment leases/deduplication, budget enforcement, cycle detection, and merge policy in `tinyassets/autoresearch/models.py` and `tinyassets/autoresearch/runner.py`; reuse the `distributed-execution` lease-store owner if its landed contract is semantically compatible.
  - _unbuilt-target; path-corrected_ — `tinyassets/autoresearch/` does not exist. The task previously named `tinyassets/runtime/lease_store.py`; **that path does not exist** and `openspec/changes/distributed-execution/` is still an active, unarchived change, so the reuse conditional is currently **false**. Re-evaluate the real module path when `distributed-execution` lands; do not create a third general distributed lease mechanism in the meantime.
- [ ] 4.5 Add `tests/test_authoring_sessions.py`, `tests/test_authoring_sandbox.py`, `tests/test_authoring_file_io.py`, `tests/test_evaluator_authoring.py`, and `tests/test_autoresearch_runtime.py`, including adversarial isolation and no-effect dry runs.
  - _unbuilt-target_ — all five are absent from `origin/main`.
- [ ] 4.6 Run §14 authoring/optimization proof: 100 concurrent author sessions, 1,000 isolated sequential sessions with no cross-user bleed, one execution per candidate lease, duplicate-candidate suppression, budget-stop races, and bounded evaluator-cache fan-out.
  - _unbuilt-target_ — gated on 4.1-4.5.
- [ ] 4.7 Complete a rendered chatbot authoring conversation through the live connector and capture full/diff inspection, file input/output, dry test, explicit publish, and post-fix clean-use evidence.
  - _unbuilt-target_ — gated on 4.1-4.6 reaching the live surface. Cannot be satisfied by direct MCP calls or local scripts (AGENTS.md final chatbot-surface rule).

## 5. Real-World Handoffs And Outcomes

- [ ] 5.1 Add handoff-effect lifecycle models in `tinyassets/handoffs/models.py` and `tinyassets/handoffs/store.py`; extend the existing `outcome_event` registry in `tinyassets/outcomes/schema.py` and its router actions in `tinyassets/api/extensions.py`, plus the next numbered storage migration, rather than creating a second generic outcome registry.
  - _unbuilt-target; owner-corrected_ — `tinyassets/handoffs/` does not exist. The correction here is ownership, not a dead path: the task previously located the whole registry in `tinyassets/api/extensions.py`, which **does exist** and correctly owns the router half (`record_outcome` / `list_outcomes` / `get_outcome` plus the `gate_event` actions), but the `outcome_event` DDL and `OutcomeEvent` dataclass live in **`tinyassets/outcomes/schema.py`**. An implementer following the old wording would extend the router and miss the storage owner. Both paths are live; use both, for their respective halves.
- [ ] 5.2 Implement consent/confirmation checks, receipt-bound handoff creation, deduplication, and provenance linkage in `tinyassets/handoffs/service.py`; route user attestations and handoff evidence transitions through the evolved outcome owner (`tinyassets/outcomes/schema.py` + `tinyassets/api/extensions.py`) while leaving `gate_events` specialized and separate.
  - _unbuilt-target; owner-corrected_ — same storage/router split as 5.1; `tinyassets/api/extensions.py` was named and exists, it just is not the storage owner.
- [ ] 5.3 Implement provider-budgeted polling, signed-webhook handling, backoff, orphan/retraction handling, and enrichment in `tinyassets/handoffs/verify.py`.
  - _unbuilt-target_ — see 5.1. No inbound webhook receiver exists on `origin/main` for this to attach to; the transport surface is part of the work, not a given.
- [ ] 5.4 Integrate through the canonical effect owners — the `tinyassets/effectors/` package (including `tinyassets/effectors/authority.py`), `tinyassets/storage/external_write_receipts.py`, and `tinyassets/storage/effector_consents.py` — and existing API routers, without bypassing generic effect authority or adding a standalone MCP handle.
  - _path-corrected_ — the task previously named `tinyassets/external_effects.py` and `tinyassets/external_write_receipts.py`. **Neither path exists.** The real owners are the three modules named above, specified by `openspec/specs/external-effect-adapters/spec.md` and `openspec/specs/external-effect-receipts/spec.md`.
- [ ] 5.5 Integrate handoff/outcome disputes through the moderation service owner; add `tests/test_handoff_authority.py`, `tests/test_handoff_receipts.py`, `tests/test_handoff_verification.py`, `tests/test_handoff_concurrency.py`, and focused `tests/test_outcome_events.py` coverage for registry migration, gate-event non-conflation, duplicate submissions, uncertain replies, webhook replay, polling races, provider budgets, disputes, and evidence downgrades.
  - _partially fenced; unbuilt-target_ — the dispute half depends on `tinyassets/moderation/service.py`, which is in-flight external on draft PR #1667 (see section 2 fence). Do not write it from this change. All five named test files are absent from `origin/main`.
- [ ] 5.6 Run §14 handoff proof with concurrent same-key submissions, webhook/poll overlap, provider outage/recovery, bounded polling volume at 10× projected load, and exactly one authoritative external effect.
  - _unbuilt-target_ — gated on 5.1-5.5.
- [ ] 5.7 Complete a rendered chatbot handoff conversation through the live connector and record confirmation, external receipt, linked outcome evidence, later verification transition, and post-fix clean-use evidence.
  - _unbuilt-target_ — gated on 5.1-5.6 reaching the live surface.

## 6. Foldback

- [ ] 6.1 Re-run collision checks immediately before every implementation write-set expansion and before canonical sync.
  - _recurring obligation; latest run 2026-07-24_ — `python scripts/claim_check.py --provider claude-o5-independent-targets --check-files "openspec/changes/complete-independent-full-platform-targets/"` returned `CLEAR: no overlap with another provider's claimed/in-flight Files`. This stays unchecked because it must re-run at each future expansion, not once.
- [ ] 6.2 Strictly validate the full OpenSpec tree, run focused plus security/load suites, and obtain independent diff/code review.
  - _partially satisfied 2026-07-24_ — `openspec validate complete-independent-full-platform-targets --strict` passes, and the full-tree strict validation result is recorded in the lane report. Two independent cross-family reviews of this lane's premise verification and completion model both returned **adapt** (Codex, 2026-07-24). Round 1 confirmed the 4.4 and 5.4 corrections and the 5.1/5.2 storage owner, rejected any checking-off of runtime tasks by delegation or annotation, and required that 6.1-6.4 stay open. Round 2 reviewed the resulting commit and required two further folds, both verified against `origin/main` and applied above: **(a)** 5.1/5.2 were misfiled as `path-corrected` when the named `tinyassets/api/extensions.py` exists and the real defect was misattributed ownership — now `owner-corrected`, with 0.2 and the note vocabulary reworded; **(b)** the section-3 host gate was recorded as a section-wide blanket when only signed publication and 3.5's final acceptance proof are host-owned — now scoped, with 3.1/3.3 relabeled and the false "permanently red required check" claim replaced by the actual protection contexts. Round 2 also caught a miscount: 31 workflows on `origin/main`, not 32. The focused/security/load suites and code-to-requirement review of the capabilities themselves cannot be satisfied while sections 2-5 are unbuilt; this stays unchecked as the implementation foldback gate.
- [ ] 6.3 Sync only capabilities whose implementation and acceptance evidence are complete; split any unfinished capability into a surviving active change.
  - _disposition recorded 2026-07-24: sync nothing_ — zero of the four capabilities has any implementation on `origin/main`, so no delta may be synced and the change stays active. **The split obligation is now live for `moderation-and-abuse-response`:** its implementation is proceeding on external draft PRs #1662/#1667 while its delta spec is held here, which is exactly the partial-implementation drift design.md warns against. Before any moderation code merges, that delta, its section 2 tasks, and its acceptance evidence must move into an independently complete successor change. **This lane recorded that obligation but did not discharge it**, because the moderation write-set is fenced to PRs #1662/#1667; a split done from here would collide with them. Discharging it requires the full delegation shape — create the successor, physically transfer the `moderation-and-abuse-response` delta and its section 2 tasks out of this change, and assign implementation, acceptance, sync, and archive ownership — not a naming note. The remaining three capabilities have no implementation lane and stay here.
- [ ] 6.4 Archive the completed change in the implementation landing lane and retire the STATUS claim.
  - _not applicable yet_ — archiving now would sync four target-only deltas into canonical specs as as-built truth. Blocked until 6.3's disposition is "everything complete", which it is not.
