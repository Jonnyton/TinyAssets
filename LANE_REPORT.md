# Scoped-reset lane report

Date: 2026-07-25
Branch: `codex/osx-scoped-reset`
Base requested: `origin/main` at `6cde7ef0`
Round-1 pushed head: `6c793c3d`

## Task 1.1 — freeze the safety contract

Implemented an explicit reset/preserve/block inventory for the current main
database and Epoch-2 stores. The planner fails closed on unknown tables,
unknown or unadapted home/root operational stores and root-run tables,
hidden/generated columns, changed resettable columns/keys/foreign-key
authority, triggers/views, foreign owners, active work, and preserved rows that
would otherwise be cascade deleted. Root/database/sidecar/home/barrier/journal/
staging paths reject symlinks, junctions, reparse points, hardlinks, and
filesystem/mount crossings.

The process-shared maintenance barrier uses Windows reader slots for concurrent
service writers and an all-slot exclusive reset lock. Every supported writer
entrypoint recovers or joins a verified-clean barrier before writing. The
legacy API acquires its replacement barrier before releasing the live one.

Red evidence:

- Initial contract run: 10 failures in `tests/test_scoped_identity_reset.py`.
- Independent-review additions reproduced failures for generated columns,
  hardlinked barrier/sidecar files, unadapted stores, foreign terminal actors,
  preserved cascade dependencies, and second-writer startup.

Green evidence:

- `tests/test_scoped_identity_reset.py` is green as part of the final 64-test
  focused run.
- Real two-process writer startup and reset exclusion pass on Windows.

Files:

- `tinyassets/scoped_reset.py`
- `tinyassets/__main__.py`
- `tinyassets/cloud_worker.py`
- `tinyassets/universe_server.py`
- `tinyassets/mcp_server.py`
- `tinyassets/desktop/launcher.py`
- `tinyassets_tray.py`
- `fantasy_daemon/__main__.py`
- `fantasy_daemon/api.py`
- `tests/test_scoped_identity_reset.py`

## Task 1.2 — read-only operator plan

Implemented an operator-only `python -m tinyassets.scoped_reset plan` command
that accepts an explicit credential-free roster, resolves only allowlisted
aliases, emits no raw subject, and binds the plan digest to roster/inventory
revisions, a domain-separated principal digest, exact row digests, resolved
paths, the home filesystem object plus entry/content digest, blockers, and
preservation scope. POSIX permissions and Windows owner/DACL are checked.
Unknown/non-allowlisted aliases fail closed. Read-only SQLite inspection does
not create WAL/SHM sidecars.

No-state planning and apply are stable mutation-free no-ops, including a data
root with no database. Completed replay returns the old receipt before
inspecting or touching a newly registered, actively blocked replacement home.

Red evidence:

- Four missing-planner failures plus two missing CLI/receipt failures.
- A no-database no-op apply reproduced the control-only-schema failure.
- Completed replay with an active replacement home reproduced an incorrect
  blocker before receipt lookup.

Green evidence:

- Both regressions pass in the final focused run.

Files:

- `tinyassets/scoped_reset.py`
- `tests/test_scoped_identity_reset.py`

## Task 1.3 — exact scoped apply and deterministic recovery

Implemented operator-only apply under the exclusive barrier and a durable
principal/home fence. Apply revalidates the exact plan, roster-principal
binding, filesystem object identity, and entry/content digest, then checks the
filesystem identity again immediately before rename. It publishes the
content-free journal before the SQLite prepared witness, stages only the exact
founder home by same-filesystem rename, deletes only exact planned primary-key
rows, and commits those deletes with the commit witness.

Recovery re-derives all paths instead of trusting SQLite, compares journal and
database evidence, rejects linked staging ancestors, rolls pre-commit state
back, completes post-commit cleanup, sweeps orphan/partial journals, and
durably flushes both rename parents plus staging/journal parents. All public
servers import only the writer barrier; apply/plan/recovery are not registered
as MCP actions or API routes.

Red evidence:

- Ten initial missing-apply failures.
- Eight Windows directory-durability failures before directory flushing was
  implemented.
- Independent review reproduced the journal-before-row and
  journal-before-completion crash windows, trusted recovery paths, linked
  staging ancestors, missing rollback-parent flushes, and multi-writer
  admission failure.

