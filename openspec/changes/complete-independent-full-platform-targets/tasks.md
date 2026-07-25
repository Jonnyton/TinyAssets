## 0. Premise Verification Record

This change was **target-only** when written: every requirement below section 1
described intended future behavior. As of 2026-07-25 that is no longer uniformly
true — `node-authoring-and-autoresearch` tasks 4.1-4.3 have landed code (see their
notes) — but the rest of the change is still target-only, and the delta specs stay
unsynced until each capability's acceptance evidence lands. The notes attached to
each task are premise verification against `origin/main` at the stated date plus,
where marked `landed`, the implementation evidence.

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
archive task in sections 2-6 was checked by the premise-verification lane
(2026-07-24)**, and none may be checked by annotation, delegation, or
host-gating — only by landed code plus its named acceptance evidence.

Update 2026-07-25 (node-authoring implementation lane): **4.1, 4.2, and 4.3 are
now checked on landed code plus the named test evidence** recorded in their notes;
the moderation capability was split out of section 2 (task 6.3 discharge). Every
other implementation, proof, sync, and archive task remains open, and the rule
above still governs them.

- [x] 0.1 Premise-verify every unchecked task in sections 2-6 against `origin/main` and label each one unbuilt-target, path-corrected, owner-corrected, in-flight external, or blocked (this lane, 2026-07-24).
- [x] 0.2 Correct the misdirecting task premises, distinguishing absent paths from misattributed ownership: **path-corrected** — 4.4 named `tinyassets/runtime/lease_store.py` and 5.4 named `tinyassets/external_effects.py` / `tinyassets/external_write_receipts.py`, none of which exist; **owner-corrected** — 5.1/5.2 named `tinyassets/api/extensions.py`, which *does* exist and really does route the outcome actions, but is not the `outcome_event` storage owner (`tinyassets/outcomes/schema.py` is).
- [x] 0.3 Record that `moderation-and-abuse-response` implementation has started outside this change (draft PRs #1662, #1667) and fence its tasks so no second lane writes `tinyassets/moderation/`. **Superseded 2026-07-25:** the fence now lives with the capability in `openspec/changes/moderation-and-abuse-response/` (see section 2).
- [x] 0.4 Record the host-owned gates in section 3 (platform code-signing identities, Apple notarization account, clean-machine OS matrix) and scope them to the two steps they actually gate — signed publication and the final acceptance proof — so no lane treats buildable packaging work as blocked.
- [x] 0.5 Re-run the pre-claim collision guard for this change's write-set and strict-validate the change (evidence in 6.1/6.2 notes).

## 1. Specification And Collision Gates

- [x] 1.1 Map full-coverage audit target groups 3, 4, 7, and 8 to their integrated-architecture and legacy-spec provenance.
- [x] 1.2 Compare current canonical and active OpenSpec owners; keep PLAN-gated portability/catalog/private-data work outside this change.
- [x] 1.3 Check candidate moderation, authoring, handoff, and attestation action verbs against `origin/main`; do not introduce standalone advertised MCP handles.
- [x] 1.4 Obtain independent opposite-family architecture-to-requirement review and resolve every overclaim, omission, and ownership collision. Claude Sonnet approved the corrected ownership model on 2026-07-22.

## 2. Moderation And Abuse Response — SPLIT OUT 2026-07-25

**This capability no longer lives in this change.** Task 6.3's split obligation
was discharged on 2026-07-25: `specs/moderation-and-abuse-response/spec.md` and
the five implementation tasks that were here moved (via `git mv` for the spec, so
the diff reads as a rename and the completed requirement review carries over) to
the surviving active change **`openspec/changes/moderation-and-abuse-response/`**,
which also carries the in-flight fence for PRs #1662/#1667 and the named
implementation / acceptance / sync / archive ownership.

Do not re-add moderation tasks or a moderation delta here. The only moderation
reference this change retains is the *dependency* in task 5.5 (handoff/outcome
disputes read `tinyassets/moderation/service.py`) — a read of the successor
change's owner, not shared ownership.

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

- [x] 4.1 Add owner-scoped authoring session/event models in `tinyassets/authoring/models.py`, `tinyassets/authoring/store.py`, and the next numbered storage migration.
  - _landed 2026-07-25_ — `models.py` (records + one path-scoped edit grammar + pure validation) and `store.py` (owner-scoped SQLite: sessions, events, versions, file handles, confirmations; compare-and-swap draft advance; immutable versions). Migration is `prototype/full-platform-v0/migrations/012_authoring_sessions.sql` — the number-note in the 2026-07-24 premise pass said `008_market_ledger.sql`, which was already stale (the real highest on `origin/main` is `009_market_ledger.sql`); 010/011 are held by parallel lanes, so this took **012** and the numbering gap is intentional. Evidence: `tests/test_authoring_sessions.py` (30 tests, incl. a store-level CAS test that holds independently of the service pre-check), `tests/test_authoring_scale.py` contiguous-event proof.
- [x] 4.2 Implement inspect/edit/test/publish session behavior in `tinyassets/authoring/service.py`, typed file manifests in `tinyassets/authoring/io.py`, and sandbox policy in `tinyassets/authoring/sandbox.py`.
  - _landed 2026-07-25_ — full/diff/summary/history inspection with anchored diffs that fail explicitly on a missing anchor; atomic edit batches (one event per batch, pure application so a rejected batch cannot mutate the draft); typed manifests binding attachments to expiring owner-scoped `fh_*` handles with no path in the definition; simulated-by-default effects with secret redaction, deny-first network decisions, budget ledger, and single-use per-run confirmation for irreversible effects. **The OS-sandbox honesty constraint is honored**: `sandbox.isolation_report()` reports `in_process_confined` unless the shipped `bwrap` probe says otherwise, and a draft declaring `requires_os_isolation` is refused rather than silently run in-process (STATUS P1 stays true; this lane does not claim to close it). Evidence: `tests/test_authoring_file_io.py` (21), `tests/test_authoring_sandbox.py` (25), `tests/test_evaluator_authoring.py` (13), plus a 16-mutation probe confirming each invariant's test goes red when the invariant is broken. Cross-family review (Codex, 2026-07-25) found and this lane fixed one real defect: a draft accepted and persisted inline credential material (`sandbox_policy.credentials` echoed back in the owner's full view and edit-event payload); declaration slots that would carry secret *material* are now refused outright instead of stored-then-redacted, while `credential_class` stays legal.
