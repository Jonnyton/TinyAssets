# Executable gates

Which of this project's rules are enforced by something that can fail, where
that enforcement runs, and which rules are deliberately still judgement.

Written 2026-08-25 during the harness reset; authority paths added 2026-08-26. The reset's rule was **every gate
is either executable or honestly labelled as judgement** — a rule that reads
like a gate but enforces nothing is worse than no rule, because it buys
confidence it has not earned.

## Enforced

| Rule | Mechanism | Runs where |
|---|---|---|
| Always-loaded context budget | `scripts/check_context_budget.py` → `context-budget` invariant | pre-commit hook **and** `invariants.yml` CI |
| Cross-provider rule-file drift | `scripts/check_cross_provider_drift.py` → `cross-provider-drift` | same |
| Skill tree valid + mirrored | `validate_skills.py`, `mirror-parity` | same |
| Plugin mirror ships the current code | `scripts/check_mirror_parity.py` → `mirror-parity`. A canonical `tinyassets/**` file that DIVERGES from its mirror copy **or has no mirror copy at all** fails, by name. | pre-commit hook (staged set) **and** `invariants.yml` CI (whole tree) |
| No CP-1252 mojibake in tracked text | `mojibake` invariant | same |
| Behavioural test gate on `main` | `required-tests` + `.github/known-failing-tests.txt` | required check |
| Diff scope declared | `pr-scope-guard.yml` | required check |
| Exact-head review receipt on gate-defining **and authority-critical** files | `scripts/drain_review_gate.py` | `pr-scope-guard.yml`, `auto-enroll-merge.yml` |
| Public MCP surface + canonical handles | `scripts/mcp_public_canary.py --assert-handles` | `deploy-prod.yml`, and by hand after DNS/tunnel/connector edits |
| **Merged is not deployed** (Hard Rule 14) | `scripts/deployed_sha.py --assert-contains <sha>` | post-deploy, by hand or from a deploy job — **never** a merge-required check |

### Two shapes worth copying

**Three exit codes, not two.** `deployed_sha.py` returns 0 shipped, 1 not
shipped, **2 could not determine**. Collapsing 2 into 0 would make a network
blip read as "yes, it shipped" — the exact failure Hard Rule 14 exists to
prevent. Any gate that talks to an external service needs this third state.

**A gate that cannot fail is decoration.** Every gate above was mutation-tested:
break the thing it guards, confirm it goes red, restore, confirm green. Two
findings came straight out of doing that during the reset — the invariant
framework was downgrading crashed checks to `SKIPPED` (so a broken gate reported
as fine), and `tests/test_validate_skills.py` had two tests failing with
`FileNotFoundError` on `origin/main`, testing nothing. Neither was visible
without trying to make them fail.

## Cross-family review — partly enforced, and why only partly

`AGENTS.md` requires opposite-provider review before build, push, and rollout for
research-derived findings and high-risk changes. Two pieces of that are now
executable; the rest is deliberately judgement.

### What the reset did NOT build

The plan proposed a `crossfamily` gate reading a committed
`.agents/verdicts/<sha>.json`. Codex refuted it, correctly: **committing the
verdict changes the SHA it claims to approve**, and anything the author can write
from their own checkout is self-attestation, not review. That gate was not built
and should not be.

### The sound mechanism, and where it fires

`scripts/drain_review_gate.py` requires an exact-head receipt in the **PR body** —
GitHub-hosted, outside the commit, invalidated by any head change:

```
Drain-Review-Verdict: APPROVE
Drain-Review-Head: <40-char sha>
Drain-Review-Artifact: docs/... | https://github.com/...
```

It fires on three classes, all from the trusted base checkout so a PR cannot
weaken the rule judging it:

1. **`drain/` branches.**
2. **Gate-defining files** — `.github/workflows/tests.yml`,
   `known-failing-tests.txt`, `heavy-test-files.txt`, `ci_required_tests.py`,
   `drain_review_gate.py`. The "a PR can neuter its own judge" class.
