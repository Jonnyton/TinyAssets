# Red-main six-test repair — corrected after ADAPT

Date/environment: 2026-07-25, Windows, Python 3.14.3, branch
`codex/osx-main-red-2`.

## Correct-side findings retained

The correct-side review verified findings 1, 2, 3, and 6 green, so they remain
unchanged:

1. The server-instruction framing stays below the live `<1600` guard while
   retaining the first-contact relay contract.
2. The extensions description test checks the current action catalog rather
   than the superseded `<900` size cap.
3. Rule 7 remains named “Assume TinyAssets,” with whitespace normalization for
   the unchanged aggressive-assumption wording.
6. The compile-warning fixture retains the added `topic` state key required by
   exact partial-schema validation.

## Findings 4 and 5 — corrected side

### Finding 4: universe tool metadata

- Reverted the generic `workflow` tag from the `universe` tool in
  `tinyassets/universe_server.py` and its generated plugin mirror.
- Reclassified the failure as a stale test, as audit #1616 had already
  identified.
- Updated `test_tool_metadata_is_directory_ready` to assert equality with the
  exact tag set ratified by OpenSpec contract #1626, requirement “Registered
  tools publish exact discoverability and behavior metadata”:
  `{agent-workflow, ai-builder, collaboration, custom-ai, daemon,
  general-purpose, tinyassets, universe, universe-builder, workflow-builder}`.
  The canonical set contains `workflow-builder`, not `workflow`.

### Finding 5: extension guide prompt metadata

- Reverted the generic `workflow` tag from the `extension_guide` prompt in
  `tinyassets/universe_server.py` and its generated plugin mirror.
- Reclassified the failure as a stale test, as audit #1616 had already
  identified.
- Updated `test_prompt_metadata_is_present` to assert equality with the exact
  prompt tag set ratified by OpenSpec contract #1626:
  `{extensions, nodes, plugins, tinyassets}`.

## Green evidence

- All green commands below were rerun after merging current `origin/main`
  `e567c6c0a4a7bed45feaa9b0d5716b9c2f305854`.
- RED proof before the runtime reversion: both exact-set tests failed only
  because runtime contained the extra `workflow` tag.
- Corrected metadata tests: `2 passed`.
- Focused three-file run: `50 passed` (2 third-party deprecation warnings).
- `test_universe_server_directory_app.py`: `50 passed` (1 third-party
  deprecation warning).
- Remaining `test_universe_server*.py`: `194 passed` (3 third-party
  deprecation warnings).
- All `test_graph_compiler*.py` plus `test_input_keys_isolation.py`:
  `102 passed` (168 third-party deprecation warnings).
- `tests/test_branches.py`: `75 passed`.
- Ruff on all five changed Python paths: `All checks passed!`.
- `git diff --check`: clean.
- `python packaging/claude-plugin/build_plugin.py`: staged 278 runtime files;
  `Import probe: probe-ok`.
- Canonical/plugin mirror SHA-256 parity:
  `B41A2C2136705CD501A2EBFEFC4BA4B616FC795586D7D9E45C29EFC0491008C2`.
- `origin/main` `e567c6c0a4a7bed45feaa9b0d5716b9c2f305854` was merged
  after its unrelated `LANE_REPORT.md` addition caused the only preliminary
  add/add conflict.
- Final `git merge-tree --write-tree --messages origin/main HEAD` against the
  newer `origin/main` `0b8fb8c153427c0298dda8d62e9cb8af496de02d`
  exited 0: the canonical and mirrored server files auto-merged with no
  conflicts.

LANE_RESULT: done - findings 4 and 5 are corrected test-side, all required checks are green, and the branch is merge-clean.