Green evidence:

- All journal, rename, commit, cleanup, completion, replay, and rollback
  boundaries pass in the final focused run.
- The durable Opus 5 review verdict is REJECT for reviewed head `f613b23d`.
  This fold fixes and proves its findings but does not invent a post-fix
  reviewer approval.

Files:

- `tinyassets/scoped_reset.py`
- writer entrypoint files listed under task 1.1
- packaged runtime mirrors under
  `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/`
- `tests/test_scoped_identity_reset.py`

## Task 1.4 — mutation and fault proof

Added a 13-case CI-executable proof that mutates the real `founder_home` and
`universe_acl` planner selection predicates and delete keys, corrupts the
commit witness and journal/path evidence,
interrupts partial journal publication, injects rollback rename failure,
checks reverse-rename durability flushes, and substitutes a linked staging
ancestor. Each widened filter or broken recovery guard makes the proof red.

Red evidence:

- Three initial mutation/recovery failures.
- Additional independent-review regressions were each observed red before
  implementation.

Green evidence:

- `tests/test_scoped_reset_mutation_proof.py`: 13 passed.

Files:

- `tests/test_scoped_reset_mutation_proof.py`
- `tinyassets/scoped_reset.py`

## Final verification

- Focused reset test files: 74 passed.
- Standalone mutation proof: 13 passed.
- Adjacent legacy API suites: 263 passed, 1 existing Starlette deprecation
  warning.
- Ruff on every changed Python source, test, and packaged mirror: clean.
- `python packaging/claude-plugin/build_plugin.py`: passed; import probe
  `probe-ok`.
- Canonical/package equality regression: passed.
- `openspec validate test-identity-and-reset --strict`: valid.
- `git diff --check`: clean before commit.
- Pre-commit gates: mirror parity, mojibake, import graph, path resolver,
  cross-provider drift, and skill validation passed.
- Branch pushed to `origin/codex/osx-scoped-reset` at `6c793c3d`; no PR opened.

## Deliberately not done

- No MCP action or public API route was added for reset.
- The existing global reset implementation was not changed.
- No PR was opened.
- Tasks 2.x and 3.x were not implemented in this lane.
- No WorkOS identities, credentials, live connector evidence, or production
  reset was created.
- This report is intentionally not committed.

## Opus 5 REJECT fold

### Finding 1 — cross-home data loss from path-only binding

- **Red:** `test_apply_refuses_home_directory_identity_swap` reproduced an
  unchanged plan and completed deletion after Alice's planned path was replaced
  by Bob's directory: 1 failed, `DID NOT RAISE`.
- **Fix:** The plan action now binds the roster-principal fingerprint,
  directory device/inode, and deterministic entry/content digest. Apply
  re-plans under the exclusive barrier and rechecks the filesystem identity
  immediately before `os.replace`.
- **Green:** The focused regression passes and Bob's file plus parked Alice
  home survive.
- **Mutation proof:** Replacing the identity capture with
  `{"path": str(home)}` turned the regression red again: 1 failed,
  `DID NOT RAISE`.

### Finding 2 — silent destruction of unclassified in-home stores

- **Red:** The reviewer formats `.sqlite3`, `.jsonl`, `.parquet`, and an
  extensionless store all produced no blocker: 4 failed.
- **Fix:** Home files are classified against an explicit resettable-content
  suffix set; known operational stores and every unclassified format abort the
  plan/apply without deletion.
- **Green:** All four formats are blocked, apply raises
  `ScopedResetBlocked`, and the store/home bytes survive: 4 passed.
- **Mutation proof:** Temporarily allowing the four suffix classes made all
  four regressions red again because no blocker was reported.

### Finding 3 — fail-open legacy writer fence

- **Red:** The legacy reconfigure probe acquired an exclusive reset lease on
  root A after root B acquisition failed while the API still pointed at A:
  1 failed, `legacy API still serves root A without its writer fence`.
- **Fix:** `configure()` now acquires the replacement shared barrier, swaps the
  module lease, then releases the previous barrier. Acquisition failure changes
  no live state.
