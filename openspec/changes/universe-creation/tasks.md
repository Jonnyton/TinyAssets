> **Residual change (reconciled 2026-07-26).** Checked items are verified
> prerequisites already present in canonical specs/runtime. Unchecked items are
> the only implementation/integration work owned by this change. Provider
> authority, requester-host activation, connector-market activation, and
> provider receipts remain separately owned dependencies.

## 1. Verified Prerequisites

> Re-verified against the tree 2026-07-24: 1.1 (`ids.new_universe_id` +
> `_action_create_universe` mkdir-rollback), 1.2 (`seed_okf_bundle`; no starter
> `self/`/`soul/`/`notes.json`/`activity.log`), 1.3 (`ensure_founder_home`
> checks create scope before reserving; `get_status` pure read), 1.4
> (`ensure_founder_home` resolves via founder-home binding, `.active_universe`
> only written for anonymous creates) all hold. Left checked.

- [x] 1.1 Verify creation generates an opaque lowercase `u-`+ULID serial when no id is supplied and rolls back partial roots.
- [x] 1.2 Verify creation seeds the linked root OKF soul bundle and omits duplicate starter `self/`, `soul/`, `notes.json`, and `activity.log` artifacts for new universes.
- [x] 1.3 Verify opening authenticated `converse` with create scope can reserve, materialize, and bind exactly one founder home while `get_status` remains a pure read; without create scope it writes no binding and returns a structured home-create/load error with `auth_scope_required: true`.
- [x] 1.4 Verify the authenticated first-contact path resolves through founder home context rather than a host-global active-universe marker.
- [x] 1.5 Reclassify lifecycle work under `universe-lifecycle-and-soul`; remove the obsolete proposed `universe-creation` capability and the duplicate identity/provider-authority delta now owned by `constrain-set-engine-provider-authority`.
- [x] 1.6 Validate the reconciled active change strictly and confirm its one residual lifecycle delta remains unsynced while implementation tasks are open.

## 1B. Newborn Voice (P0 #1582 — host decision 2026-07-25)

> NUMBERING NOTE: no task 1.14 existed when this lane opened — section 1 ended
> at 1.6 (verified 2026-07-25, `grep -rn "1\.14" openspec/changes/` returns only
> unrelated changes). The host's 2026-07-25 decision named "task 1.14: the
> can-it-speak test", so this lane created it here under that number rather than
> silently renumbering it into a section titled "Verified Prerequisites".
>
> GATE 2.0 RELATIONSHIP: this task grants no authority, resolves no authority
> bundle, and selects no provider. It changes only how an ALREADY-FAILED turn is
> reported, strictly on the fail-closed side of 92dd60c5. It is not
> execution-authority runtime, so it does not open tasks 2.1-4.4 and no 2.x/4.x
> task is checked below.

- [x] 1.14 Add the can-it-speak test proving a newborn universe answers its founder's first turn, and make a universe with no engine of its own return an actionable setup reply instead of raw provider exhaustion.
  - DONE (2026-07-25). RED FIRST: every one of the 97 first-contact tests
    asserted BIRTH; none asserted SPEECH. Against current behavior the founder's
    opening turn returned
    `{"error": "Your universe couldn't be reached right now: All providers
    exhausted for role=writer. Daemon should retry with backoff."}` — no
    `universe_id`, no path forward. Cause: 92dd60c5 correctly refuses
    host-credential fallback and nothing provisions a newborn a credential.
  - FIX: `engine_setup_required_payload` (`tinyassets/api/universe.py`) returns
    `status: held` / `reason: setup_required` / `universe_id` / `missing:
    [compute, model_access]` / `note` / `setup_paths`, consumed by the `converse`
    seam in `tinyassets/universe_server.py`. It carries NO `reply` key — `reply`
    is what the connector renders verbatim as the universe's own first-person
    voice, so a platform-authored message travels as `note`, the same split the
    existing `write_page` / `_BRAIN_WRITE_RELAY_ACTIONS` relays use.
  - CURRENT MAIN, SUPERSEDED FOR TARGET CUTOVER: `setup_paths` carries
    `path: byo_api_key` with the truthful but Tier-1-dead instruction to ask the
    host to use an internal engine-assignment surface; the advertised seven
    handles expose no such action. Approved PR #1784 preserves this shipped
    projection while V2 is dark, then forbids raw API-key deposit at cutover.
    Task 4.2 MUST consume only successor-proven setup paths before provider
    authority/newborn deny-all activates. The absent market path remains absent
    until the connector successor makes it completable.
  - DISTINGUISHABILITY (BUG-038/039 not masked): the payload requires BOTH
    `exc.chain_state is not None` (only router.py's genuine
    every-provider-failed raise carries FEAT-006 diagnostics; the allowlist /
    pinned-writer / api-key-policy / no-router raises are bare) AND
    `not universe_has_assigned_engine(udir)` (vault `llm_subscription` /
    `llm_api_key` record, OR a non-default `engine_source`). Unreadable vault or
    config returns True — absence is never inferred from a read failure.
  - Tests (`tests/test_first_contact.py`, 12 added, 54 pass): held payload +
    platform-authored (no `reply`) + credentialed-universe exhaustion still raw
    + non-provider failure still raw + unreadable vault fails safe + single
    provider call + 3 non-vault engine sources + policy hard-fail keeps its own
    message + unreadable config fails safe + non-string `engine_source` does not
    crash. SIX guards mutation-proven (each disabled → its tests go red).
  - Opposite-provider review: Codex (read-only), TWO `adapt` rounds, all four
    findings folded with a failing-first test each — (r1) `self_hosted_endpoint`
    / `market_rented` / `host_daemon` write no vault record; (r1) the allowlist
    policy hard-fail shares the exception class; (r2) `load_universe_config`
    degrades a corrupt config to defaults so the claimed config fail-safe never
    fired; (r2) `engine_source: 7` reached `.strip()` and raised AttributeError
    inside the failure handler. Full record: `LANE_REPORT.md`.
  - KNOWN RESIDUAL GAP (Codex r2 finding 1, accepted not fixed): under
    `TINYASSETS_PIN_WRITER`, a credential-less newborn gets the BARE pinned-writer
    exhaustion (`router.py`, no `chain_state`), so the discriminator rejects it
    and the raw error still reaches the founder. Not a production path —
    `TINYASSETS_PIN_WRITER` appears in no `deploy/` config, no workflow, and no
    repo variable (`gh variable list` → only `AUTO_FIX_DISABLED`,
    `WORKOS_REQUIRE_AUTH`), verified 2026-07-25. The clean fix is to attach
    `chain_state` to that raise in `tinyassets/providers/router.py`, which this
    lane holds read-only and STATUS's R2-1a lane owns.

