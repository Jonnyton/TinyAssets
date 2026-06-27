# Orphaned `tests/test_phase7.py` Decision

**Author:** planner
**Date:** 2026-04-13

## Situation

`tests/test_phase7.py` contains a `TestDaemonControllerIntegration`
cluster (lines ~398-512) that references three `DaemonController`
methods not present in `tinyassets/__main__.py` and not present in
any commit on `main`:

- `controller._run_progressive_ingestion("test-universe")` (line 409)
- `controller._bootstrap_universe_runtime_files(...)` (line 424)
- `controller._bootstrap_retrieval_indices()` (lines 477, 510)

Four tests in the cluster depend on these. Tester flagged this;
`git log --all -S` confirms the method names literally never
existed in version control. Somebody wrote the tests for a
controller shape that was never merged.

The rest of `test_phase7.py` (`TestProgressiveIngestor`,
`TestOutputVersionStore`, `TestSeriesPromiseTracker`) tests
real modules that DO exist in `tinyassets/memory/` and should stay.

## Options

### Option A — delete the orphaned tests

Scope: remove the four tests in the
`TestDaemonControllerIntegration` cluster. Keep the file's other
three test classes. ~110 lines removed.

**Pros:**
- Simple. No design debate.
- Matches reality: those methods don't exist, the tests can't
  assert anything meaningful against them.
- Reduces red noise in CI.

**Cons:**
- Loses any design intent the original author encoded. Test
  signatures hint at features that *might* have been planned:
  bootstrap seeding of `work_targets.json` + `hard_priorities.json`
  from a new universe, and one-time retrieval index population
  from canon + prose on first run.
- If that intent is still valid, deleting makes it easier to forget.

### Option B — re-scope by implementing the missing methods

Scope: add `_bootstrap_universe_runtime_files(premise)` and
`_bootstrap_retrieval_indices()` to `DaemonController`. Also add
`_run_progressive_ingestion(universe_id)`.

**Pros:**
- The tests' assertions describe sensible behavior: a new universe
  should seed `work_targets.json` with at least `universe-notes`
  and `book-1` targets; on first daemon start, canon + prose
  should be indexed into the KG if the KG is empty.
- Those behaviors may already be partly present elsewhere under
  different method names. Some of this logic likely lives in
  runtime bootstrap or `ensure_seed_targets` — re-scoping could
  surface duplication worth consolidating.

**Cons:**
- Significant scope. Implementing three new methods with no
  product pressure behind them is speculative work.
- The tests were written without supporting implementation; there
  is no current incident or missing-feature report asking for
  them.
- Violates "don't add features for hypothetical future
  requirements" — the codebase already has bootstrap paths that
  work (sporemarch runs daily). If something is missing, let real
  usage surface it.

### Option C — skip-mark and defer (compromise)

Scope: add `pytest.mark.skip(reason="…")` to the four tests,
leaving the code in place as a TODO marker.

**Pros:**
- Keeps design intent visible.
- Unblocks CI immediately.

**Cons:**
- Accumulates cruft. Skip-marked tests rot; nobody unskippeds
  them.
- "Not urgent" (per STATUS.md) argues against preserving them as
  dead weight.

## Recommendation — Option A, delete

Reasons:

1. **No active requirement drives these tests.** No STATUS.md
   Concern, no user-sim finding, no bug report says "bootstrap
   seeding or first-run indexing is broken." The tests exist in
   isolation.
2. **The codebase already bootstraps universes successfully.**
   `ensure_seed_targets` in `tinyassets/work_targets.py` seeds the
   registry when targets are empty. Canon + prose indexing runs
   via retrieval's ingestion path under different triggers.
   Whatever these orphan tests were describing, the working system
   has its own solution.
3. **Preserving them is lossy in both directions.** Option B
   expands scope on speculation. Option C accumulates skip-rot.
   Neither produces clearer intent than the git log + this memo.
4. **Recovery is trivial.** The deletion commit is permanently
   addressable. If a real need surfaces for first-run bootstrap
   behavior later, `git show <commit>:tests/test_phase7.py`
   resurrects the design intent instantly, and a real
   implementation + test can be written with the incident it's
   responding to.

## Dev task shape

**One small dev task:**

- Open `tests/test_phase7.py`, remove the
  `TestDaemonControllerIntegration` class in its entirety (all
  four methods).
- Keep `TestProgressiveIngestor`, `TestOutputVersionStore`,
  `TestSeriesPromiseTracker` — those exercise real modules in
  `tinyassets/memory/`.
- Run `pytest tests/test_phase7.py -q` → should pass or reveal any
  real regression.
- Single commit message: `"Remove orphaned DaemonController
  integration tests from test_phase7.py — methods never
  existed on main."`

Not urgent. Bundle with another CI-hygiene PR if one is in flight;
otherwise file-and-forget.
