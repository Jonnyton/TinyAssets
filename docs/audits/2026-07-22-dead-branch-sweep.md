# Dead-branch sweep: 16 of 17 "unmerged" origin branches are already dead

**Date:** 2026-07-22
**Provider:** claude-code (independent re-derivation)
**Scope:** every branch on `origin` with no open PR
**Outcome:** 16 dead, 1 genuinely stranded. **No branch was deleted by this audit** — deletion is
proposed as a host-action list in the PR body.

---

## Why this audit exists

`git rev-list --count origin/main..origin/<b>` reports a non-zero count for 17 branches that have no
open PR. Read naively that says *17 pieces of stranded work*. It does not. **16 of the 17 are dead** —
their content is already on `main`, or already contained in another live branch.

Two independent lanes have now been misled by this signal, and it is the same defect that put five
wrong rows into PR #1510's audit. This document records the root cause and a cheap classifier so the
next sweep costs minutes instead of an afternoon.

### Root cause: squash merge makes merged branches look unmerged forever

This repo merges via **squash**. A squash merge writes a *new* commit onto `main` carrying the
branch's content; the branch's own commits never become ancestors of `main`. Therefore
`git rev-list --count origin/main..origin/<b>` stays **permanently non-zero** for a fully merged
branch, and every ancestry-based "is it merged?" test — including `git branch -r --merged` — reports
*not merged*.

Evidence that the strategy is squash: `origin/fix/declare-typing-extensions` is 2 commits "ahead" of
`main`, yet its entire content (`typing-extensions>=4.0`) is present at `pyproject.toml:46` on `main`,
landed as a single squash commit under PR #1488.

**The corollary that matters:** ahead-count is a measure of *ancestry*, not of *content*. To decide
whether work is lost you must test content, not ancestry.

---

## Method (reproducible)

```bash
export MSYS_NO_PATHCONV=1     # REQUIRED on Windows/Git Bash: without it,
                              # `git show origin/main:path` can silently return empty
cd /c/Users/Jonathan/Projects/TinyAssets
git fetch --prune origin
```

**Step 1 — authoritative branch inventory.** Use `ls-remote`, not `git branch -r`:

```bash
git ls-remote --heads origin | sed 's#.*refs/heads/##' | sort > /tmp/live_origin.txt
wc -l < /tmp/live_origin.txt          # 64
```

> `git branch -r` reported **108** here. The extra 44 are leftover local ref namespaces
> (`pr/*` ×33, `pull/*` ×9, `review/*` ×1, plus `origin/HEAD`) that belong to **no configured
> remote** — `git remote -v` lists only `origin`. They are local cruft and are **not** origin
> branches. `--prune` does not remove them because they are outside the `origin` fetch refspec
> (`+refs/heads/*:refs/remotes/origin/*`). A sweep that counts `git branch -r` will over-report by
> ~70%.

**Step 2 — subtract branches with an open PR.**

```bash
gh pr list --state open --limit 1000 --json headRefName,number \
  --jq '.[] | "\(.headRefName)\t\(.number)"' | sort > /tmp/open_prs.txt
cut -f1 /tmp/open_prs.txt | sort -u > /tmp/open_heads.txt
comm -23 /tmp/live_origin.txt /tmp/open_heads.txt > /tmp/no_open_pr.txt
```

64 heads − 46 with an open PR = **18**, which includes `main` ⇒ **17 candidates**. All 17 are ahead of
`origin/main` (ahead-counts range 1 → 207).

**Step 3 — the classifier.** A branch is DEAD if either test passes:

```bash
gh pr list --state merged --limit 1000 --json headRefName,number \
  --jq '.[] | "\(.headRefName)\t\(.number)"' > /tmp/merged_prs.txt

# TEST A — squash-merged: the branch name appears as the head ref of a merged PR
awk -F'\t' -v b="$b" '$1==b {print "MERGED as #" $2}' /tmp/merged_prs.txt

# TEST B — contained: every commit is already reachable from another branch
git rev-list --count origin/<containing-branch>..origin/$b   # 0 == fully contained
```

> Use `--limit 1000`, not the default. At `--limit 300` the merged-PR list truncates at 300 of 481
> and older branches silently fall through to "no merged PR" — i.e. get misclassified as *stranded*,
> the exact error this audit exists to prevent.

**Step 4 — content verification (the part that actually justifies deletion).** A merged-PR number is
weaker evidence than the content being present. For each branch, compare every file it touched
against `main`:

```bash
mb=$(git merge-base origin/main origin/$b)
for f in $(git diff --name-only "$mb" origin/$b); do
  git cat-file -e "origin/main:$f" 2>/dev/null \
    && [ "$(git rev-parse origin/main:$f)" = "$(git rev-parse origin/$b:$f)" ] \
    && echo "IDENTICAL $f" || echo "CHECK $f"
done
```

