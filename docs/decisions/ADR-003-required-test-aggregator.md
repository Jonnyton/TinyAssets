# ADR-003: A Required Status Check That Tests Code

## Status

Proposed — the workflow is landed and green, but **making it required is a host
decision**. See "What the host must run" below. Until that command is run, this
gate reports but blocks nothing.

## Date

2026-07-21

## Context

`main` had two required status checks. Neither tested code behaviour:

| Required check | Workflow | What it actually verifies |
|---|---|---|
| `policy` | `daemon-request-policy.yml` | Reads the PR's `writer:`/`checker:` labels. Every branch is `false`, no violation fires, check passes. |
| `Diff scope declared` | `pr-scope-guard.yml` | Whether release-critical paths were *declared* via the `infra-change` label. Its own honesty note says it "is a scope-declaration gate, not a security control". |

Both premises were confirmed empirically, not by reading:

- `policy` reported **success** on PR #1502, which carries no writer/checker
  labels at all.
- `gh api repos/Jonnyton/TinyAssets/branches/main/protection` returns exactly
  `["policy", "Diff scope declared"]`, with `required_pull_request_reviews: null`
  — so no human review is required either.

Since 2026-07-22 `auto-enroll-merge.yml` enrols every non-draft PR for
auto-merge, and merges flow onward to production. The composition is the risk:
**code could reach live users without a single behavioural gate anywhere in the
chain.** That is the gap this ADR closes. The merge automation itself is fine —
it was correctly delegating safety to branch protection; branch protection just
had nothing behavioural to delegate to.

## Decision

### 1. One required check, named `required-tests`

Added by `.github/workflows/tests.yml`. Branch protection contexts are job
*names*, so the job is named `required-tests` and that string is the context.
Renaming the job silently detaches the requirement — a comment in the workflow
says so at the definition site.

### 2. It runs unconditionally — no `paths:` filter, no job-level `if:`

This is the non-negotiable property. A **required** check that is path-filtered
never reports on PRs outside its paths, and those PRs hang forever on
"Expected — waiting for status". This repo already knows that failure mode:
`lint`/actionlint is path-filtered and must therefore never be made required.

Every exit path in the gate produces a conclusion for the same check name,
including the fail-closed paths (no junit written, pytest internal error).

### 3. `pull_request`, not `pull_request_target`

Testing a PR means *executing* the PR's code, so it must run in the untrusted
context where the token is read-only and secrets are withheld. This is the exact
opposite of the choice `pr-scope-guard.yml` makes — that one reads only metadata
and uses `_target` so a PR cannot edit the workflow judging it. The tradeoff
this creates is handled in "Residual risk" below.

### 4. The split: `required-tests` (blocking) vs `slow-tests` (reported)

The brief asked for a proposed split rather than an assumed one, and the
measurement moved the answer twice.

First measurement: the full non-`slow` suite runs **9,139 tests in ~166 s**
under `pytest-xdist -n auto --dist loadfile`. That suggested throughput was a
non-issue and the whole suite could be the gate — no curated subset needed.

Second measurement killed the parallelism (see "Why serial" below), so the gate
runs serially and costs more wall-clock. The split is therefore **by
trustworthiness, not by speed**:

- **`required-tests`** — the entire suite except the `slow` marker, run
  serially. Blocking (once the host makes it required).
- **`slow-tests`** — the 9 stress/race tests behind the repo's opt-in `slow`
  marker, run serially. These previously had **no CI runner at all**, which
  contradicts the AGENTS.md rule that uptime work ships with a concurrency/load
  proof. Reported but **not required** initially: stress tests are the likeliest
  source of flake, and a flaky *required* check trains everyone to re-run until
  green, which is how a gate stops meaning anything. Promote it once it has a
  clean track record.

### 5. Why serial — parallelism made the gate's verdict non-deterministic

`pytest-xdist` was the obvious choice and it was wrong here.