3. **Authority-critical files** (added 2026-08-26) — `tinyassets/auth/`,
   `credential_vault.py`, and `api/{permissions,interlocutor,visibility,engine_helpers}.py`.

Class 3 exists because `AGENTS.md` *already* required exact-head approval for
auth and public-surface changes and nothing enforced it. Making a stated rule
executable is not new process; inventing a requirement because it feels safer
would be.

**Scoped to where the repeat actually happened.** Every file in class 3 is named
in an open finding in `docs/concerns/` — the write-ACL tier grant
(`interlocutor.py`), the ambient identity fallback (`engine_helpers.py`), founder
canon defaulting public (`visibility.py`), the credential-vault fail-open. All of
them **landed** and were found later by cross-family review. The gap was never
"no review" — it was review not bound to the merge, which is exactly what an
exact-head receipt binds.

**Deliberately narrow: ~7% of recent commits touch these paths.** A blanket
receipt requirement across `tinyassets/` would be the process bloat this reset
removed. The regex is mutation-tested: it matches all seven authority files and
rejects ordinary product work, the generated `packaging/` mirror, and lookalike
filenames such as `visibility_helpers.py`.

### Still judgement

Everything else. Whether a *design* is right, whether a finding is real, whether
a shape should ship — no path regex reaches those. Cross-family review of
judgement-class decisions stays a norm, dispatched via `peer-agents`.

## A check that gave false assurance, twice

Both times the check looked right and was too narrow. Both were caught by
something else, never by the check.

**Orphan-script detection.** `for f in scripts/*.py; grep -l "$(basename $f)"`
matches `timestamp_lint_run.py` but **not** `from scripts.timestamp_lint_run
import ...` — the module form has no extension. A script with a dedicated test
suite was deleted as unreferenced, and CI caught it as a collection error two
pushes later. When checking whether a module is used, search **both** the
filename and the dotted/slashed module path:

```bash
git grep -l "scripts\.$m\|scripts/$m\|import $m"
```

**Orphan-hook detection.** The same shape: grepping only
`.claude/settings.json` reported three hooks as wired nowhere. They were wired
through agent frontmatter. (`.claude/settings.shared.json` was deleted 2026-08-27: it
existed to work around `.claude/settings.json` being gitignored, which it never was.)

The generalisation, and the reason both are recorded here: **a "nothing
references this" check is a claim about every reference form that exists.**
Enumerate the forms before trusting the absence. An emptiness result from a
narrow search is not evidence of emptiness — the same mistake as
`Get-ChildItem -ErrorAction SilentlyContinue` returning empty on a directory it
could not read.

## Classifying local branch refs: the check that works

Measured 2026-08-26, resolved 2026-08-27. The primary checkout carried ~975
local branches. The first pass deleted 50 provably-redundant ones and concluded
the remaining 925 **could not be safely classified**, because every cheap check
lies under squash-merge:

| Check | Why it lies here |
|---|---|
| `git branch --merged main` | This repo **squash-merges**. A squash-merged branch's commits are not ancestors of `main`, so it reports "unmerged" for work that fully landed. `harness-reset` proved it: reported unmerged, content byte-identical to `main`. |
| `git diff main..branch` | Sampled 40: all differed by ~2,400 files. That is `main`'s forward progress since they branched, not their content. |
| `git cherry main branch` | Sampled 14: 5 had zero unique commits, 9 had 1–50. Squash-merging changes patch-ids, so a landed branch's commits still show as `+`. Over-reports. |

That conclusion was **too pessimistic**, and the fix was to stop asking git.

**Ask GitHub instead.** The repo has `delete_branch_on_merge: true`, so a local
branch whose upstream reads `[gone]` had its remote deleted — and intersecting
those with the head refs of *merged* PRs gives a set whose work provably landed:

```
git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads \
  | grep '\[gone\]' | awk '{print $1}' | sort -u          > gone.txt
gh pr list --state merged --limit 1000 --json headRefName \
  --jq '.[].headRefName' | sort -u                        > merged.txt
comm -12 gone.txt merged.txt                              # provably landed
```

