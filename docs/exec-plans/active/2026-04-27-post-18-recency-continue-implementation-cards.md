# Post-#18 Implementation Cards: `run_branch resume_from`

Date: 2026-04-27
Updated: 2026-05-02
Author: codex-gpt5-desktop
Status: Cards A-C code-shipped; live MCP verification remains

Decision stamp: F2 accepted by host on 2026-04-28. Drop Recency as a platform
primitive. Do not add standalone `my_recent*` or `continue_branch` action
verbs. Add one optional `resume_from=<run_id>` parameter to existing
`extensions action=run_branch`.

Implementation stamp: Cards A-B are present in `tinyassets/api/runs.py`; Card C
removed the standalone `continue_branch` dispatch route and prompt routing on
2026-05-02. Keep Card D until live MCP proof covers both default `run_branch`
and `run_branch resume_from=<run_id>`.

## Card A - Add Optional `resume_from`

- **Files:** `tinyassets/api/runs.py`, `tests/`
- **Goal:** teach the existing `run_branch` handler to accept
  `resume_from=<run_id>` while preserving exact behavior when the parameter is
  absent.
- **Input contract:** `docs/specs/2026-04-27-recency-and-continue-branch-primitives.md`
  section 2.
- **Tests:** use fixture pack
  `docs/specs/2026-04-27-recency-continue-fixture-pack.md`.
- **Done when:** default `run_branch` tests still pass and resume requests
  produce a new normal run/request envelope with source-run context attached.

## Card B - Source-Run Visibility And Carryover

- **Files:** `tinyassets/api/runs.py`, `tests/`
- **Goal:** resolve the source run under caller scope and carry only supported
  continuation context into the new run.
- **Done when:** success, not-found, forbidden, invalid-state, and branch
  mismatch cases are deterministic.

## Card C - Retire Stale Action Paths

- **Files:** `tinyassets/api/runs.py`, `tinyassets/api/market.py`, tests touching
  action routing
- **Goal:** avoid adding `_action_my_recent_runs`, `_action_my_recent`, or
  `_action_continue_branch` from the superseded 2026-04-27 plan.
- **Done when:** unknown-action fail-loud behavior is unchanged and no new
  Recency/standalone-continue action appears in dispatch tables.

## Card D - Verification Runbook

- focused tests for cards A-C
- full relevant suite slice for runs dispatch
- live MCP probe after merge using `extensions action=run_branch` both with and
  without `resume_from`

## Sequencing

1. A
2. B
3. C
4. D

No further product re-scope is needed unless `#18` changes the run dispatch
architecture.