Some test in this suite leaks global state — a patched `subprocess`, most likely
— and poisons every later test scheduled on the same worker. One measured run
put **70 of its 149 failures on worker `gw2` alone**, against 5, 11 and 6 on the
other three. The clearest symptom: a `git diff --name-only --cached` inside a
fresh temp repo returned `['https://github.com/x/x/pull/99']` — another test's
data, surfacing through a subprocess call that should have been isolated.

Because `--dist loadfile` assigns files to workers from the file list, **adding a
single test file moved ~34 tests in and out of the failure set** between two runs
of otherwise-identical code. A gate whose verdict depends on scheduling cannot
carry a committed baseline: it would fail PRs for sins they did not commit, and
the quarantine list would need rewriting on every file addition.

Serial execution does **not** fix the leak. It makes it *deterministic*, which is
the property a gate actually needs. The cost is wall-clock; the alternative was a
faster check that is not trustworthy, which is the thing this ADR exists to stop.

Fixing the underlying state leak is worth doing on its own — it would restore
~4x parallelism and remove a whole class of order-dependent test lies. It is
deliberately **not** bundled into this change.

### 6. The gate enforces "no NEW failures", not "green suite"

On its first run against `main` the gate found **106 failures and 14 errors that
predate it**. Requiring a green suite on day one would have blocked every PR in
the repo; the gate would have been reverted within the hour and `main` would
still have nothing. So `scripts/ci_required_tests.py` enforces the property that
actually protects production:

> **No PR may introduce a test failure that `main` did not already have.**

Already-broken tests are enumerated by node id in
`.github/known-failing-tests.txt`, generated reproducibly from a CI junit
artifact (`--emit-quarantine`), never hand-typed. The list is **ratcheted**: an
entry that stops failing is a hard error telling you which line to delete, so
fixed tests cannot rot in the file and quietly re-cover a future regression.
A small number of genuinely-alternating tests carry an explicit `flaky` prefix,
which exempts them from the ratchet only — they are still tolerated, still
visible, still countable.

The list may only shrink. It is technical debt with a name, a count, and a
one-way door — not a subset chosen because it happened to be green.

## What this already caught

The gate paid for itself on its first run, which is the strongest evidence that
a behavioural check was missing.

Three tests (`test_wiki_path_resolver.py`, `test_data_dir_resolver.py`)
monkeypatched the **global** `os.name` to `"nt"` while running on Linux. That
poisons `pathlib`: `Path()` dispatches to `WindowsPath`, which raises
`NotImplementedError` on Linux — and raises *again* inside pytest's own failure
reporting (`Path(os.getcwd())` in `nodes._repr_failure_py`). An ordinary test
failure therefore became an xdist `INTERNALERROR` that killed the worker and
aborted the session.

Consequences, all invisible before this gate existed:

- `tests/test_data_dir_resolver.py` recorded **zero** testcases in CI while the
  summary still reported thousands of passes.
- **~2,300 tests were silently not running** — 6,774 reported passes before the
  fix, 9,022 after.
- Two runs of *identical code* executed test sets differing by 26 tests.

Fixed by making those three tests `skipif(os.name != "nt")`. A faked `os.name`
cannot prove "actual Windows" behaviour anyway — which is what their own
docstrings claim to test.

It also surfaced two problems left deliberately unfixed here, because each is its
own piece of work and bundling them would make this change unreviewable:

- **A global-state leak between tests** (see "Why serial"). Worth fixing: it
  would restore ~4x parallelism and remove a class of order-dependent results.
- **9 `slow` concurrency tests had no CI runner at all**, and the tray tests
  cannot even be *imported* on a headless runner (`Xlib.error.DisplayNameError`).
  The `slow-tests` job now runs the former and skips collecting the latter.

## Residual risk — stated plainly

