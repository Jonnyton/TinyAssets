---
severity: P2
title: The required test surface carries a ~one-flake-per-run floor on main
filed: '2026-10-03'
summary: 'Three consecutive main-push `required-tests` runs each failed exactly ONE test, and all three were DIFFERENT (`test_dev_hygiene`, `test_open_receivers`, `test_mcp_probe` latency) on unchanged code. None is quarantined. So `main-red`''s attempt-1 re-run is load-bearing rather than a nicety, a share of the merge queue''s `failed_checks` drops are flakes not regressions, and a lone failure under a lone entry is weak evidence of causation'
---

# The required test surface carries a ~one-flake-per-run floor on main

**Filed:** 2026-10-03
**Verified:** 2026-10-03, from the `junit-required-tests` artifact of three
consecutive `push` runs of Tests on `main` (37093191928, 37088463393,
37087028562)
**Severity:** P2 — nothing is unprotected; what is wrong is that a red
`required-tests` on main is not by itself evidence of a regression

Each of those three runs failed **exactly one** test, and all three were
different tests, on code that had not changed in the relevant areas:

| run | the one failure |
|---|---|
| 37093191928 | `tests/test_dev_hygiene.py::test_apply_removes_a_merged_worktree_and_leaves_the_kept_one` |
| 37088463393 | `tests/test_open_receivers.py::test_the_sender_cannot_read_the_owners_workflow_step_or_run` |
| 37087028562 | `tests/test_mcp_probe.py::test_latency_subcommand_reports_elapsed_ms` |

A fourth, `tests/test_mcp_probe.py::test_latency_raw_includes_response`, failed
in merge-group run 37100054097, and a fifth observation of that same test at PR
time is attributed in the addendum below. None of them is in
`.github/known-failing-tests.txt`.

## Why this is filed rather than quarantined

A `flaky` ledger entry would make these verdict-neutral and stop the noise, and
that is the wrong trade here: `MAX_QUARANTINE` ratchets the ledger down
deliberately, and a flake that is hidden stops being fixed. The first two are
already being fixed — `test_dev_hygiene` by #4347 and `test_open_receivers`
likely by #4345, both queued as of filing. The `test_mcp_probe` latency cases
are new and have no owner yet; they are the reason this file exists.

## What it changes about reading CI

1. **`main-red`'s attempt-1 re-run is load-bearing**, not a nicety. At roughly
   one flake per run, a policy that reverted on the first red would revert
   constantly and almost always the wrong change.
2. **Some merge-queue `failed_checks` drops are flakes.** The lean-CI note
   measures 39 of them in four days and attributes them to repo-wide ratchets;
   this floor is a second cause, and it ejects entries that broke nothing.
3. **A lone failure under a lone queue entry is weak evidence of causation.**
   `scripts/miss_attr.py` reports such cases separately for exactly this reason
   rather than counting them as escapes
   (`docs/design-notes/2026-10-02-affected-only-merge-gate.md`).

## Addendum 2026-10-03: the `test_mcp_probe` mechanism, attributed

A fifth observation gives the `test_mcp_probe` latency cases a cause, and it is
not the one guessed below.

`tests/test_mcp_probe.py::TestSubcommands::test_latency_raw_includes_response`
failed again at PR time -- not only in a merge group -- in `affected-tests 1/6`
of run 37110450239 (job 111167158641) on PR #4368. **Re-running that identical
shard on that identical head passed.** Same code, same selection, different
result: direct evidence of non-determinism, rather than the inference from
"three consecutive runs, three different tests" above.

The failure is `StopIteration`, **not** a wrong `latency_ms`. That matters,
because it means the fix proposed below would not fix it:

```python
times = iter([20.0, 20.05])
monkeypatch.setattr(mcp_probe.time, "monotonic", lambda: next(times))
```

`mcp_probe` does `import time`, so `mcp_probe.time` **is** the `time` module --
verified, not assumed (`m.time is time` -> `True`). So that `setattr` replaces
`time.monotonic` **process-wide** for the duration of the test, backed by a
finite two-element iterator. `scripts/mcp_probe.py:_cmd_latency` makes exactly
two `monotonic()` calls on each of its paths (235 and 259, or 235 and 238), so
the iterator is sized for the test alone. **Any other code in the process that
calls `time.monotonic()` inside that window steals a value**, and the next call
in the test raises `StopIteration`.

So the clock is already pinned -- too tightly. The clock is not the variable;
the number of callers is.

### Why this gets more likely, not less

Anything concurrent that consults the clock is enough: a lingering worker
thread, and `ThreadPoolExecutor`'s own queue waits consult `time.monotonic`
directly. The repo is adding background work (PR #4368 introduces a shortlist
refresh pool, which clears itself between tests via a `conftest` fixture). In
fairness to that PR, the one failure did not reproduce on re-run and the pool is
joined after every test -- but the point stands independently of any one change:
a process-wide clock patch against a finite iterator is a landmine whose
probability rises with the repo's concurrency.

### Resolving it

The fix is a NARROW clock seam, not a longer sequence. Checked both by hand
before writing this down:

- `itertools.chain([20.0, 20.05], itertools.repeat(20.05))` removes the
  `StopIteration` class, but a stolen value then makes the test compute
  `20.05 - 20.05` and assert `latency_ms == 0 != 50`. That trades a loud
  error for a quieter wrong-value flake -- no better, and harder to read.
- The real fix is that no other caller can consume the sequence at all: give
  `_cmd_latency` an injectable clock and patch THAT, instead of the shared
  `time` module. This is the repo's stated preference anyway -- test switches
  by injection, not by reaching into a global.

Both `test_latency_raw_includes_response` and
`test_latency_subcommand_reports_elapsed_ms` share the shape, so one seam
fixes both. Whoever picks this up should treat any process-wide
`monkeypatch.setattr(<module>.time, ...)` in the suite as the same class of
landmine.

Not ledgered, for the reason this file already gives: a `flaky` entry would make
it verdict-neutral and stop it being fixed, and the cause above is small enough
to fix properly.

## Resolving it

Attribute the two `test_mcp_probe` latency cases: the addendum above does, and
the cause is a process-wide clock patch against a finite iterator rather than a
slow runner. Delete this file when the five names above either pass consistently
or carry owners.