- [x] 4.3 Route node and evaluator authoring through existing canonical API handles in `tinyassets/api/extensions.py`; preserve the then-current canonical advertised handle set.
  - _landed 2026-07-25_ — seven `extensions` actions (`authoring_start` / `_inspect` / `_edit` / `_test` / `_confirm_effect` / `_publish` / `_list`) dispatch through the existing router. **No new advertised handle and no widened tool signature**: each parameter reuses an existing `extensions` kwarg (documented in both the router arm and `tinyassets/authoring/service.py`), the same technique as the effector-consent actions, so `universe_server.py` is untouched. Action-scope rows derive automatically because `tinyassets/auth/provider.py` now includes the authoring table (start/edit/publish/confirm = write, test = costly, inspect/list = read) — without that, `require_action_scope` would fail closed in production. Evidence: `test_authoring_actions_add_no_advertised_handle` asserts the advertised set is exactly the canonical seven; `test_authoring_actions_are_listed_and_scope_derived` asserts the derived effects.
- [ ] 4.4 Add optimization specifications, fixed-evaluator binding, experiment leases/deduplication, budget enforcement, cycle detection, and merge policy in `tinyassets/autoresearch/models.py` and `tinyassets/autoresearch/runner.py`; reuse the `distributed-execution` lease-store owner if its landed contract is semantically compatible.
  - _unbuilt-target; path-corrected_ — `tinyassets/autoresearch/` does not exist. The task previously named `tinyassets/runtime/lease_store.py`; **that path does not exist** and `openspec/changes/distributed-execution/` is still an active, unarchived change, so the reuse conditional is currently **false**. Re-evaluate the real module path when `distributed-execution` lands; do not create a third general distributed lease mechanism in the meantime.
- [ ] 4.5 Add `tests/test_authoring_sessions.py`, `tests/test_authoring_sandbox.py`, `tests/test_evaluator_authoring.py`, `tests/test_authoring_file_io.py`, and `tests/test_autoresearch_runtime.py`, including adversarial isolation and no-effect dry runs.
  - _4 of 5 landed 2026-07-25; stays open on the fifth_ — `test_authoring_sessions.py` (30), `test_authoring_sandbox.py` (25), `test_authoring_file_io.py` (21), and `test_evaluator_authoring.py` (13) exist and pass, with adversarial isolation (cross-user session/handle reads, expiry, revocation, undeclared-destination egress) and no-effect dry runs covered. `test_autoresearch_runtime.py` is **not** written because it tests task 4.4's `tinyassets/autoresearch/` package, which this lane deliberately did not build (4.4's lease-reuse conditional is still false while `distributed-execution` is unarchived). This task cannot be checked until 4.4 lands its runtime.
- [ ] 4.6 Run §14 authoring/optimization proof: 100 concurrent author sessions, 1,000 isolated sequential sessions with no cross-user bleed, one execution per candidate lease, duplicate-candidate suppression, budget-stop races, and bounded evaluator-cache fan-out.
  - _authoring half landed 2026-07-25; optimization half blocked on 4.4_ — `tests/test_authoring_scale.py` proves the authoring clauses: 100 concurrent sessions across 100 accounts with every event owner-bound and reported p50/p95/max latency; 1,000 sequential cross-account sessions with neighbour-isolation spot checks (`slow` marker); and single-session edit contention showing one version per commit with a contiguous event sequence (no lost or duplicated event). The lease, duplicate-candidate, budget-stop-race, and evaluator-cache clauses are optimization behavior owned by 4.4 and are **not** proven. Task stays open until they are.