## 2. Provider-Authority Integration Tests

- [x] 2.0 Consume the opposite-provider-approved provider-authority target from PR #1784 (`abdca5fe`) and remove every conflicting ownership claim from this change.
  - VERIFIED 2026-07-26: Opus 5 APPROVED the exact provider target; its
    published handoff requires target lineage only, successor-proven setup
    paths, and setup-payload `fulfillment_class`, with no caller-built authority
    bundle.
- [ ] 2.1 After the provider owner lands runtime, prove opening `converse` passes only canonical server-derived universe/request lineage and receives its typed result without caller-built provider authority.
- [ ] 2.2 Prove `ProviderAuthorityHeldError` preserves completed birth and maps directly to `engine_setup_required_payload` before provider invocation, with the materialized `universe_id`, typed missing elements, and no fabricated `reply`.
- [ ] 2.3 After `activate-connector-requester-authority` lands, prove a Tier-1 accepted-market success executes through its B2/B13 remote seam and the chatbot relays the universe reply verbatim.
- [ ] 2.4 After `activate-requester-host-engines` lands, prove each supported host/local surface consumes its attested capability without implying that browser-only users need a desktop.
- [ ] 2.5 Add hostile ambient-resource integration tests proving a provider-owner refusal remains held at the universe boundary; do not duplicate provider isolation or fallback implementation here.
- [ ] 2.6 Prove reply generation and model-backed learning extraction consume the same opaque provider request capability; the setup payload uses `fulfillment_class`, while result-local evidence uses only owner-defined receipt fields and never `_last_provider`.

## 3. Owned Dependencies

- [ ] 3.1 Confirm `constrain-set-engine-provider-authority` lands the request carrier, typed hold, migration, and provider-selection boundary before universe integration begins.
- [ ] 3.2 Confirm `provider-attempt-receipts` lands result-local `authority_held` evidence for both model-backed phases; consume it without a parallel receipt.
- [ ] 3.3 Confirm `activate-connector-requester-authority` lands before an accepted-market setup/result path is advertised to Tier-1 connector users.
- [ ] 3.4 Confirm `activate-requester-host-engines` lands before a host/local setup path is advertised on its supported surfaces.

## 4. Universe-Owned Provider Integration

- [ ] 4.1 Pass only canonical target universe/request lineage from `converse` into the provider owner; reject caller-built bundles, provider allowlists, and ambient authority reconstruction.
- [ ] 4.2 Catch the typed provider hold and map it to the canonical setup-required payload while preserving birth; advertise only owner-supplied live routes, never raw API-key deposit or unavailable market/desktop paths.
- [ ] 4.3 Relay a successful universe reply verbatim and carry the same opaque provider request capability through model-backed learning extraction without inspecting, widening, or minting it.
- [ ] 4.4 Map `fulfillment_class=requester_owned|accepted_market` only in the canonical setup-required payload and consume provider-attempt evidence using its owner-defined fields; keep credential `authority_class` separate and create no parallel receipt.

