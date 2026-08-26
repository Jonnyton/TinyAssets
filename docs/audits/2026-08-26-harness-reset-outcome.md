# Harness reset — the "after", measured

Companion to `2026-08-25-harness-reset-baseline.md`. That file existed so every
later phase would be falsifiable; this is the falsification test. Same commands,
same repo, 22 commits later.

**Base:** `origin/main` @ `8cbf9769` → branch `harness-reset`.

---

## The numbers

| Measure | Before | After | Change |
|---|---|---|---|
| Always-loaded context | **62,082 B** | **25,355 B** | −59% |
| `AGENTS.md` | 493 lines / 28,524 B | 316 / 18,926 | −36% |
| `CLAUDE.md` | 223 lines / 12,388 B | 115 / 6,429 | −48% |
| `STATUS.md` | 56 lines / 21,170 B | *deleted* | — |
| Hooks | 15 files / 1,728 lines | **5 / 501** | −71% lines |
| Orphaned hooks | 3 (miscounted; see below) | **0** | — |
| Skills | 34 / 6,348 lines | **10 / 2,200** | −65% lines |
| Agent role files | 10 | **0** | — |
| Sibling `wf-*` directories | 61 | **3** (+17 empty ACL shells) | −95% |
| Registered worktrees | 26 | 8 | −69% |
| Context budget under `--strict` | **HARD FAIL** | **exit 0** | — |
| Invariants running in CI | **none** | 5 | — |

Reproduce with the commands in the baseline's § *Reproduce*.

## What the budget number does not say

The context reduction is real but it is not the point. The mechanism is:
**the budget is now HARD, `pre_commit_scope=True`, and runs in CI.** Before, it
was a registered invariant reporting VIOLATED that nothing ran and nothing
failed on. Measurement without a pawl is not a ratchet — the 59% could drift
back in a month, and the only thing preventing that is that loosening a ceiling
is now a deliberate, reviewable edit.

## Three checks that could not go red

The most useful finding of the reset, and none of it was visible by reading:

1. **The invariant framework downgraded crashed checks to `SKIPPED`**
   (`scripts/invariants/__init__.py`). A broken gate reported as fine and
   `--check-all` still exited 0. Found by renaming a constant and watching the
   budget gate silently disarm. Exceptions now VIOLATE.
2. **`tests/test_validate_skills.py` had two tests failing with
   `FileNotFoundError` on `origin/main`** — their fixtures mutated real skills by
   name, and those skills had been deleted. Red, ignored, testing nothing.
   Rebuilt on synthetic fixtures that assert the fixture starts clean.
3. **The invariants never ran in CI at all.** Only from a git hook requiring
   manual installation. A fresh clone, a CI runner, or an agent sandbox got zero
   enforcement — the actual mechanism behind four months of drift.

Each surfaced only from deliberately trying to make a check fail. That is now
written down as a rule in `docs/reference/executable-gates.md`.

## Where the plan was wrong

Kept honest because the baseline's job was to make this checkable.

| Plan claim | Reality |
|---|---|
| "3 hooks wired nowhere" | Wired via `.claude/settings.shared.json` and agent frontmatter. The orphan check grepped one file. |
| "Nothing writes STATUS.md programmatically" | `openspec_drain_supervisor.py:410` wrote and committed it; `collector.py:558` read it at runtime. True only for `tinyassets/`. |
| "~125 worktrees to reap" | 61 directories — and 49 source files in them that git had never seen. |
| "25 skills / 4,357 lines" | 34 / 6,348. The plan measured a checkout 825 commits behind. |
| Six named security concerns | Three were stale; the real list was 10 + 2 watches, one of which was already resolved and inverted. |
| `deployed_sha` as a merge gate | Circular — a merge check cannot require prod to contain an unmerged head. |
| A `crossfamily` verdict file | Self-attestable, and committing it changes the sha it approves. Not built. |
| Supervisor churn predicate | Would have flagged this reset. Not built; kept as a test. |

Codex refuted the plan (`2026-08-25-harness-reset-codex-review.md`) with nine
material flaws. All nine were verified and all nine held. Half the value of this
reset came from that review, and the other half from mutation-testing.

## Not done, and honest about it

- **`invariants.yml` is not a required check yet.** It must run green once
  first. One `gh api` call after that.
- **17 empty directory shells** remain from the reap — every real file deleted,
  only an ACL-locked `.pytest_cache` left. Needs an elevated `takeown`; the
  one-liner is in `docs/audits/harness-reset-preserved/MANIFEST.md`.
- **The end-to-end proof is unrun.** The real test is landing one live product
  task through the reset harness and confirming the session-start context is
  under budget while the work still lands. That needs the branch merged.
- **The full local suite is not a valid oracle on this machine.** It aborts with
  `PermissionError` on sandbox-created temp ACLs — the exact case `AGENTS.md`
  § *Testing* documents. CI is the authority. Every harness-touched suite is
  green (134 tests) and 13,925 collect repo-wide with no import breakage.

## The claim, stated so it can be disproved

The harness is 59% smaller in always-loaded context, has 71% fewer hook lines,
and — for the first time — has a context ceiling that fails a build instead of
printing a warning nobody reads. Whether that makes the *work* better is not yet
measured, and this document should not be read as if it were. That evidence
comes from the next product task, not from these numbers.