- **Green:** Failed root B configuration leaves root A's shared lease held, and
  the root/barrier pair swaps before the old lease releases: 2 passed.
- **Mutation proof:** Restoring release-before-acquire turned the same probe
  red with the original unfenced-root assertion.

### Finding 4 — root stores and `.runs.db` schema growth skipped

- **Red:** A root `future_queue.sqlite3` and a live `pending_jobs` table in
  `.runs.db` yielded no blockers.
- **Fix:** Root files and root-run tables are explicit allowlists; unknown
  entries abort reset. Read-only WAL snapshots require the existing SHM and
  never create one.
- **Green:** Both unknown surfaces report blockers and the root/home bytes
  survive the refused apply.
- **Mutation proof:** The inventory regression directly pins both default-deny
  decisions; widening either allowlist makes the focused assertion red.

### Finding 5 — `founder_home` widening survived mutation proof

- **Red:** The Opus mutation widened `founder_home` to universe-only and the
  old 64-test suite stayed green.
- **Fix:** The planner validates every selected founder-home row against both
  exact principal and exact home before producing an action; the mutation
  suite now widens `founder_home` explicitly.
- **Green:** The widened runtime selector raises
  `ScopedResetPlanChanged("founder-home selection escaped...")`; the mutation
  file is 13 passed.
- **Mutation proof:** The new selector-widening case is itself the executable
  mutation and fails without the exact-row validation.

### Finding 6 — plan created SQLite WAL/SHM sidecars

- **Red:** The recursive size/mtime/SHA snapshot gained
  `.tinyassets.db-wal` and `.tinyassets.db-shm`.
- **Fix:** Sidecar-free databases use immutable read-only SQLite. Existing WAL
  snapshots use read-only mode only when their SHM already exists; a WAL
  without SHM fails closed.
- **Green:** `test_plan_does_not_create_sqlite_sidecars` preserves the complete
  recursive snapshot.
- **Mutation proof:** Replacing the helper with the former bare `mode=ro`
  connection makes the snapshot regression red by adding both sidecars.

### Finding 7 — unsupported independent-approval claim

- **Red:** `git log --name-only 6cde7ef0..f613b23d` contained no review
  artifact while the old report claimed `APPROVE`.
- **Fix:** `docs/reviews/2026-07-25-scoped-reset-opus5.md` durably records the
  named/date/range REJECT and all seven findings. This report removes the false
  approval claim.
- **Green:** The review artifact is included in the commit candidate; this
  intentionally uncommitted report points to it.
- **Mutation proof:** Removing the durable artifact or restoring the approval
  sentence makes the documented review-evidence check false by inspection.

## Round 2 - recovery ownership and case-fold containment

### Finding 8 - automatic recovery cleanup deleted a replacement staging directory

- **Red:** The reviewer reproduction crashed at `after_commit`, parked the
  reset-created staged home, moved Bob's pre-existing home into the exact
  staging path, and called automatic recovery. Recovery did not raise and
  deleted Bob's directory. In the first focused run this regression and both
  recovery legs of the general containment test failed with `DID NOT RAISE`
  (3 staging-ownership failures total).
- **Fix:** The already-reviewed home identity manifest is now persisted in both
  `plan_json` and the pre-rename journal, with the database copy bound to the
  existing `state_digest` and the two copies cross-validated during recovery.
  `_safe_cleanup_staging` cannot be called without a planned identity and is
  the only `shutil.rmtree` site in scoped reset. It verifies device, inode, and
  complete entry/content digest before deletion. Pre-commit rollback uses the
  same authorization before moving staged state back.
- **Green:** The replacement directory causes
  `ScopedResetRecoveryError("...filesystem identity...")`; Bob's bytes remain
  at the staging path and the parked reset-owned home remains intact. The
  reviewer regression and all four general containment cases pass.
- **Mutation proof:** Temporarily turning
  `_assert_recovery_filesystem_identity` into a no-op made the reviewer
  regression, both staged-replacement containment cases, and the foreign
  already-restored source case red: 4 failed, 3 passed. Restoring the guard
  returned them to green.

### Finding 9 - Windows case collision bypassed credential and audit classification

