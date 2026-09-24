# Execution-choice authoring — build verification record

**Date:** 2026-09-24 (03:50–04:00 UTC)
**Change:** `openspec/changes/preserve-snapshot-execution-choices`
**Branch:** `codex/execution-choice-authoring`, worktree
`wf-execution-choice-authoring`, base `ff1320d5`
**Author of this pass:** Claude Opus 5 (verification only — no runtime change)

This records what was *measured*, and separates it from what was reasoned. It
is not an independent review: the author of the tests wrote this file. Final
independent review is root's.

## Environment

| | |
|---|---|
| Host | Windows 11 Home 10.0.26200, local worktree |
| Python | 3.14.3 (local). **CI runs 3.11 and stays authoritative.** |
| Ruff | 0.15.8 |
| Temp root | `C:/Users/Jonathan/AppData/Local/Temp/ta-pt-ec` — outside the repo, per `tests/conftest.py` |
| Services | none. No Docker, no WSL, no browser, no production, no credentials. |

A local Windows run is evidence, not an oracle. Nothing here touches the
sandbox, filesystem helpers, process limits or the workspace, so the Linux
oracle was not required; CI remains the gate.

## Test run — this file only

```
python -m pytest tests/test_branch_execution_choice_authoring.py -q
51 passed in 6.47s
```

**51 passed, 0 failed, 0 skipped, 0 xfail** (2026-09-24 03:52 UTC).

Composition:

| Group | Cases | Red-first status |
|---|---|---|
| Capability pass (pre-existing) | 45 | **29 RED against `ff1320d5`, 16 GREEN there** |
| `TestLegacyDatabaseMigration` (added this pass) | 6 | **Not executed against `ff1320d5`.** No red-first claim. |

The 16 green-on-both cases are deliberate compatibility pins (unknown-op
refusal, legacy-row absence, the unset snapshot form, unknown-spec-key
tolerance, the `validate_concurrency_budget` unit checks). The module docstring
now says this instead of claiming every assertion was red-first.

The 6 new cases assert columns that do not exist at `ff1320d5`, so they could
not pass there — that is reasoning about the unfixed tree, stated as reasoning,
not a measured red run.

## What the new tests close

The gap: the previous legacy assertion passed a **Python dict with missing
keys** to `_branch_def_from_row`. That proves the reader tolerates absent keys.
It does not prove a real database survives the migration, which is what a live
install depends on, and `design.md` promised an old-writer regression that did
not exist.

`TestLegacyDatabaseMigration` (`tests/test_branch_execution_choice_authoring.py`):

1. `test_the_fixture_really_is_pre_migration` — premise guard: the table has
   exactly the 17 `ff1320d5` columns and neither new one. Without this the
   rest of the class could be vacuous.
2. `test_migrating_adds_the_columns_and_preserves_every_old_field` — after
   `_initialize_author_server_locked`, all five ALTER-added columns exist and
   **every** one of the 17 legacy field values is byte-identical (whole-row
   compare, not a sampled column). Both new columns are NULL.
3. `test_the_migrated_row_reads_back_as_unset_through_the_real_reader` —
   `get_branch_definition` over an actual migrated row returns the old
   name/entry_point/version and both choices as `None`.
4. `test_rerunning_the_migration_is_idempotent` — three migration passes: no
   `duplicate column name`, identical column list, identical row.
   `_initialize_author_server_locked` is called directly on purpose;
   `initialize_author_server` short-circuits on `_AUTHOR_SERVER_INITIALIZED`,
   so re-calling it would prove the cache works, not the migration.
5. `test_a_migrated_install_can_then_store_and_clear_both_choices` — the
   migrated legacy install becomes authorable: set both, clear both, and the
   untouched legacy row stays untouched.
6. `test_an_old_writer_erases_the_choices_it_does_not_know_about` — the
   promised boundary. The `ff1320d5` 20-column `INSERT OR REPLACE` (reused
   verbatim; the current writer's first 20 values are the old column order
   unchanged, asserted) replaces a row carrying both choices and **erases**
   them, while every other field survives. This pins the `DISAGREE_EVIDENCE`
   from the pre-build review so the rollback note cannot quietly go stale.

No fixture touches a real data dir; every base path is under pytest `tmp_path`.

## Ruff — baseline comparison, not a bare run

