---
status: active
updated_on: 2026-05-01
---

# Run-Branch Resume-From Fixture Pack (Post-#18)

**Date:** 2026-04-27
**Updated:** 2026-05-01
**Author:** codex-gpt5-desktop
**Purpose:** eliminate test-data design time once the `tinyassets/api/runs.py`
lock clears for the accepted `extensions action=run_branch
resume_from=<run_id>` implementation.

## 1. Canonical Fixture Datasets

Create reusable fixtures in `tests/fixtures/`:

1. `runs_resume_from_source_catalog.json`
   - valid source run id owned by actor `alice`
   - missing run id case
   - cross-user run id owned by actor `bob`
   - invalid-state source run case

2. `runs_resume_from_context.json`
   - source branch id
   - target branch id
   - frozen source inputs
   - minimal checkpoint/artifact references supported by the current run model

3. `runs_resume_from_branch_mismatch.json`
   - source run whose continuation context cannot apply to the requested target
     branch
   - expected validation reason

## 2. Golden Response Snapshots

Expected payloads for stable assertions:

- `expected_run_branch_resume_from_success.json`
- `expected_run_branch_resume_from_not_found.json`
- `expected_run_branch_resume_from_forbidden.json`
- `expected_run_branch_resume_from_invalid_state.json`
- `expected_run_branch_resume_from_branch_mismatch.json`

## 3. Determinism Rules

- Freeze timestamps to fixed ISO values.
- Freeze source and target ids.
- Keep copied input ordering stable.
- Keep validation messages stable enough for exact substring assertions.

## 4. Test Mapping

- `test_run_branch_resume_from_preserves_default_run_branch_behavior`
- `test_run_branch_resume_from_carries_source_context`
- `test_run_branch_resume_from_not_found`
- `test_run_branch_resume_from_cross_user_forbidden`
- `test_run_branch_resume_from_invalid_state`
- `test_run_branch_resume_from_branch_mismatch`

## 5. Acceptance

Fixture pack is complete when a dev can implement the `resume_from` parameter
and plug in these fixtures/snapshots without inventing extra action verbs or
recency-only data models.