- **Red:** On the case-folding Windows pytest path, `AUTH.JSON`, `Auth.Json`,
  `.CREDENTIAL-VAULT.JSON`, and `BID_EXECUTION_LOG.JSON` produced no blocker;
  all four reviewer variants failed before apply could be proven to abort.
- **Fix:** Home traversal now computes `entry.name.casefold()` once and uses
  that normalized name for every credential, audit prefix, operational
  directory, operational filename, SQLite sidecar, and suffix decision. The
  allowlist and deny rules therefore use one case-insensitive classification
  domain.
- **Green:** All four case-collided stores are classified as credential or
  audit artifacts, apply raises `ScopedResetBlocked`, and their bytes plus the
  founder home survive.
- **Mutation proof:** Temporarily replacing `entry.name.casefold()` with the
  original `entry.name` made all six credential, audit, operational-file, and
  operational-directory variants red again.

### Structural assessment and choice

Two rounds finding the same guarantees at new paths showed an incomplete
generalization, not two unrelated last-edge bugs. The row-delete side was
already structurally exact: reviewed primary keys are the only rows deletion
accepts. The filesystem side also already built the right identity-owned
manifest before mutation, but recovery dropped the filesystem actions and the
tree-delete primitive accepted only a path.

The chosen structural change reuses that manifest rather than creating a
parallel deletion model:

1. One shared state-digest function binds database and filesystem actions.
2. Prepared database evidence and the durable journal both carry the reviewed
   filesystem identity before rename or deletion.
3. Recovery validates plan digest evidence, owner fingerprint, source path,
   action kind, and journal parity before returning a deletion identity.
4. The sole scoped-reset tree-delete primitive requires that identity and
   refuses mismatches; rollback uses the same identity gate.
5. Home classification normalizes once before every protected-name or
   resettable-suffix decision.
6. Pre-commit recovery accepts exactly two filesystem states: owned staging
   with absent source (restore it), or absent staging with the same owned source
   already restored. Both-present, neither-present, and foreign identity abort
   without marking rollback complete or releasing the lease.

This closes the class at the destructive primitive and recovery-evidence
boundary instead of adding another path-specific check. An interrupted
operation created by older code without filesystem manifest evidence now
fails recovery loudly and preserves staged state rather than guessing.

### General containment invariant

`test_foreign_directory_is_refused_at_every_filesystem_boundary` enumerates all
filesystem ownership transitions:

- replacement of the reviewed source before apply;
- replacement at the `before_rename` boundary;
- replacement of staging before pre-commit rollback;
- replacement of staging before post-commit cleanup.

Every case must abort and preserve both the foreign directory and the parked
reset-owned directory. Removing the pre-rename identity recheck makes its case
red (wrong exception after database commit), while disabling the shared
staging guard makes both recovery cases destructive and red. The journal
manifest has its own red-first persistence regression. A second parameterized
state-table test proves that pre-commit recovery refuses both missing home state
and a foreign source replacement, while a non-vacuity control accepts the
already-restored reset-owned source.

### Round-2 final verification

- First reviewer-reproduction run: 7 failed, 2 passed for the expected reasons.
- Independent-review state-machine additions: 2 failed, 7 passed before the
  final recovery-state fix.
- Focused reviewer and containment cases after the fix: 14 passed.
- Full reset set:
  `tests/test_scoped_identity_reset.py tests/test_scoped_reset_mutation_proof.py`
  - 89 passed.
- Standalone mutation proof: 21 passed.
- Literal mutations: recovery identity guard no-op - 4 failed; case-fold
  removal - 6 failed; pre-rename recheck removal - 1 failed.
- `ruff check` on canonical source, packaged mirror, and both reset test files:
  all checks passed.
- Canonical/package SHA-256 parity:
  `8661C1A7974FE5D1D7E24CEAA54D26FD0678E4CCBCAA36DED7940BA2EA151E7E`.
- `git diff --check`: clean.
- Independent read-only review of the final diff: Ready yes; no Critical,
  Important, or Minor findings.
- `.claude/.fleet_floor_state.json` and `.claude/.fleet_warn_stamp` remain
  untouched and untracked.
- No PR was opened.

LANE_RESULT: done - both Round-2 data-loss holes are structurally closed, mutation-pinned, fully verified, committed, and pushed
