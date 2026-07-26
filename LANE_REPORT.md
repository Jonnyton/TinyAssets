# Control Station Merge/Land Report

Date/environment: 2026-07-25, Windows, Python 3.14
Branch: `codex/osx-control-station`
Merged base: `origin/main` `f7142a5707d31d1e43d5a9996499b9716a81bebc`

## Merge conflicts and resolutions

- `LANE_REPORT.md`: replaced the conflicting historical lane reports with this
  current merge/verification report.
- `tests/test_universe_server_framing.py`: kept origin/main's Rule 7 whitespace
  normalization and “Assume TinyAssets” wording, retained origin/main's semantic
  action-catalog checks, and preserved this branch's explicitly requested
  reverted `< 900` extensions-description assertion. Kept origin/main's
  `< 2200` universe-description assertion.
- `tests/test_universe_server_metadata.py`: took origin/main's exact canonical
  tag-set assertions from PR #1789.
- `STATUS.md`: origin/main's version was accepted automatically without a
  conflict.
- `tests/test_paid_market_migrations.py`: retained origin/main's dynamic
  `MIGRATIONS.glob("*.sql")` migration-list behavior.
- Preserved this branch's control-station/instruction-surface reconciliation,
  runtime-payload-guidance fixes, and extended invariant test.

## Verification evidence

Green:

- Invariant:
  `python -m pytest tests/test_mcp_instruction_surfaces.py -q`
  -> `18 passed` (12 third-party deprecation warnings).
- Ruff on the 52 touched Python files outside the previously disclosed
  mojibake-separator baseline files -> `All checks passed!`.
- Plugin build:
  `python packaging/claude-plugin/build_plugin.py`
  -> staged 285 runtime files; `Import probe: probe-ok`.

Not green:

- The six-test PR #1789 regression selection -> `5 passed, 1 failed`.
  The sole failure is
  `test_extensions_tool_description_points_to_prompts_for_rules`: the requested
  restored `< 900` assertion observes 1,948 characters. PR #1789 did not shorten
  that description; it removed the stale size cap and replaced it with semantic
  action-catalog assertions. Preserving the branch assertion therefore conflicts
  with the premise that #1789 made this selection green.
- The earlier report's other three baseline-red cases remain red:
  `test_get_run_output_text_channel` still receives “Output from tinyassets”
  rather than the asserted word “workflow”; both
  `test_run_recursion_limit.py` invocation tests still fail because their
  temporary databases have no `runs` table (`12 passed, 2 failed` for that
  file). The relevant test/runtime regions are unchanged from current
  origin/main.
- Full Ruff across all 60 touched Python files -> 54 `E501` findings in
  `tinyassets/api/market.py`, `tinyassets/api/runs.py`, and
  `tinyassets/runs.py`, plus their generated mirrors. Directly linting the
  current origin/main blobs reproduces all 27 canonical findings (7, 3, and 17
  respectively); the mirrors double the total.

No test or lint rule was weakened to manufacture a green result.

## Push and PR state

- PR #1763 is already merged, but its head was
  `coord/control-station-claim`, not this branch.
- `gh pr list --head codex/osx-control-station --state all` returns no PR.
- Resolved merge commit `fab5e7c2` was pushed to
  `origin/codex/osx-control-station`.
- No new PR or auto-merge was opened/armed because the requested gate set is
  demonstrably red. Arming a known-red public-surface change would violate the
  verification gate.

## Deploy-time acceptance

Hard Rule 11 requires the post-deploy public canary with `--assert-handles` and
a rendered chatbot conversation following `ui-test`. Those are deploy-time
checks, not part of this branch-only lane.

LANE_RESULT: blocked - merge is resolved and core invariant/build are green, but the preserved assertion and unchanged baseline failures prevent a green landing or auto-merge.