## 5. Lifecycle Residuals

- [x] 5.1 Add tests proving public `POST /v1/universes` cannot create a universe, then remove or reject the route.
  - PREMISE STALE + REGRESSION-LOCKED (2026-07-24): no `POST /v1/universes`
    HTTP route exists in the tree — nothing to remove. The only public
    creation surfaces are the MCP `universe action=create_universe` and
    `write_graph target=universe` tools; `create_streamable_http_app()`
    (`universe_server.py:2231`) registers only MCP transport + discovery
    routes. Added `test_http_app_exposes_no_universe_creation_route`
    (`tests/test_universe_server_directory_app.py`) asserting the app mounts no
    universe-creation route — fails loudly if one is ever added. The
    public-birth boundary itself is enforced at the shared dispatch chokepoint
    (task 5.2).
- [x] 5.2 Add tests proving every public birth path generates its own serial and rejects caller-selected ids, then enforce the boundary without breaking internal migration tooling.
  - DONE (2026-07-24): `_universe_impl` now rejects a caller-selected
    `universe_id` on `create_universe` with `reason: caller_selected_id_rejected`
    at the shared dispatch boundary, so both public birth entry points
    (`universe action=create_universe`, `write_graph target=universe`) refuse a
    chosen id and self-serialize an opaque `u-`+ULID. Internal callers pass a
    keyword-only `allow_named_universe_id=True` (first-contact home
    materialization threaded; migration/dev tooling that calls
    `_action_create_universe` directly bypasses the boundary unchanged). Tests:
    `tests/test_first_contact.py` (rejects chosen id via both entry points;
    self-serializes without id; internal named-id accepted; first-contact
    still serial).
  - ADAPT fold (2026-07-24, Codex review): `ensure_founder_home` threaded the
    trust flag for `winner` from `claim_founder_home` without proving its
    provenance. Because `claim_founder_home` does INSERT ... ON CONFLICT DO
    NOTHING, a stale founder-influenced *descriptive* `founder_home` binding
    (pre-boundary caller-selected creation) was returned verbatim and could be
    materialized through the flag — defeating self-serialization at its own
    seam. FIX: a fail-closed provenance gate trusts `winner` ONLY when it is the
    fresh `candidate` just reserved OR itself passes the canonical
    `is_universe_serial` validator; otherwise it logs loudly and returns "" —
    never rebinding/migrating a stale descriptive home to a serial (that is
    host-run migration, task 5.4). Added tests: stale descriptive binding is
    rejected + not materialized + binding left intact; legitimate pre-existing
    serial reservation materializes; a public-schema reachability lock asserting
    the trust flag is absent from both public tool wrappers.
  - ADAPT fold round 2 (2026-07-24, Codex): `is_universe_serial(winner)` proves
    FORMAT, not GENERATION provenance — a hostile/legacy value like
    `u-00000000000000000000000000` satisfies the regex yet was never generated
    by the platform, and `founder_home` has TWO writers (`claim_founder_home` +
    the general `set_founder_home`), so sole-writer provenance cannot be
    assumed. STRUCTURAL FIX (route 2): added a `founder_home.platform_generated`
    marker (schema + ALTER migration; existing rows default 0 → fail closed
    until host-run backfill). `claim_founder_home` stamps it for a freshly
    reserved serial; `set_founder_home` gained a `platform_generated` param and
    `_action_create_universe` passes True only when IT generated the id (public
    births self-serialize → True; caller/dev-supplied → False). First-contact's
    gate now requires the marker (`founder_home_is_platform_generated`) AND
    serial shape (defense-in-depth), replacing the format-only check. Stamping
    both writers truthfully (not claim-only) preserves the legitimate
    interrupted-birth repair of a genuine platform serial while failing closed
    on any caller-influenced or unproven binding. New/updated tests
    (`tests/test_first_contact.py`): serial-SHAPED-but-unproven value fails
    closed (the exact reviewer repro, can-fail); proven-marker serial
    materializes; `claim_founder_home` stamps provenance vs unproven
    `set_founder_home`; interrupted-birth repair updated to record true
    provenance. Also adapted two `test_universe_server_isolation.py` create
    tests to self-serialization (round-1 boundary regression they weren't in the
    prior focused set).