**A PR can rewrite the gate that judges it.** `required-tests` runs from the PR's
own checkout, because testing PR code requires executing PR code. A PR can
therefore replace the test command with a no-op while keeping the check name, and
go green. Branch protection requires no review (`required_pull_request_reviews:
null`), so nothing else catches it.

Partial mitigation landed here: `pr-scope-guard.yml` now treats
`scripts/ci_required_tests.py` and `.github/known-failing-tests.txt` as
release-critical, alongside `.github/workflows/`. Neutering the gate is still
*possible*, but it can no longer be done **silently** — it requires an explicit
`infra-change` declaration visible in the diff.

This is a declaration control, not a security boundary — the same honest framing
`pr-scope-guard.yml` uses about itself. **The real fix is a host action:** require
a non-author approving review for changes to these paths (a GitHub ruleset), or
enforce the gate as an organisation-level required workflow. Recommended, not
assumed.

Likewise, adding a line to `.github/known-failing-tests.txt` can excuse a test
you broke. That is deliberate — the alternative is no gate at all — and it costs
a reviewable line in the diff on a scope-guarded path instead of an invisible
regression riding in on a green check.

## What the host must run

**Not run by this PR — branch protection is a host decision.**

Add `required-tests` to the existing required contexts, preserving both current
ones and `strict`:

```bash
gh api --method PATCH \
  repos/Jonnyton/TinyAssets/branches/main/protection/required_status_checks \
  -F strict=true \
  -f 'contexts[]=policy' \
  -f 'contexts[]=Diff scope declared' \
  -f 'contexts[]=required-tests'
```

Verify it took effect:

```bash
gh api repos/Jonnyton/TinyAssets/branches/main/protection \
  --jq '.required_status_checks.contexts'
# expect: ["policy","Diff scope declared","required-tests"]
```

**Preconditions before running it:**

1. This PR is merged, so `required-tests` exists on `main`. Adding a context that
   no workflow produces hangs every open PR on "Expected".
2. A green `required-tests` run exists on `main`.

**Rollback** — remove just this context, leaving the others intact:

```bash
gh api --method DELETE \
  repos/Jonnyton/TinyAssets/branches/main/protection/required_status_checks/contexts \
  -f 'contexts[]=required-tests'
```

Do **not** add `lint`, `actionlint`, or any other path-filtered workflow as a
required context.

### After the flip: backfill the open PRs

An open PR that has no `required-tests` result sits on "Expected" and cannot
merge. Push any commit, or `gh pr update-branch <n>` for BEHIND ones, to
generate the `synchronize` event that produces one. In practice `main` moves
often enough here that PRs go BEHIND on their own, so this is self-healing —
but check the open set right after flipping.

**A conflicted PR produces no run at all.** `pull_request` workflows execute
against the generated merge ref, which GitHub cannot create while the PR
conflicts with its base — so on a DIRTY PR *every* `pull_request` workflow is
silently absent while `pull_request_target` ones still run, and the required
context stays "Expected" forever. Observed on this very PR on 2026-08-02
(head `54b25d84`: only the two `_target` checks ran; merging `main` restored
all six immediately). That state is a conflict signal, not a broken gate —
resolve the conflict, never weaken the check. Check `gh pr view <n> --json
mergeStateStatus` before diagnosing a missing required check.

## Evidence of record (2026-08-02)

