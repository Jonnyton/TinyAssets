# Lane report — OpenSpec change `universe-creation`

Branch: `claude/osx-universe-creation` (off `origin/main`). Builder lane.
Date: 2026-07-24.

## Summary

Drove the lifecycle residuals of `universe-creation` to completion and honestly
classified the execution-authority tasks that are hard-blocked behind the P0
#1582 opposite-provider security gate (task 2.0). No execution-authority runtime
was built (correctly — it is gated). All 33 checklist items are now either
checked with evidence or annotated with a verified premise classification.

## Gate posture (why 2.1-4.7 were not built)

Task 2.0 is the P0 #1582 first-contact execution-authority security review gate.
The review packets are the open DRAFT PRs #1617 and #1660, both explicitly
"DO NOT MERGE OR IMPLEMENT RUNTIME" pending Claude's independent re-check after
its rate-limit reset. Tasks 2.1-2.7 and 4.1-4.7 "MUST NOT begin until this gate
is satisfied". I built none of that runtime and did not duplicate #1617/#1660 —
I built around them on the ungated lifecycle surface.

## Tasks completed (built + tested)

- **5.2 — public birth self-serializes; rejects caller-selected id.** Enforced
  the public-birth boundary at the shared `_universe_impl` dispatch chokepoint:
  `create_universe` with a non-empty caller-supplied `universe_id` is rejected
  (`reason: caller_selected_id_rejected`) unless the keyword-only internal-trust
  flag `allow_named_universe_id` is set. Catches BOTH public entry points
  (`universe action=create_universe` and `write_graph target=universe`).
  First-contact home materialization (`api/first_contact.py`) threads the flag
  so its already-reserved serial is accepted; direct `_action_create_universe`
  callers (dev/test/migration) bypass the boundary unchanged.
  - Files: `tinyassets/api/universe.py`, `tinyassets/api/first_contact.py`.
  - Tests: `tests/test_first_contact.py` — rejects chosen id via both entry
    points; self-serializes without id; internal named-id accepted;
    `ensure_founder_home` still serial. (37 passed.)

- **5.3 — root index keyed by immutable id + learned-name projection.** The
  `universes` index was already keyed by the immutable id and creation
  registers an unnamed serial row (`display_name` defaults to the serial). Added
  the missing learned-name projection: new
  `daemon_server.set_universe_display_name` updates ONLY the `display_name`
  column for the row keyed by the immutable id (no-op when absent), and
  `_action_soul_edit` projects an accepted `identity.md` self-name onto that
  same row after a governed learning event (best-effort; never fails the
  persisted learning). Key + runtime operation id untouched.
  - Files: `tinyassets/daemon_server.py`, `tinyassets/api/universe.py`.
  - Tests: `tests/test_universe_soul.py` —
    `test_creation_adds_unnamed_serial_index_row`,
    `test_learned_name_projects_onto_immutable_index_row`. (13 passed.)

- **5.1 — HTTP cannot create a universe (regression-locked).** Premise stale:
  no `POST /v1/universes` (or any universe-creation) REST route exists — the MCP
  tools are the only public creation surface. Added
  `test_http_app_exposes_no_universe_creation_route` asserting the
  streamable-http app mounts no universe-creation route (fails loudly if one is
  ever added).
  - Files: `tests/test_universe_server_directory_app.py`. (2 passed.)

- **6.2 — strict OpenSpec validation.** `openspec validate universe-creation
  --strict` → "Change 'universe-creation' is valid".

## Tasks classified (verified premise, not code-buildable in this lane)

- **1.1-1.6** — Re-verified against the tree; all hold. Left checked.
- **2.0** — GATE UNSATISFIED (P0 #1582; DRAFT PRs #1617/#1660 pending Claude
  re-check). Blocks 2.1-4.7.
- **2.1-2.7, 4.1-4.7** — BLOCKED by 2.0. Execution-authority runtime; not built.
- **3.1** — PARTIAL: the R2-1a `allowed_providers` router boundary EXISTS
  (`providers/router.py:209-345`, hard-fails non-admitted providers) — the
  boundary 4.3 must consume, not duplicate. R2-1a not fully landed (founder-key
  half open per STATUS). Recorded, not checked.
