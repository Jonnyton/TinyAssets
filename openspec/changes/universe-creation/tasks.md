> **Residual change (reconciled 2026-07-22).** Checked items are verified
> prerequisites already present in canonical specs/runtime. Unchecked items are
> the only implementation work owned by this change. Provider/security runtime
> work remains gated on requester/market authority dependencies and
> opposite-provider security review.

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
- [x] 1.5 Reclassify the remaining work under `identity-auth-and-access-control` and `universe-lifecycle-and-soul`; remove the obsolete proposed `universe-creation` capability delta.
- [x] 1.6 Validate the reconciled active change strictly and confirm its residual deltas remain unsynced while implementation tasks are open.

## 2. Execution-Authority Contract Tests

- [ ] 2.0 Obtain opposite-provider APPROVE of provider-specific environment, cloud-chain, auth-home, local-subscription, hardware, and market-grant isolation, or incorporate every required ADAPT finding and have it re-reviewed to acceptance. Tasks 2.1-4.7 MUST NOT begin until this gate is satisfied; planning/spec work only.
  - GATE UNSATISFIED (verified 2026-07-24). This is the P0 #1582 first-contact
    execution-authority security gate. The review packets are open DRAFT PRs
    #1617 (`codex/first-contact-authority-handshake`) and #1660
    (`codex/first-contact-authority-review`), both explicitly "DO NOT MERGE OR
    IMPLEMENT RUNTIME": they require Claude to independently re-check primary
    sources and current TinyAssets ownership after its rate-limit reset before
    the gate returns approve/adapt. Until that verdict lands, tasks 2.1-4.7 are
    BLOCKED — planning/spec only. This lane built no execution-authority
    runtime.
- [ ] 2.1 Add a requester-owned success test proving a complete requester compute/model bundle permits the universe intelligence to generate a reply which the chatbot relays/renders verbatim.
- [ ] 2.2 Add an accepted-market success test proving accepted compute and, when separately required, model-access grants permit execution and are recorded as market authority.
- [ ] 2.3 Add missing and partial authority tests proving birth/binding may complete but no provider is invoked and the result is `held` / `setup_required` with `universe_id`, missing elements, and BYOC/market paths.
- [ ] 2.4 Add hostile ambient-credential tests proving project-maintainer, project-founder, and platform-operator credentials, quota, auth homes, cloud chains, hardware, and accounts are never selected for a requester workload.
- [ ] 2.5 Add routing/fallback tests proving retries can use only providers admitted by the immutable authority bundle and hold when that set is exhausted. This is acceptance coverage for STATUS R2-1a plus task 4.3 and depends on the R2-1a `allowed_providers` boundary.
- [ ] 2.6 Add phase-boundary tests proving reply generation and learning extraction use the same authority bundle, may select different providers admitted for their respective phases, and never invoke an uncovered provider.
- [ ] 2.7 Add receipt tests proving each invocation records phase, provider, and `requester_owned` or `accepted_market` authority without recording secrets. This is acceptance coverage for STATUS R2-1b plus task 4.7 and depends on the R2-1b race-safe result-object receipt.

## 3. Authority Dependencies and Security Gate

- [ ] 3.1 Confirm R2-1a has landed its `allowed_providers` engine/router boundary; consume that boundary rather than implementing a second provider-selection path.
  - PARTIAL (verified 2026-07-24): the `allowed_providers` router boundary
    EXISTS and hard-fails a provider not admitted by the resolved universe's
    allowlist (`tinyassets/providers/router.py:209-345`) — this is the boundary
    task 4.3 must consume, not duplicate. R2-1a is NOT fully landed: STATUS's
    "R2-1a set_engine must constrain allowed_providers" row notes the founder's
    own key still falls through the writer chain. Full consumption stays gated
    behind task 2.0; recorded, not checked.
- [ ] 3.2 Confirm R2-1b has landed its race-safe provider result/receipt for both writer calls; extend that object rather than using `_last_provider` or a parallel receipt.
  - NOT LANDED (verified 2026-07-24): only the R2-1b SPEC landed (#1650,
    `provider-attempt-receipts`); the runtime still exposes the process-global
    `_last_provider` (`tinyassets/providers/call.py:54`) — the exact sink the
    spec forbids. There is no result-local receipt object to extend yet, so
    task 4.7 cannot begin. Blocked; recorded, not checked.

## 4. Execution-Authority Implementation