| Claim | Evidence |
|---|---|
| Baseline captured honestly | run `30767266528`: 12,747 ran / **483 failing** across 72 files (up from 189 on 2026-07-22 — fifteen days of ungated, review-less merges) |
| Ledger absorbs exactly the baseline | run `30768520337`: ran 12,747, failing 483, known-broken 483, **NEW 0, stale 0**, `required-tests` = success |
| Count is deterministic, not flaky | identical 12,747/483 across two independent runs |
| Gate goes red on a novel failure | run `30773503892` with one injected failure (reverted in the next commit) |
| Real runtime | ~26 min serial (a 30-min job timeout killed run `30766011005` at 30:15; raised to 50) |
| Cannot pass vacuously | `MIN_RAN_FLOOR` = 10,000 vs 12,747 measured; a deselect-everything run yields 0 new failures + 0 stale and is caught *only* by the floor (regression test) |
| Cannot be neutered by its own PR | scope guard demands an exact-head review receipt for edits to `tests.yml`, `ci_required_tests.py`, `known-failing-tests.txt`, `drain_review_gate.py`. Deletion-only ledger edits are exempt, decided by **comparing parsed ledger content** read through the **git tree/blob API** (never diff metadata, never the Contents API). Five fail-opens were caught across four cross-family review rounds before the flip: `.patch` is omitted on large/binary diffs; `additions: 0` is reported for binary files (a NUL in a comment makes the ledger "binary" while Python still parses a smuggled entry — verified on PR #2041); pure renames also report `additions: 0` (verified on PR #2172); the Contents API **dereferences symlinks**, so swapping the ledger for a link to identical content reads as a no-op and a later PR edits the unprotected link target freely; and a truncated/failed fetch yields a subset of base, which reads as a deletion. Now: only a regular blob (`100644`/`100755`) is trusted, decoded bytes must equal the tree's declared `size`, and the exemption's parser is pinned to the aggregator's by a parity test — 30 boundary tests |

Cross-family review: Codex, two rounds, both `adapt`, all findings addressed
(`.codex-gate-plan.txt`, `.codex-gate-confirm.txt` trails).

## Consequences

- A PR that breaks a test can no longer auto-merge to production.
- Repo test debt becomes a visible, counted, one-way-ratcheted number instead of
  an unknown.
### Why `strict: false`, and why not a fast subset (2026-08-03)

`Require branches to be up to date` (`strict`) means a PR must be current with
`main` *at merge time*. `main` takes a commit every **~10 min** (median, 39 gaps
measured) and this suite takes **~37 min**, so a PR goes stale before its own
run finishes: only **5% of gaps** are long enough to land. Keeping `strict`
would have wedged every merge, the drain included.

The obvious escape — require a fast subset instead — was built, measured, and
**rejected on evidence**. Excluding the 53 files that held 90% of the wall clock
gave a 4-minute gate, but turned **81 passing tests red** (run 30781261125)
purely by changing test *order*: this suite is not hermetic, so its results
depend on which files run. A subset baseline would shift every time anyone adds
a test file, failing PRs for unrelated reasons — the flaky-required-check trap
this ADR exists to avoid. The full run's baseline, by contrast, reproduced
identically twice (483 then 482).

So the full suite is required and `strict` is set **false**. PRs do not
serialize: each runs its own ~37 min concurrently and merges when green, so
throughput is unchanged and only per-PR latency rises. The cost is a real
regression `strict` used to prevent — a PR green against an older `main` can
merge after a compatible-looking invariant changed underneath it. That is
detected by the per-SHA `push: main` run, which now actually completes (main
runs used to share one concurrency group and cancel each other, so the
"tripwire" had never once finished).

**Unblocking a subset gate, parallelism, and `strict` all reduce to one thing:
making the suite order-independent.** Two leaks are already fixed (the
`git_bridge.is_enabled` process cache; the headless tray collection abort); the
xdist note above and these 81 failures are the same class.

- Every PR pays the serial suite: measured **~26 minutes** on 2026-08-02
  (25:48 of tests; the original ~3-minute estimate predated the suite's growth
  to ~9,100 tests and was wrong). Accepted trade: it was ~0 minutes of
  verification before, and merges were median-3.7-minute review-less lands.
  Follow-up if the latency bites: a curated fast-subset job becomes
  `required-tests` and the full serial suite stays a non-required
  post-merge/nightly tripwire — change it via the documented context-rename
  procedure, never by weakening this gate in place.
- The `known-failing-tests.txt` count is a standing cleanup backlog; each entry
  removed is a real regression the gate can newly catch.