Same repo config both sides; baseline piped from `ff1320d5` through
`ruff check - --stdin-filename <path>`.

| File | `ff1320d5` | working tree |
|---|---|---|
| `tinyassets/branches.py` | 0 | 0 |
| `tinyassets/daemon_server.py` | 8 | 8 |
| `tinyassets/api/branches.py` | 3 | 3 |
| plugin mirror `.../api/branches.py` | 3 | 3 |
| `tests/test_branch_execution_choice_authoring.py` | n/a (new) | **0 — all checks passed** |

All 11 pre-existing findings are `E501` (line length) and are unchanged in
count and identity. **This change introduces zero new Ruff findings.**

## Root's independent work, as reported to this pass

Root independently reviewed the runtime and ran **149 tests, 0 skipped**, with
no basic runtime blocker found. That figure is **root's, not re-measured here**
— this pass ran one file only, by instruction. It is recorded as an input, not
as evidence this session produced.

The pre-build review artifact exists and is real:
`docs/reviews/2026-09-24-execution-choice-authoring-shape.md` (independent
Codex root review, 2026-09-24 UTC) — AGREE on the additive nullable columns,
existing authorized operations, explicit clearing, immutable versions, no new
provider authority, PLAN unchanged; one `DISAGREE_EVIDENCE` on the rollback
claim, now folded into `design.md` and pinned by test 6 above.

## Documentation corrections made this pass (comments/docs only)

1. **Receipt echo overclaim.** The receipt echoes the stored policy dict
   verbatim and validation tolerates unknown policy keys, so a typo *inside*
   the dict is echoed back looking applied. Corrected in
   `tinyassets/api/branches.py`, the plugin mirror, `design.md`, the spec delta
   and the test docstring: the echo is a **report**, exposing the FIELD-level
   miss (a misspelled top-level key leaves the choice `null` while the call
   reports success), **not** an unknown-key detector. Validation scope is
   unchanged and no allowlist was added — the residual gap is now stated
   rather than papered over.
2. **`design.md` surface table** said build reads the choices "via
   `_spec_get`". It does not — `_spec_get` falls through on an explicit null.
   Corrected to the dedicated `_choice_present`/`_choice_value` presence
   resolution, which is what the code does.
3. **Pre-build review marked performed**, with the artifact cited, replacing
   "pending, not done".
4. **Historical citations pinned.** `design.md` Context now states up front
   that every line reference is pinned to `ff1320d5` and describes the tree
   before this change, readable with `git show ff1320d5:<path>`.
5. **Red-first counts made honest** in the test module docstring, `design.md`
   and task 2.6: 29 RED / 16 GREEN, not "every assertion red". Task 2.7 added
   for the new tests, explicitly making no red-first claim.
6. **Spec delta narrowed.** "a misspelled key cannot return success" exceeded
   the validator. Now: known-invalid fields produce explicit errors, applied
   receipts must report the choices actually stored, and an unknown key inside
   a forward-compatible policy is stored rather than refused — unknown-key
   forward compatibility explicitly preserved.

## Open — not done here, not claimed

- **CI:** not run this pass. CI is authoritative and has not reported on these
  edits.
- **Plugin mirror rebuild:** the mirror comment was edited by hand to match;
  `python packaging/claude-plugin/build_plugin.py` was **not** run this pass,
  so `mirror-parity` is unverified.
- **Deploy:** nothing merged, nothing deployed. `deployed_sha.py` and
  `mcp_public_canary.py` not run — no production surface was touched.
- **UI proof:** the rendered-conversation acceptance (task 3.2, an uncoached
  author setting and reading back a budget through the live connector) is
  **not done**. It is the final chatbot-surface proof and nothing here
  substitutes for it.
- **Independent review of this pass:** root's. The tests and this record share
  an author, which is exactly the condition self-review does not satisfy.

## Files touched

- `tests/test_branch_execution_choice_authoring.py` — +6 cases, docstring
  corrections.
- `tinyassets/api/branches.py` + plugin mirror — comment only.
- `openspec/changes/preserve-snapshot-execution-choices/{design,tasks}.md`,
  `.../specs/graph-execution-substrate/spec.md` — corrections above.
- `output/execution-choice-finalize-result.md`, this file.

No commit, no push.