- [ ] 4.7 Complete a rendered chatbot authoring conversation through the live connector and capture full/diff inspection, file input/output, dry test, explicit publish, and post-fix clean-use evidence.
  - _blocked: not deployed_ — the code above is on an unmerged branch, so the live connector at `https://tinyassets.io/mcp` does not serve these actions yet; a rendered conversation now would prove the *old* surface. Per AGENTS.md this cannot be satisfied by direct MCP calls or local scripts. Order of operations: merge → confirm the deployed sha via `get_status` → `--assert-handles` canary (the handle set must still be exactly seven) → rendered `ui-test` → post-fix clean-use watch item.

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
  - _recurring obligation; latest check 2026-07-25_ — the node-authoring lane expanded the write-set beyond the change directory to `tinyassets/authoring/**`, `tinyassets/api/extensions.py`, `tinyassets/auth/provider.py`, `prototype/full-platform-v0/migrations/012_authoring_sessions.sql`, and `tests/test_authoring_*.py`. Checked against every `claimed:*`/`in-flight` row's Files in `STATUS.md`: no overlap (the active lanes hold `providers/router.py`, `api/universe.py`, `universe_server.py`, `persona.py`, `universe_intelligence.py`, `api/status.py`, `reset.py`, `paid_market/`, and OpenSpec change dirs). `tinyassets/api/extensions.py` and `tinyassets/auth/provider.py` are held by no row. Migration numbers 010/011 are taken by parallel lanes, hence 012. Stays unchecked: it must re-run at each future expansion, not once.
- [ ] 6.2 Strictly validate the full OpenSpec tree, run focused plus security/load suites, and obtain independent diff/code review.
  - _partially satisfied 2026-07-24_ — `openspec validate complete-independent-full-platform-targets --strict` passes, and the full-tree strict validation result is recorded in the lane report. Two independent cross-family reviews of this lane's premise verification and completion model both returned **adapt** (Codex, 2026-07-24). Round 1 confirmed the 4.4 and 5.4 corrections and the 5.1/5.2 storage owner, rejected any checking-off of runtime tasks by delegation or annotation, and required that 6.1-6.4 stay open. Round 2 reviewed the resulting commit and required two further folds, both verified against `origin/main` and applied above: **(a)** 5.1/5.2 were misfiled as `path-corrected` when the named `tinyassets/api/extensions.py` exists and the real defect was misattributed ownership — now `owner-corrected`, with 0.2 and the note vocabulary reworded; **(b)** the section-3 host gate was recorded as a section-wide blanket when only signed publication and 3.5's final acceptance proof are host-owned — now scoped, with 3.1/3.3 relabeled and the false "permanently red required check" claim replaced by the actual protection contexts. Round 2 also caught a miscount: 31 workflows on `origin/main`, not 32. The focused/security/load suites and code-to-requirement review of the capabilities themselves cannot be satisfied while the remaining sections are unbuilt; this stays unchecked as the implementation foldback gate. Partial credit 2026-07-25 (node-authoring lane): full-tree strict validation passes (42/42), the authoring focused suites plus their touched-and-adjacent neighbours pass (232), a 16-mutation probe verified each new invariant's test can go red, and one independent cross-family review round returned a real defect that was fixed in the same commit. Tray, handoff, and the autoresearch half remain unreviewed because they remain unbuilt.
- [ ] 6.3 Sync only capabilities whose implementation and acceptance evidence are complete; split any unfinished capability into a surviving active change.
  - _split discharged 2026-07-25; sync disposition still "sync nothing"_ — **the moderation split is done, not just recorded.** `openspec/changes/moderation-and-abuse-response/` now holds the delta spec (moved by `git mv`, so the diff is a rename and the 1.4 requirement review carries over), the five section-2 implementation tasks with their premise notes, the in-flight fence for PRs #1662/#1667, and named implementation / acceptance / sync / archive ownership. Verified collision-free before the move: `gh pr view 1662/1667 --json files` (2026-07-25) shows neither draft touches this change directory. Section 2 here is now a pointer.
    **Sync still nothing.** `node-authoring-and-autoresearch` has landed implementation (4.1-4.3) but not its acceptance evidence (4.6 optimization half, 4.7 rendered proof), and `packaged-tray-installation` / `real-world-handoffs-and-outcomes` have no implementation at all — so no delta may be synced and this change stays active. This task stays unchecked as the recurring sync gate; it also becomes live again for `node-authoring-and-autoresearch` if that capability lands separately from the other two, which would require the same split shape as moderation.
- [ ] 6.4 Archive the completed change in the implementation landing lane and retire the STATUS claim.
  - _not applicable yet_ — archiving now would sync three target-only deltas (tray, handoffs, outcomes) plus an authoring delta whose acceptance evidence is incomplete into canonical specs as as-built truth. Blocked until 6.3's disposition is "everything complete", which it is not.
