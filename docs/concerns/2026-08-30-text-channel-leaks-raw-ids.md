# The text channel still leaks raw ids — and the tests that would catch it are quarantined

**Filed:** 2026-08-30 · **Severity:** P2 — phone/chat users read `text` verbatim; ids belong in
`structuredContent` (task #58). **Found by:** Codex diagnosis of CI reds on #2690/#2693.

## The finding

Four tests fail on `main` and every PR, and `required-tests` tolerates them because they sit in
`.github/known-failing-tests.txt`:

- `tests/test_text_channel_id_redaction.py::test_goal_bind_text_hides_goal_id_and_branch_def_id` —
  `_action_goal_bind` interpolates the raw `goal_id` into `text` (`tinyassets/api/market.py:~1454-1458`);
  ids are separately kept in structured fields, so the text copy is the defect.
- `…::test_patch_branch_text_hides_branch_def_id` — `patch_branch` prints `branch_version_id`
  (`tinyassets/api/branches.py:~2981-2985`), whose format `<branch_def_id>@<hash>` embeds the
  whole `branch_def_id` (`tinyassets/branch_versions.py:277`).
- `tests/test_universe_nodes.py::TestWorldbuildCanonGeneration::test_handle_{contradiction,expansion}_rejects_symlinked_existing_file` —
  containment still holds (the escaping symlink is skipped in `tinyassets/ingestion/canon_io.py:146`
  and `canon_names.py:25` raises `canon filename escapes…`), but the tests assert the older
  wording `canon existing file escapes`. Stale assertion, not a lost guard.

There is no generic id-redaction post-processor; safe text is built per action, so each leak is a
one-line omission.

## Resolving

Omit the raw ids from `text` at the two sites (keep them structured), update the two symlink
assertions to a stable `escapes` match, then remove all four entries from
`known-failing-tests.txt` in the same PR (that ledger edit needs the exact-head review receipt the
scope guard demands). Delete this file when the four tests are green and unquarantined.