- [ ] 4.1 Implement the requester BYOC authority resolver for compute and separately required model access. Depends: 2.0.
- [ ] 4.2 Implement accepted-market compute/model grant resolution and bind it to the requester's accepted offer. Depends: 2.0.
- [ ] 4.3 Construct an immutable complete authority bundle and pass only its eligible provider set into the R2-1a selection/fallback boundary. Depends: 4.1, 4.2, and STATUS R2-1a; extend its `allowed_providers` boundary, do not duplicate or replace it.
- [ ] 4.4 Isolate provider child processes from ambient maintainer credential sources with the allowlisted environment/home/profile boundary. Depends: 2.0 and the reviewed isolation design.
- [ ] 4.5 Return the structured `held` / `setup_required` envelope without provider invocation when the bundle is absent, partial, or loses all eligible fallbacks. Depends: 4.3 and 4.4.
- [ ] 4.6 Thread the same bundle through universe reply generation and learning extraction; keep the chatbot as relay/renderer only. Depends: 4.3-4.5.
- [ ] 4.7 Extend the R2-1b result object with redacted per-phase authority class and accepted-market grant linkage without recording secrets. Depends: 4.6 and STATUS R2-1b; extend the provider result object and never use `_last_provider`.

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
  - TOOLING LANDED / HOST-RUN OPERATIONAL (verified 2026-07-24). Existing
    `scripts/rename_live_data_universes_to_serial_ids.ps1` detects descriptive
    roots by universe markers, generates `u-`+ULID serials, `Move-Item`s the
    directory, writes a `universe_id_aliases.json` manifest (legacy id ->
    serial, backed up), and re-points `.active_universe` — with root-containment
    guards. This is a PowerShell operation against the live-data snapshot
    (`scripts/` + `Workflow-live-data-snapshot`), OUTSIDE this lane's code Files
    boundary and a live-data / data-loss-risk class needing host staging +
    independent review. Evidence it has largely run: `migrate_live_data_okf_
    baseline.ps1` already excludes a serial-id universe
    (`u-01kw34sp5bdgzn1s9f7r2tmc4p`). Left to host-action; not a code build here.
- [ ] 5.5 Verify migrated bindings and read/write/run/status references resolve only the serial id after migration.
  - HOST-VERIFY (2026-07-24). No runtime `universe_id_aliases.json` resolution
    layer exists in `tinyassets/` (grep clean) — by design, the migrator
    RENAMES the directory to the serial, so directory-name-keyed references
    resolve the serial after the move; the alias file is compatibility-lookup
    only. Confirming live bindings/read/write/run/status all resolve the serial
    is post-migration operational verification on the live snapshot, not a code
    task in this lane. Blocked on 5.4's host run.
- [ ] 5.6 Remove duplicate `self/`, `soul/`, and brain-archive directories plus empty starter notes/logs from existing roots while preserving non-empty historical runtime data.
  - TOOLING LANDED / HOST-RUN OPERATIONAL (2026-07-24). Existing
    `scripts/migrate_live_data_okf_baseline.ps1` rebuilds the canonical OKF
    baseline top-files per root. Same class as 5.4: a PowerShell operation on
    the live snapshot, outside this lane's code Files boundary. Host-action.

## 6. Verification and Release Gates

- [ ] 6.1 Run focused auth, first-contact, provider-routing, learning-extraction, receipt, universe-lifecycle, migration, and HTTP tests.
  - PARTIAL (2026-07-24): the lifecycle/first-contact/HTTP surfaces this lane
    touched are green — `pytest tests/test_first_contact.py
    tests/test_universe_soul.py tests/test_universe_server_directory_app.py
    tests/test_universe_server_ledger.py tests/test_multi_tenant_isolation.py
    tests/test_soul_edit.py` → 97 passed. Provider-routing / learning-extraction
    / receipt coverage belongs to the blocked execution-authority tasks
    (2.1-4.7) and is not built here. Verifier runs the full suite.
- [x] 6.2 Re-run strict OpenSpec validation after implementation and before syncing or archiving this change.
  - DONE (2026-07-24): `openspec validate universe-creation --strict` →
    "Change 'universe-creation' is valid".
- [ ] 6.3 Verify the success and setup-required paths through a rendered chatbot conversation using the live connector.
  - BLOCKED: the success/setup-required (`held`) paths are the
    execution-authority behavior gated behind task 2.0. Live-connector
    `ui-test` proof applies once that runtime lands.
- [ ] 6.4 Freshness-stamp post-fix production evidence that real users complete first contact without consuming maintainer resources; leave a monitoring item if no clean use is visible yet.
  - PENDING execution-authority landing (gated by 2.0). STATUS P0 #1582 watch
    item already tracks "newborn contact has no BYOC/market authority path" —
    no post-fix clean-use evidence is possible until the authority runtime
    ships.