---

## Category 1 — squash-merged (12 branches, DEAD)

`files` = files the branch touched vs its merge-base; `identical` = of those, how many are
byte-identical on `origin/main` today.

| Branch | Merged as | Tip | files | identical |
|---|---|---|---|---|
| `fix/l4-reducer-law` | #1480 | `f2d6f9e5` | 3 | 3/3 |
| `fix/card-matcher-fallback` | #1483 | `b49668b2` | 2 | 2/2 |
| `feat/per-job-sandbox-runner` | #1485 | `b4b310e6` | 3 | 3/3 |
| `feat/phase6-workflow-db` | #1486 | `dac43fc0` | 5 | 5/5 |
| `fix/declare-typing-extensions` | #1488 | `85776b65` | 1 | 1/1 |
| `feat/agent-village-command-center` | #1489 | `d4ae367e` | 17 | 17/17 |
| `chore/recover-untracked-docs` | #1490 | `88374f01` | 166 | 166/166 |
| `ci/post-merge-release-trigger` | #1497 | `e10b3380` | 1 | 0/1 † |
| `docs/openspec-and-fleet-to-main` | #1498 | `7abd0b13` | 24 | 24/24 |
| `ci/release-reconcile` | #1499 | `a6b4551c` | 1 | 0/1 † |
| `fix/reconcile-against-production` | #1500 | `e2aac805` | 3 | 2/3 † |
| `claude/release-chain-log` | #1501 | `23024f09` | 2 | 2/2 |

† Three rows do not show a clean 1:1 content match. **All three are explained by a deliberate
supersession chain, verified against `main`'s history — not by lost work.** See below.

### The three anomalies are supersession, not data loss

All four workflow files involved live in `.github/workflows/`.

```bash
git log --oneline --diff-filter=AD --format='%h %ad %s' --date=short \
  origin/main -- .github/workflows/post-merge-release.yml
# 32241353 2026-07-21 fix(ci): the safety net was asking a question it could answer wrongly (#1500)
# 9e86425d 2026-07-21 ci: merged and live were two different things (#1497)
```

