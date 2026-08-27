# Lane: foreground run provider authority

**Branch:** `resume/run-provider-authority` (from `claude/run-provider-session`)
**OpenSpec change:** `openspec/changes/run-provider-authority/`
**PR:** #2559

## What this lane does

Foreground runs mint their own provider authority instead of borrowing an
ambient one. `_ForegroundRunProviderSession.admit()` is split in two:

- `prepare()` captures run identity, the Branch snapshot, and its content
  digest, and validates run state. No authority is minted.
- `_admit()` mints the authority, and fires lazily from `_ensure_admitted()`
  on first provider use, under a lock and idempotent on `self._receipt`.

So a run that never calls a provider never mints provider authority, and
admission validates against state pinned at prepare time rather than re-read at
use time -- the exact-revision shape this repo uses elsewhere.

## Corrected 2026-08-27

This file previously described a DIFFERENT lane -- "assigned consumer activation
+ visible refusal" on `claude/consumer-activation-visibility`. The branch was
repurposed for provider authority without updating it, and the
2026-08-26 handoff flagged the mismatch: **the commits are the truth.**

## State

Four commits on top of `main`. The last (`19524770`) was committed unreviewed
purely so a worktree teardown could not lose it; it has since been read and the
two-phase design above is what it implements. `tests/test_run_provider_session.py`
passes (10 tests).

Authority-critical: `pr-scope-guard` requires an exact-head cross-family review
receipt before this can merge.