- [x] 5.3 Add tests and implementation for the root universe index keyed by immutable id with learned-name projection from `identity.md`.
  - DONE (2026-07-24): the `universes` index is keyed by the immutable
    `universe_id` (PK / `ON CONFLICT(universe_id)`), and creation registers one
    unnamed serial row (`ensure_universe_registered` is called without a
    display name, so `display_name` defaults to the serial) — that half was
    already landed. NEW: learned-name projection. Added
    `daemon_server.set_universe_display_name` (updates ONLY the `display_name`
    column for the row keyed by the immutable id; no-op when no row exists) and
    wired `_action_soul_edit` to project the accepted `identity.md` self-name
    onto that same row after a governed learning event (best-effort; never
    fails the persisted learning). The immutable key and runtime operation id
    are untouched. Tests: `tests/test_universe_soul.py`
    (`test_creation_adds_unnamed_serial_index_row`,
    `test_learned_name_projects_onto_immutable_index_row`).
- [ ] 5.4 Inventory descriptive-id roots and live references, then implement an atomic, rollback-safe migration to generated serial roots.
  - UNSAFE CANDIDATE ONLY — DO NOT RUN (verified 2026-07-26).
    `scripts/rename_live_data_universes_to_serial_ids.ps1` moves roots before
    writing its alias manifest, updates only `.active_universe`, and does not
    transactionally update `founder_home`, the universes index, or all live
    references. Replacement tooling MUST journal rollback state before the
    first move, update bindings/index/references under one recoverable
    transaction, and survive a crash at every boundary.
- [ ] 5.5 Verify migrated bindings and read/write/run/status references resolve only the serial id after migration.
  - BLOCKED on the safe 5.4 replacement. Verification MUST prove
    `founder_home`, the universes index, active-universe state, read/write/run/
    status paths, and rollback/restart all converge on the serial id before a
    legacy root is retired.
- [ ] 5.6 Remove duplicate `self/`, `soul/`, and brain-archive directories plus empty starter notes/logs from existing roots while preserving non-empty historical runtime data.
  - UNSAFE CANDIDATE ONLY — DO NOT RUN (verified 2026-07-26).
    `scripts/migrate_live_data_okf_baseline.ps1` overwrites governed soul files
    with blank templates, including learned `identity.md`, and only reports
    legacy directories instead of removing them. Replacement tooling MUST
    support dry-run, back up/no-overwrite every governed file, remove only
    proven duplicate/empty artifacts, and preserve all non-empty history.

## 6. Verification and Release Gates

- [ ] 6.1 Run focused auth, first-contact, provider-routing, learning-extraction, receipt, universe-lifecycle, migration, and HTTP tests.
  - PARTIAL (2026-07-24): the lifecycle/first-contact/HTTP surfaces this lane
    touched are green — `pytest tests/test_first_contact.py
    tests/test_universe_soul.py tests/test_universe_server_directory_app.py
    tests/test_universe_server_ledger.py tests/test_multi_tenant_isolation.py
    tests/test_soul_edit.py` → 97 passed. Provider-routing / learning-extraction
    / receipt coverage belongs to the blocked provider-integration tasks
    (2.1-4.4) and is not built here. Verifier runs the full suite.
  - EXTENDED 2026-07-25 (task 1.14): `pytest tests/test_first_contact.py
    tests/test_converse_handle.py tests/test_api_universe.py
    tests/test_credential_fail_closed.py tests/test_credential_vault.py
    tests/test_s2_engine_assignment.py tests/test_s6_s8_engine_sources.py
    tests/test_relay_ux_prompts.py tests/test_per_universe_engine_resolution.py
    tests/test_triage_classify_provider_exhaustion.py
    tests/test_provider_allowlist.py tests/test_provider_router_diagnostics.py
    tests/test_providers_call.py` → 251 passed, 1 skipped. `ruff check` clean on
    the three touched files. Baseline debt NOT introduced by this lane and NOT
    fixed here: 6 tests fail identically on `origin/main`
    (`test_universe_server_framing.py` ×3, `test_universe_server_metadata.py`
    ×2, `test_input_keys_isolation.py` ×1) — verified by re-running them in a
    detached `origin/main` worktree. They belong to their own lane.
- [ ] 6.2 Re-run strict OpenSpec validation after every implementation task and immediately before syncing or archiving this change.
  - CURRENT PLANNING EVIDENCE (2026-07-26): the reconciled change validates
    strictly, but implementation and release gates remain open; task 1.6 records
    this pre-implementation validation and does not satisfy final validation.
- [ ] 6.3 Verify the success and setup-required paths through a rendered chatbot conversation using the live connector.
  - BLOCKED on tasks 3.1-3.4 and 4.1-4.4 plus a live in-app browser route.
    `ui-test` preflight on 2026-07-26 returned `No browser is available`; no
    direct MCP proof substitutes for the rendered connector conversation.
- [ ] 6.4 Freshness-stamp post-fix production evidence that real users complete first contact without consuming maintainer resources; leave a monitoring item if no clean use is visible yet.
  - PENDING provider-authority and successor landing. STATUS P0 #1582 tracks
    that newborn contact lacks a live requester/market authority path; no
    post-fix clean-use evidence exists until that runtime ships.