931 local branches → 853 `[gone]` → **716 also matched a merged PR**. Excluding
branches checked out in a worktree (`harness-cut2` was in the set — a real trap)
and `main` left 715, deleted with their shas recorded first. **931 → 216.**

Both halves matter: `[gone]` alone is not proof (a remote can be deleted without
merging), and a merged PR alone is not proof the *local* ref is redundant.

**What remains, and why it stays:**

| Remaining | Count | Why |
|---|---|---|
| Gone upstream, no merged PR | 138 | Remote deleted without merging — abandoned, or unlanded. Not distinguishable cheaply. |
| Live tracking branch | 46 | Remote still exists. |
| **Never pushed** | 32 | **Highest risk.** Nothing anywhere else holds them. This is the class that held `99529969`, a droplet-diagnostics commit found on no remote during the 2026-08-26 audit. Never bulk-delete these. |

**Prevention still beats cleanup.** `delete_branch_on_merge` is already on, so
new merges self-clean; the pile was historical. Run the intersection above when
it grows again — it is cheap, and it is the only check here that does not lie.

## Branch protection: `strict` is off, deliberately

Changed 2026-08-27 after the setting deadlocked four queued PRs.

`strict` ("require branches to be up to date before merging") makes every merge
mark every other open PR `BEHIND`. **GitHub's auto-merge does not update a
behind branch** -- that is the entire selling point of merge queue, which says
it "does not require a pull request author to update their pull request branch."
So `strict` + auto-merge deadlocks at any concurrency above one: the PRs sit
enrolled, mergeable, and never merge.

**Merge queue -- the supported fix -- is unavailable here.** It requires an
ORGANIZATION-owned repository; `Jonnyton/TinyAssets` is user-owned, so no plan
unlocks it.

Two things `strict` was assumed to give, that it does not:

- *"It keeps `main` green."* It guarantees only that the PR was tested against
  `main` **as of its last update**. A merge landing between that check and the
  button reopens the window. Only a merge queue closes it.
- *"The post-merge run depends on it."* Backwards. `tests.yml` runs on
  `push: main` and that is the **substitute** for strict, not something it
  protects. Verified firing on every recent merge.

GitHub's own docs present the two modes as a tradeoff, not a recommendation --
loose means "status checks may fail after you merge," which is detectable.

**The compensator, which is the part that must not rot:** a red `main` is the
signal now. `tests.yml` on `push: main` must stay wired, and the standing
response to a red main is **revert first, diagnose after**. If PR concurrency
ever rises enough for semantic conflicts to bite, the correct move is to move
the repo to an organization and enable merge queue -- not to re-enable `strict`.

### Required checks, and why each earns it

| Check | Time | Unique value |
|---|---|---|
| `required-tests` | ~7 min | The behavioural gate. All tests minus 50 heavy files, `-m "not slow"`. |
| `slow-tests` | ~1 min | The ONLY place `-m slow` race/stress tests run -- `required-tests` explicitly deselects them. Made required 2026-08-27: it was 10/10 green and nobody read it. |
| `invariants` | ~15 s | Mechanical checks. Best signal per second here. |
| `Diff scope declared` | ~10 s | Blast-radius guard. Caught PR #1491's seven-file diff behind a "two-file auth fix". |

They run in parallel, so the wall clock is `required-tests` alone.

`heavy-tests` is NOT required and runs ONLY the files `required-tests` excludes
(it replaced `full-tests`, which re-ran the required suite as well). It is still
red, and that is tracked, not fixed.
See `docs/concerns/2026-08-27-full-tests-permanently-red.md`.

## Not gates, and should not become gates

- **Evidence-before-completion.** A script can confirm a command and its output
  are present; it cannot confirm the evidence supports the claim. Checking the
  string would create exactly the false confidence this file warns about.
- **Shape-before-hardening review sequencing.** The ordering is a judgement
  about what a change *is*. Encoding it would mean encoding "is this
  foundation or feature," which is the judgement itself.
