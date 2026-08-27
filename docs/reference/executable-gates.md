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
through `.claude/settings.shared.json` and agent frontmatter.

The generalisation, and the reason both are recorded here: **a "nothing
references this" check is a claim about every reference form that exists.**
Enumerate the forms before trusting the absence. An emptiness result from a
narrow search is not evidence of emptiness — the same mistake as
`Get-ChildItem -ErrorAction SilentlyContinue` returning empty on a directory it
could not read.

## Why 925 local branch refs are not being bulk-deleted

Measured 2026-08-26. The primary checkout carries ~975 local branches; 50 were
provably redundant (on the remote, or merged into `main`) and were deleted. The
remaining **925 cannot be safely classified**, and the reason is worth writing
down because the obvious checks all lie:

| Check | Why it lies here |
|---|---|
| `git branch --merged main` | This repo **squash-merges**. A squash-merged branch's commits are not ancestors of `main`, so it reports "unmerged" for work that fully landed. `harness-reset` proved this: reported unmerged, content byte-identical to `main`. |
| `git diff main..branch` | Sampled 40: all differed by ~2,400 files. That is `main`'s forward progress since they branched, not their content. |
| `git cherry main branch` | Sampled 14: 5 had zero unique commits, 9 had 1–50. But squash-merging changes patch-ids, so a landed branch's commits still show as `+`. Over-reports. |

With squash-merge, no cheap check answers "does this branch hold unlanded
work?" — it needs per-branch comparison against `main` as it stood when that
branch diverged.

**So the branches stay.** They are inert: a ref is a 41-byte file, they are not
worktrees, and they cost nothing but noisy `git branch` output. Deleting 925 of
them to tidy a listing risks unlanded work that nobody has inventoried, and
Hard Rule 13 exists for exactly that trade.

**Prevention beats cleanup.** Merge with `gh pr merge --delete-branch` and the
ref goes with the PR. The accumulation is the bug; the pile is only its symptom.

## Not gates, and should not become gates

- **Evidence-before-completion.** A script can confirm a command and its output
  are present; it cannot confirm the evidence supports the claim. Checking the
  string would create exactly the false confidence this file warns about.
- **Shape-before-hardening review sequencing.** The ordering is a judgement
  about what a change *is*. Encoding it would mean encoding "is this
  foundation or feature," which is the judgement itself.