- **`ci/post-merge-release-trigger` (#1497)** added `post-merge-release.yml`. That file **did** land on
  `main` (`9e86425d`) and was then **deleted** by #1500 (`32241353`). Its absence from `main` today is
  the intended end state, not a failed merge.
- **`ci/release-reconcile` (#1499)** added `release-reconcile.yml` (landed `1437b30a`). It differs from
  `main` only because #1500 subsequently modified it. Confirmed by blob identity — `main`'s copy is
  byte-identical to the *later* branch, not the earlier one:

  ```
  main                              f29d9dc302f8e23b46debe47aa87d0110d2df155
  ci/release-reconcile       (#1499) a4d308154a74f6e872495228225913c6fe2f7a5b
  fix/reconcile-against-prod (#1500) f29d9dc302f8e23b46debe47aa87d0110d2df155   ← main matches this
  ```

- **`fix/reconcile-against-production` (#1500)** is a clean landing once read correctly: its *deletion*
  of `post-merge-release.yml` is reflected on `main` (file absent ✓) and both files it *modified*
  (`pr-scope-guard.yml`, `release-reconcile.yml`) are byte-identical on `main` ✓. The "2/3" is an
  artifact of counting a deleted file as a miss.

**Generalizable lesson:** a naive content check miscounts *intentional deletions* and *subsequent
edits* as missing content. Before calling a branch stranded on a content mismatch, check whether a
**later** merged PR touched the same file.

### Guard: was any branch reused after it merged?

"Merged as #X" is not sufficient on its own — a branch can be squash-merged and then have *new*
commits pushed to it, which would be real stranded work hiding behind a merged-PR number. Checked
for all 12; all clean.

```bash
pr=<merged PR number>
ma=$(gh pr view "$pr" --json mergedAt --jq '.mergedAt')
lc=$(TZ=UTC git log -1 --date=format-local:'%Y-%m-%dT%H:%M:%SZ' --format='%cd' origin/$b)
[ "$lc" \> "$ma" ] && echo "REUSED-AFTER-MERGE" || echo clean
```

Every branch's last commit predates its merge by 12 s – 8 min. **Normalize to UTC first** — `gh`
returns UTC (`Z`) while `git log %cI` returns local (`-0700` here); comparing them raw is a 7-hour
error that can flip the result either way.

*(The content comparison in Step 4 independently covers this case — post-merge commits would surface
as a file differing from `main` — but this check names the failure mode directly.)*

---

## Category 2 — contained in the #1477 stack base (4 branches, DEAD — with a caveat)

Every commit on these four is already reachable from `origin/feat/patch-loop-leasestore-fix2`
(tip `4e0a22e2`). Verified two independent ways:

```bash
for b in feat/patch-loop-blobresult feat/patch-loop-capsule \
         feat/patch-loop-device-auth feat/patch-loop-leasestore; do
  echo "$b -> $(git rev-list --count origin/feat/patch-loop-leasestore-fix2..origin/$b)"
  # second, independent method: is the branch tip an ancestor of the base?
  git merge-base --is-ancestor origin/$b origin/feat/patch-loop-leasestore-fix2 && echo "  ANCESTOR-OK"
done
```

| Branch | Tip | `base..branch` | tip is ancestor of base | PR ever opened |
|---|---|---|---|---|
| `feat/patch-loop-blobresult` | `4db75ccd` | 0 | yes | none |
| `feat/patch-loop-capsule` | `609ad42c` | 0 | yes | none |
| `feat/patch-loop-device-auth` | `3a30c14c` | 0 | yes | none |
| `feat/patch-loop-leasestore` | `5a307576` | 0 | yes | none |

### ⚠ Caveat: the containing branch is NOT merged

`feat/patch-loop-leasestore-fix2` is the head of **PR #1477, which is OPEN** — *"S2 distributed
execution: unified authority derivation + runnable B2 spine (V1.1–V1.3)"*. None of these commits are
on `main`.

So these four are dead in a **weaker sense** than the twelve above. The twelve are safe unconditionally
— their content is on `main`. These four are safe **only for as long as `feat/patch-loop-leasestore-fix2`
survives**. If #1477 were closed unmerged *and* its branch deleted, the commits would become
unreachable from any ref.

**Recommendation:** sequence these four **after** #1477 lands, or accept the (small) dependency
explicitly. They are listed separately in the prune list for exactly this reason.

---

## Category 3 — genuinely stranded (1 branch, DO NOT DELETE)

**`claude/brain-scratch-root-cleanup`** — tip `9ede5299`, **2 commits**, no PR has *ever* been opened
for it (checked against all 877 PRs, every state).

```bash
tip=$(git rev-parse origin/claude/brain-scratch-root-cleanup)
git branch -r --contains "$tip" --format='%(refname:short)' | grep '^origin/'
# origin/claude/brain-scratch-root-cleanup      <- only itself
```

```
9ede5299 2026-07-21 chore(docs): drop the .gitignore hunk — PR #1517 owns that file
e9b5a86e 2026-07-21 chore(docs): move seven root brain scratch dumps into a dated audits folder
```

Neither commit is an ancestor of `main` (`git merge-base --is-ancestor` fails for both). **Deleting
this branch destroys the only copy of this work.** A separate lane
(`open-pr-for-brain-scratch-root-cleanup`) is opening its PR.

### It is actively moving — do not sweep it

This branch received a **new push during this audit**, between two reads minutes apart:

```bash
git reflog show origin/claude/brain-scratch-root-cleanup --date=iso
# 9ede5299 ...@{2026-07-21 20:33:51 -0700}: update by push
# e9b5a86e ...@{2026-07-21 20:09:16 -0700}: update by push
```

An earlier ahead-count in this same session read **1**; the later read was **2**. A concurrent lane is
working it right now. Any sweep must treat a live-moving branch as off-limits regardless of its
classification.

---

## Summary

| Category | Count | Safe to delete | Basis |
|---|---|---|---|
| Squash-merged | 12 | yes, unconditionally | content verified present on `origin/main` |
| Contained in #1477 stack base | 4 | yes, **while #1477's branch exists** | commits reachable from `feat/patch-loop-leasestore-fix2` |
| Genuinely stranded | 1 | **NO** | unique commits, reachable from no other ref, actively moving |
| **Total candidates** | **17** | 16 proposed | — |

The 46 branches with an open PR are **out of scope** and excluded from every list here.

---

## Prevention

1. **Never use ancestry to decide whether a branch is merged in a squash-merge repo.**
   `git branch -r --merged` and `origin/main..origin/<b>` are both wrong by construction here.
2. **Use `git ls-remote --heads origin`** for branch inventory, never `git branch -r` (44 phantom refs
   here from unconfigured `pr/`, `pull/`, `review/` namespaces).
3. **Pass `--limit 1000` to `gh pr list`.** The default silently truncates and turns merged branches
   into false "stranded" reports.
4. **Verify content, not PR numbers**, before proposing deletion — and when content appears missing,
   check for a *later* merged PR that deleted or rewrote the file before concluding work was lost.
5. **Check for post-merge reuse.** A merged branch can still carry new commits pushed after the
   merge. Compare last-commit time to `mergedAt` — in UTC, since `gh` and `git log %cI` disagree on
   timezone by default.
6. **Re-check ahead-counts immediately before acting.** Branches move mid-sweep.
7. **`export MSYS_NO_PATHCONV=1`** on Windows/Git Bash, or `git show origin/main:path` can silently
   return empty and fake a "content missing" result.
