# The visibility test double turns "undeclared" into "public" repo-wide

**Filed:** 2026-09-26 | **Verified:** 2026-09-26 | **Severity:** P2
**Source:** Codex cross-family review of PR #4019, finding C7
(`DISAGREE_CONCERN`).

> Replaces the reviewer's full PR-#4019 artifact. The three
> `DISAGREE_EVIDENCE` findings in that review (delegated writers could publish as
> the owner; the migration skipped undeclared universes as "already closed";
> `metadata_only` disclosed raw content through a legacy reader) were **fixed in
> #4019 itself**, each with a mutation-proven test. This file keeps only what
> that PR did not resolve.

## Source (verbatim)

> DISAGREE_CONCERN C7: creation tests are immune to the double, but a global
> undeclared=>PUBLIC patch is not evidence of production startup behavior. Use
> explicit public fixtures or an opt-in marker and strict tests for callers
> crossing the startup/default boundary. No additional concrete regression was
> established solely from this fixture.

## What the fixture does

`tests/conftest.py::_emulate_deployed_visibility_backfill` is **autouse for every
module** except those in `_STRICT_VISIBILITY_MODULES` (currently
`test_universe_visibility` and `test_private_by_default`). For any universe with
no explicit declaration it returns `PUBLIC`, so several hundred pre-visibility
tests can build a bare directory and assert public-reader behaviour without each
re-declaring.

Until 2026-09-26 that was a faithful emulation: the production backfill derived
`public` from the legacy `public_read` bit. It no longer is — the backfill
declares `private` (founder, 2026-09-26). PR #4019 kept the fixture's behaviour
and rewrote its docstring so it reads as "these legacy modules' bare directories
stand for a universe whose owner chose public".

## Why that is not sufficient

Renaming the assumption does not establish that those tests model publication.
Each of those modules asserts its own concern (status shape, word count,
telemetry, ledger) and is simply indifferent to visibility; the fixture makes
them pass either way. The specific gap: **no test outside the two strict modules
crosses the startup/default boundary**, so nothing in the suite would notice if a
reader that used to work on a freshly-booted deployment stopped working now that
boot declares `private`.

What is *not* claimed: no concrete regression has been attributed to the double.
It is a coverage hole, not a known defect.

## What would settle it

1. Explicit public fixtures — or an opt-in marker — in the modules that actually
   need a published universe, and no repo-wide autouse patch. This is a mass
   fixture migration across several hundred tests; it was kept out of #4019
   deliberately, because mixing a harness migration into an authority change makes
   both harder to review.
2. At least one test per surface that runs the **real** boot path
   (`run_visibility_startup_gate`) and then drives a reader, with no double
   installed — the startup-to-reader path that currently has no coverage.
3. A live check is the honest final word here: boot a deployment with legacy
   undeclared universes and confirm no reader a real user depends on went dark.
   PR #4019's review was static and said so.

Delete this file when the autouse double is gone, or when the startup-to-reader
path is covered un-emulated and the remaining fixture is scoped to modules that
declare their universes explicitly.