- **3.2** — NOT LANDED: only the R2-1b spec landed (#1650); runtime still uses
  the process-global `_last_provider` (`providers/call.py:54`), the sink the
  spec forbids. No result-local receipt object to extend. Blocked.
- **5.4 / 5.6** — TOOLING LANDED / HOST-RUN OPERATIONAL. Existing
  `scripts/rename_live_data_universes_to_serial_ids.ps1` (serial migration +
  `universe_id_aliases.json` manifest + `.active_universe` repoint + containment
  guards) and `scripts/migrate_live_data_okf_baseline.ps1` (OKF baseline
  cleanup). PowerShell operations against the live-data snapshot — outside this
  lane's code Files boundary and a live-data/data-loss-risk class needing host
  staging + independent review. Evidence largely run: the OKF-baseline script
  already excludes a serial-id universe (`u-01kw34sp5bdgzn1s9f7r2tmc4p`).
- **5.5** — HOST-VERIFY: no runtime alias-resolution layer exists (by design —
  the migrator renames the dir to the serial). Post-migration reference-resolve
  verification is operational, on the live snapshot.
- **6.1** — PARTIAL: lifecycle/first-contact/HTTP surfaces this lane touched are
  green (97 passed, see below). Provider-routing/receipt coverage belongs to the
  blocked 2.1-4.7. Verifier runs the full suite.
- **6.3 / 6.4** — Live-connector `ui-test` + post-fix clean-use evidence apply
  once the gated execution-authority runtime lands.

## Test + ruff evidence (2026-07-24, this worktree, Python 3.14)

- `pytest tests/test_first_contact.py tests/test_universe_soul.py
  tests/test_universe_server_directory_app.py tests/test_universe_server_ledger.py
  tests/test_multi_tenant_isolation.py tests/test_soul_edit.py` → **97 passed**.
- `ruff check` clean on every file I authored code in:
  `tinyassets/api/universe.py`, `tinyassets/api/first_contact.py`,
  `tests/test_first_contact.py`, `tests/test_universe_soul.py`,
  `tests/test_universe_server_directory_app.py`. My added
  `daemon_server.set_universe_display_name` is clean.
- **Pre-existing red reported honestly:** `ruff check tinyassets/daemon_server.py`
  shows 8 E501 long-line errors at lines 2317-4264 (col 149). These predate my
  change (0 over-length lines in my +25-line diff) and are left for their own
  lane — not gamed, not touched.
- Plugin mirror rebuilt via `packaging/claude-plugin/build_plugin.py` after each
  canonical `tinyassets/*` edit; pre-commit mirror-parity gate green.

## Boundary note

Assigned Files were `openspec/changes/universe-creation/`,
`tinyassets/universe_server.py`, `tinyassets/api/universe.py`, plus tests. Two
adjacent files were necessarily touched (small, additive, not claimed by any
in-flight STATUS row): `tinyassets/api/first_contact.py` (thread the
internal-trust flag for 5.2) and `tinyassets/daemon_server.py` (the narrow
`set_universe_display_name` index helper for 5.3). `universe_server.py` itself
was not modified (the birth chokepoint lives in `api/universe.py`).

## ADAPT fold — Codex review round 1 (2026-07-24)

Verdict: `scratchpad/verdict-universe-creation.md` — **ADAPT**. Direct flag
reachability (closed), HTTP absence, projection isolation, focused tests, mirror
parity, and reported lint debt all checked out. One required fold: 5.2's
self-serialization was incomplete at the first-contact seam.

- **Finding:** `ensure_founder_home` threaded `allow_named_universe_id=True` for
  `winner` from `claim_founder_home`, without proving provenance. That helper
  does `INSERT ... ON CONFLICT(founder_sub) DO NOTHING` and returns a
  pre-existing `founder_home` binding verbatim; `founder_home` has no
  serial-format constraint, so a stale founder-influenced *descriptive* id
  (pre-boundary caller-selected creation) could cross the trust flag and be
  materialized as a named universe.
- **Fix (fail-closed provenance gate):** trust `winner` ONLY when it is the
  fresh `candidate` just generated this call OR it itself passes the canonical
  `is_universe_serial` validator (not a regex copy). A winner failing both →
  log loudly + return `""`; never rebind/migrate a stale descriptive home to a
  serial here (that is host-run migration, task 5.4). Files:
  `tinyassets/api/first_contact.py`.
- **Tests added (`tests/test_first_contact.py`):** stale descriptive
  `founder_home` is rejected, not materialized, and left intact (can-fail:
  without the gate it materializes `chosen-name`); a legitimate pre-existing
  serial reservation still materializes; a public-schema reachability lock
  asserts the trust flag is absent from both public tool wrappers.
- **Evidence:** `tests/test_first_contact.py` 40 passed; focused set (same six
  files) **100 passed**; ruff clean on `first_contact.py` + test file; plugin
  mirror rebuilt; `openspec validate universe-creation --strict` valid.

## Commits pushed

- `05775a74` feat(universe): public birth self-serializes; reject caller-selected id
- `81ab0c58` feat(universe): project learned identity.md name onto immutable index row
- `20661dd5` docs(universe-creation): classify blocked/operational tasks; lane report
- `4704b95f` fix(universe): fail-closed provenance gate on first-contact home materialization (ADAPT fold)

Branch pushed to `origin/claude/osx-universe-creation` (head `4704b95f`). No PR
opened — cross-family review happens before any PR.
