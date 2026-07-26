# Control Station Landing Report

Date/environment: 2026-07-25, Windows, Python 3.14
Branch: `codex/osx-control-station`
Merged base: `origin/main` `f7142a5707d31d1e43d5a9996499b9716a81bebc`

## Merge and leftover-marker check

- `git fetch origin` followed by `git merge origin/main` completed with
  `Already up to date`; this branch already contains its prior clean main merge.
- Exact Python conflict-marker scan:
  `rg -n '^(<<<<<<< .+|=======|>>>>>>> .+)$' -g '*.py' .`
  found no actual markers. The earlier broad scan's only `=======` matches were
  legitimate reStructuredText table separators.
- `tests/test_universe_server_metadata.py` is byte-identical to `origin/main`
  and keeps the exact-set `extension_guide.tags` assertion.
- `tests/test_paid_market_migrations.py` is byte-identical to `origin/main` and
  keeps `MIGRATIONS.glob("*.sql")` at all migration-copy/discovery sites.
- `STATUS.md` is byte-identical to `origin/main`.

## Character-assertion resolution

The failing `<900` assertion was attached to the hidden legacy `extensions`
tool description, not to the 24,954-character `control_station` prompt. The
reconciled action catalog is legitimately 1,948 characters.

Resolution: option (b) for the actual size assertion, strengthened with option
(a)'s semantic invariant.

- Replaced `<900` with `<2600`. This leaves about 33% growth headroom over the
  reconciled 1,948-character catalog while remaining under half of the reviewed
  6,000-character MCP text ceiling.
- Pinned the advertised surface to exactly seven canonical handles:
  `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
  `converse`, and `get_status`.
- Explicitly asserted that the retired fat `extensions` tool is not advertised
  and that the `control_station` Tool Catalog equals the exact canonical set.
- Corrected a review-found semantic regression: legacy canon-ingest results now
  say that a later ingest of the same canon-source filename replaces its stored
  bytes/manifest entry; they no longer falsely claim `converse` performs that
  ingest operation. The packaged runtime mirror was regenerated.

## Green evidence versus clean main

- Clean-main comparison supplied by the host:
  `tests/test_universe_server_metadata.py` +
  `tests/test_universe_server_framing.py` -> `24 passed`.
- This branch, same two full files -> `24 passed`.
- Full branch-touched test-file gate plus metadata -> `536 passed`
  (`170` third-party deprecation warnings).
- Instruction-surface invariant file -> `18 passed`
  (`12` third-party FastMCP deprecation warnings).
- Test-first canon wording correction -> RED on the old false response, then
  GREEN; invariant + focused canon test -> `19 passed`.
- A stale main-identical assertion in `test_get_run_output_text_channel`
  expected the generic word “workflow” although its stated invariant is the
  workflow name. It was narrowed to the actual `Recipe tracker` name; the full
  touched-file gate is green.
- Ruff across all 60 touched Python files reports 54 `E501` findings. Running
  Ruff against the `origin/main` blobs for the same 59 existing paths reports
  the same 54 findings; normalized branch-vs-main delta is `0`. All are
  pre-existing mojibake separator-line debt, so none were changed. Ruff on the
  files modified during this repair passes.
- `python packaging/claude-plugin/build_plugin.py` staged 285 runtime files and
  returned `Import probe: probe-ok`.
- `git diff --check origin/main` passed.
- Independent review: no blocking findings after both requested corrections.

## PR and auto-merge

- PR: pending creation after the first report-bearing push.
- Squash auto-merge: pending.

## Deploy-time acceptance requirement

This is a public MCP-surface change. Hard Rule 11 remains a deploy-time gate:
run `scripts/mcp_public_canary.py --assert-handles` against the deployed
endpoint and complete a rendered chatbot conversation following `ui-test`.
Local tests and direct MCP checks do not replace that acceptance evidence.

LANE_RESULT: partial - all local branch gates are green; PR creation and squash auto-merge remain.
