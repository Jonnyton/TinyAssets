# The 55 sweepable worktree lanes: 45 belong to a running job, 9 are dead

**Date:** 2026-07-22 · **Provider:** claude-code · **Lane:** `docs/worktree-lane-sweep-audit`
**Scope:** local worktree *registrations* (`git worktree list`). Audit-only — nothing was removed.
**Adjacent, non-overlapping:** PR #1521 audits *origin branches*. See "Reconciliation" below.

> **Read the freshness stamps.** Measurements are from 2026-07-21 22:30–23:05 PDT. A cross-family
> re-check at 00:05 returned **`VERDICT: reject`** because two time-sensitive claims had already
> expired — correctly. The structural findings (F1, F2, F6-structure, F7, F8) hold; the live-job
> quote in F3 and the missing-commit example in F6 are historical. See
> [Cross-family review](#cross-family-review--verdict-reject-and-it-was-right). **Do not paste the
> sweep block from this document — re-derive it.**

---

## Summary

`python scripts/worktree_status.py` — the tool `AGENTS.md` § *Provider session-start ritual* step 2
mandates for every provider, every session — reports 149 registered worktrees, of which **45 are
`ORPHANED` and 10 are `READY_TO_REMOVE`**. The tool's own prescriptions for those states are
"remove worktree" and "log remove/sweep", and `--sweep-orphaned` prints 63 ready-to-paste commands.

Running those 63 commands would be a mistake. The classification below is:

| Verdict | Count | Meaning |
|---|---|---|
| `keep` — live job | 45 | Not project lanes. Scratch worktrees of a **currently-running** job. |
| `dead` | 8 | Real project lanes, safe to remove. |
| `keep` — active | 1 | Committed *after* the census; no PR yet. |
| `has-unpushed-work` | 1 | Uncommitted tracked edits, no PR. |

**45 of the 63 emitted commands target the working directories of one live agent session.**

The premise this lane was dispatched on — "45 lanes are abandoned work whose purpose is
unrecoverable" — is **false**, but the underlying worry was pointed at something real. It was
pointed one directory too shallow. See F6.

---

## What I verified vs. what I inferred

**Verified** (command output, this session, 2026-07-21 ~22:30–23:05 PDT / 2026-07-22 05:30–06:05 UTC):

- The census, and its drift (149 → 152 lanes during the audit).
- Every one of the 45 `ORPHANED` paths is under `~/.claude/jobs/aaaa5b09/tmp/` — `python` bucket of
  `path` over the full census; the split is 45/45 clean, 0 exceptions.
- All 45 are detached HEAD, no branch, no origin branch, no PR (bulk `gh pr list --limit 2000`,
  901 PRs, no truncation).
- Every one of the 45 HEAD shas is contained in ≥19 refs (min 19, all include at least one
  `refs/remotes/origin/*`) — `git for-each-ref --contains <sha>`.
- Job `aaaa5b09` state: `{"state":"blocked"}`, 1 in-flight task, `state.json` mtime
  `2026-07-21T22:41`.
- `58430f7c` / `a727b574` are absent from this repo's object store and present in
  `.codex-worktrees/wf-credential-vault-fail-closed/`.
- `.agents/worktrees.md`: 47 `CREATE` events, 12 `REMOVE` events.
- `wf-probe-catalog-probe003-truth` committed `38ce4a2a` at `22:57`, after the census was taken.

**Inferred, not proven:**

- That the 45 job-scratch worktrees were created by the background-job harness rather than by a
  script that happened to write into that directory. The evidence is circumstantial but strong:
  one job id, no `_PURPOSE.md` on any of them, zero entries in `.agents/worktrees.md`, and a path
  root (`~/.claude/jobs/<id>/tmp/`) that is harness-owned. I did not read harness source.
- That job `aaaa5b09` will still be live when a human reads this. `blocked` means awaiting host
  input; it could be answered or abandoned at any time. **Re-check before sweeping.**
- Verdict `dead` for the 4 lanes with no PR and 0 commits ahead rests on them having produced
  nothing, not on positive evidence that their owner finished. They are safe to remove because
  there is nothing in them to lose, not because their work is known-landed.

---

## Findings

### F1 — The 45 `ORPHANED` lanes are not project lanes at all

Every one lives under `C:/Users/Jonathan/.claude/jobs/aaaa5b09/tmp/wt-*`, not the repo's
`../wf-<slug>` convention. They are registered in `git worktree list`, so `worktree_status.py`
counts them, and they legitimately satisfy the `ORPHANED` predicate
(`scripts/worktree_status.py:298`): no `_PURPOSE.md`, older than 24h, upstream `detached`.

They have no `_PURPOSE.md` because they never went through `scripts/wt.py new` — they were never
meant to be project lanes. Classifying them against the lane-discipline invariants is a category
error: `AGENTS.md`'s "a branch is not durable memory" rule is about *branches someone is working a
task on*, and these have no branch at all.

### F2 — Nothing is stranded in them

Each of the 45 HEAD shas is reachable from at least 19 refs, always including an
`refs/remotes/origin/*` ref. They are detached checkouts of the shared patch-loop stack
(fork point `b372e000`, PR #1462, 2026-07-15). Removing the worktrees would destroy no commit.

This is the one place where the sweep is *safe on data-loss grounds* — and it is still unsafe, for
the next reason.

### F3 — Job `aaaa5b09` is live, so the sweep is unsafe anyway

`~/.claude/jobs/aaaa5b09/state.json` reads `{"state": "blocked", "inFlight": {"tasks": 1}}` with
mtime `2026-07-21T22:41` — minutes before this audit. `blocked` is *awaiting host input*, not
finished. A shell fan-out (a Playwright Chrome on `--remote-debugging-port=9222`) is listed as
in-flight.

`git worktree remove` on those 45 paths deletes the working directories of a running agent.
None of them is locked (`.git/worktrees/<name>/locked` absent), so git will not refuse.

**This is the reason to not paste `--sweep-orphaned` output.** It is not a data-loss risk; it is a
concurrency risk, and the tool has no signal for it.

### F4 — "Commits ahead of main" is not evidence of stranded work

These lanes report 10–207 commits ahead of `origin/main`, and `scripts/git_squash_merge.is_merged_into`
says *not merged*. Both are true and neither means work is stranded — the commits are the shared
patch-loop stack, anchored on origin refs (F2).

`is_merged_into` is deliberately conservative ("returns False so callers refuse teardown rather than
discard unmerged work"). Read as a *liveness* signal it produces a false positive on every lane
whose branch was rebased or whose squash landed with different context. My first pass classified
45/45 as `has-unpushed-work` on exactly this mistake before the PR-state cross-check corrected it.

This is the `stale-backlog-rows-misdirect` lesson in a new costume: **classify by PR state, never by
reachability.** Reachability answers "is this sha an ancestor", which is not the question.

### F5 — Exactly two of the ten project lanes must not be swept

- `wf-persona-note-relay-reshape` — 3 modified tracked files (`tinyassets/persona.py`,
  `tests/test_persona.py`, plugin mirror), no PR. Uncommitted work on disk.
- `wf-probe-catalog-probe003-truth` — **committed `38ce4a2a` at 22:57, after my census**
  ("PROBE-003 has been red for 6 days"). Pushed to origin, so the commit is safe, but the lane is
  mid-flight with no PR yet.

The second one is the important one, because at census time it was clean with 0 commits ahead, so
it classified `READY_TO_REMOVE` → `dead`, and **my own sweep list would have included it.**

### F6 — The real blind spot: `worktree_status.py` cannot see separate clones

This is the finding worth more than the sweep.

`.codex-worktrees/` and `codex-tmp/` contain **53 checkouts invisible to the main repo**, of which
**11 have modified tracked files right now**:

- **46 separate clones** — `.git` is a directory, each with its own `origin` remote pointing back at
  `github.com/Jonnyton/TinyAssets`.
- **7 worktrees of those clones** — `.git` is a file whose `gitdir:` resolves *into another nested
  clone*, e.g. `codex-tmp/pr1487-clean-41c0e67c` → `codex-tmp/pr1487-source-41c0e67c/.git/worktrees/…`.
  A second tier of nesting, equally invisible.

`git worktree list` on the main repo reports **0** of these 53 (verified). A clone is a separate
object store, so the main repo's worktree registry cannot know about it, and the second-tier
worktrees are registered in *their parent clone's* registry, not this one. The mandated cold-start
tool is therefore structurally blind to all 53 — `worktree_status.py` contains no path-origin
awareness of any kind and no clone discovery.

That blind spot has a live cost. At the time of writing, job `aaaa5b09` is blocked asking the host:

> do you want me to redo R2-1 from scratch on a fresh branch (safest, loses whatever those two
> commits held), or first ask the other Codex session whether `58430f7c`/`a727b574` are in its
> checkout?

**Those commits are not lost.** Both are in `.codex-worktrees/wf-credential-vault-fail-closed/`, on
branch `fix/credential-vault-fail-closed`, in an actively-progressing lane (HEAD `ae4182a2`,
`2026-07-21T22:53`, dirty working tree):

```bash
git -c safe.directory='*' -C .codex-worktrees/wf-credential-vault-fail-closed \
    log --oneline -2 58430f7c
# 58430f7c fix: fail closed on universe provider credentials
# a727b574 feat: expose universe provider payer receipts   (child)
```

`58430f7c` carries the OpenSpec change `fail-closed-universe-credentials` plus
`tests/test_credential_vault_fail_closed.py`; `a727b574` adds the payer-receipt surface across
`providers/{base,call,router}.py`, `credential_vault.py`, `graph_compiler.py`, `api/{runs,universe}.py`.
That is R2-1, the row gating the next live test round — and a session was about to redo it from
scratch because the mandated discovery tool cannot see the directory it is sitting in.

So: the dispatching worry ("work is stranded where nobody can find it") was **correct**. It was
aimed at the 45 lanes, where nothing is stranded, instead of at the 53 invisible checkouts, where the
project's current gating work was about to be rebuilt from zero.

### F7 — The sanctioned reaper could never have cleaned these

`scripts/wt.py sweep` exists and is the automation layer meant to stop sprawl. Its
`_is_sweep_candidate` accepts **only** `READY_TO_REMOVE`, never `ORPHANED`. So the 45 were outside
its reach in principle, not by neglect.

Combined with the teardown ledger — **47 `CREATE` events vs 12 `REMOVE` events** in
`.agents/worktrees.md` (46 vs 12 on 2026-07-22 alone) — the picture is that lane creation is
automated and lane teardown is not. `wt.py new` is called by the fleet; `wt.py done` is called by
whoever remembers.

### F8 — The census is a moving target

During this audit the registered count went **149 → 152**, and
`wf-persona-note-relay-reshape` moved `READY_TO_REMOVE` → dirty → `PARKED_DRAFT`.
`wf-probe-catalog-probe003-truth` gained a commit (F5).

A sweep list generated at time *T* is stale within minutes on a saturated fleet. Any sweep must be
re-derived immediately before it is run, and must re-check liveness per lane rather than trusting a
list pasted from a document. This audit's command block is written accordingly.

---

## Two measurement traps (from the brief) — plus one more

1. **`--provider <x>` is a substring filter, not a label.** `worktree_status.py:592-598` matches on
   `slug`/`branch`/`path`. `--provider probe` returns 2 lanes because both contain "probe", not
   because the tool is blind to the rest. Run with **no** `--provider` for a census. *(Confirmed by
   reading the code; I did not re-run the bad invocation.)*
2. **`git worktree prune` is a different question.** Prune only removes worktrees whose *directory
   is gone* — 1 of 149 here. `ORPHANED`/`READY_TO_REMOVE` are about missing `_PURPOSE.md` and dead
   upstreams. A previous cycle correctly killed a "141 orphaned worktrees" claim using prune; that
   refutation does not apply to this finding, and this finding does not resurrect that claim.
3. **New — a lane's git state is not its liveness.** `worktree_status.py` ages lanes by *last
   commit* (`_last_commit_age_hours`). An agent that has been running for an hour without
   committing looks old and idle. Filesystem mtime and, for harness lanes, the owning job's
   `state.json` are the liveness signals, and the tool reads neither. F3 and F5 are both instances.

---

## Reconciliation with PR #1521 (`docs/dead-branch-sweep`)

Different sets. #1521 audits **origin branches**; this lane audits **local worktree registrations**.

- The 45 job-scratch lanes are detached with **no branch at all**, so they cannot appear in #1521's
  17. Overlap: **0**.
- Of the 10 project lanes, **2** branches appear in #1521's set:
  `claude/brain-scratch-root-cleanup` (its excluded "genuinely stranded" branch — since merged as
  **#1519**, so #1521's exclusion is now expired) and `fix/reconcile-against-production`
  (its Group A, merged as #1500).
- **8 of 10 are new here.**

The two audits are complementary: #1521 removes dead *remote refs*, this one removes dead *local
checkouts*. Neither subsumes the other, and neither covers the 53 unregistered checkouts in F6 — that
set is currently audited by nobody.

#1521's traps that I reused: `gh pr list` truncates at its default limit (I passed `--limit 2000`
and got 901 PRs — the default 30 would have misclassified nearly everything as "no PR"), and
`export MSYS_NO_PATHCONV=1` on Git Bash.

---

## Classified lanes

### Group A — 45 harness job-scratch worktrees (`~/.claude/jobs/aaaa5b09/tmp/`)

All detached HEAD, no branch, no origin branch, no PR, no `_PURPOSE.md`, all owned by one live job.
`refs` = number of refs containing that HEAD sha (all ≥19, all including an origin ref → nothing
stranded). Verdict is uniform: **keep while the job lives**.

| # | Worktree (basename) | Branch | Last commit | PR | refs | Verdict |
|---|---|---|---|---|---|---|
| 1 | `wt-bundle-sweep` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 2 | `wt-bundle-sweep-10` | *(detached)* | 2026-07-18 | none | 31 | keep - live job |
| 3 | `wt-bundle-sweep-2` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 4 | `wt-bundle-sweep-3` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 5 | `wt-bundle-sweep-4` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 6 | `wt-bundle-sweep-5` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 7 | `wt-bundle-sweep-6` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 8 | `wt-bundle-sweep-7` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 9 | `wt-bundle-sweep-8` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 10 | `wt-bundle-sweep-9` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 11 | `wt-core-r13-fable` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 12 | `wt-decexec-fable` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 13 | `wt-decexec-fable-2` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 14 | `wt-decexec-fable-3` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 15 | `wt-decexec-fable-4` | *(detached)* | 2026-07-18 | none | 31 | keep - live job |
| 16 | `wt-fix4-baseline` | *(detached)* | 2026-07-19 | none | 19 | keep - live job |
| 17 | `wt-merge-fable` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 18 | `wt-rev-43070ab7` | *(detached)* | 2026-07-18 | none | 31 | keep - live job |
| 19 | `wt-s1-base-r27` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 20 | `wt-s1-fable` | *(detached)* | 2026-07-15 | none | 33 | keep - live job |
| 21 | `wt-s1-fable-r27` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 22 | `wt-s1-fable-r28` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 23 | `wt-s1-review-r24` | *(detached)* | 2026-07-16 | none | 33 | keep - live job |
| 24 | `wt-s1-review-r25` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 25 | `wt-s1-review-r26` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 26 | `wt-s2-fable` | *(detached)* | 2026-07-15 | none | 33 | keep - live job |
| 27 | `wt-s2-review` | *(detached)* | 2026-07-16 | none | 33 | keep - live job |
| 28 | `wt-s2merge-fable` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 29 | `wt-s3-fable` | *(detached)* | 2026-07-15 | none | 33 | keep - live job |
| 30 | `wt-s3-review` | *(detached)* | 2026-07-16 | none | 33 | keep - live job |
| 31 | `wt-s3-review-r21` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 32 | `wt-s3merge-fable` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 33 | `wt-s4-fable` | *(detached)* | 2026-07-15 | none | 33 | keep - live job |
| 34 | `wt-s4-review` | *(detached)* | 2026-07-16 | none | 33 | keep - live job |
| 35 | `wt-s4-review-r18` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 36 | `wt-s4merge-fable` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 37 | `wt-s5-fable` | *(detached)* | 2026-07-15 | none | 33 | keep - live job |
| 38 | `wt-s5-fable-r24` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 39 | `wt-s5-review` | *(detached)* | 2026-07-16 | none | 33 | keep - live job |
| 40 | `wt-s5-review-r23` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 41 | `wt-seam-fable-r2` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 42 | `wt-seam-review` | *(detached)* | 2026-07-17 | none | 31 | keep - live job |
| 43 | `wt-vault-fable-r12` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |
| 44 | `wt-vault-review` | *(detached)* | 2026-07-16 | none | 33 | keep - live job |
| 45 | `wt-vault-review-r11` | *(detached)* | 2026-07-17 | none | 33 | keep - live job |

### Group B — 10 project lanes (`Projects/wf-*`), state `READY_TO_REMOVE`

| # | Worktree | Branch | Last commit | PR | Ahead | Verdict |
|---|---|---|---|---|---|---|
| 1 | `wf-activity-null-results` | `tmp/activity-null-results` | 2026-07-21 | none | 0 | dead |
| 2 | `wf-brain-scratch-root-cleanup` | `claude/brain-scratch-root-cleanup` | 2026-07-21 | #1519 MERGED | 3 | dead |
| 3 | `wf-persona-note-relay-reshape` | `claude/persona-note-relay-reshape` | 2026-07-21 | none | 0 | **has-unpushed-work** |
| 4 | `wf-pr1506-verdict-landedness` | `claude/pr1506-verdict-landedness` | 2026-07-21 | #1532 MERGED | 2 | dead |
| 5 | `wf-probe-catalog-probe003-truth` | `claude/probe-catalog-probe003-truth` | 2026-07-21 | none | 0 | **keep - active** |
| 6 | `wf-scope-guard` | `fix/reconcile-against-production` | 2026-07-21 | #1500 MERGED | 1 | dead |
| 7 | `wf-suite-baseline` | `audit/suite-baseline-20260722` | 2026-07-22 | none | 0 | dead |
| 8 | `wf-ui-test-deployed-build` | `claude/ui-test-deployed-build` | 2026-07-21 | #1504 MERGED | 2 | dead |
| 9 | `wf-worktree-sweep-0722` | `claude/worktree-sweep-0722` | 2026-07-22 | none | 0 | dead |
| 10 | `wf-worktree-sweep-0722b` | `claude/worktree-sweep-0722b` | 2026-07-22 | none | 0 | dead |

---

## host-action: sweep

**Do not paste this blind.** Re-derive first — the census drifts (F8) and job liveness changes (F3).

### Step 0 — preconditions (all three must hold)

```bash
cd /c/Users/Jonathan/Projects/TinyAssets

# (a) Is job aaaa5b09 still live? If state is anything but a finished/abandoned
#     state, DO NOT touch ~/.claude/jobs/aaaa5b09/tmp/* — 45 lanes belong to it.
cat ~/.claude/jobs/aaaa5b09/state.json | head -5

# (b) Re-take the census; confirm the 9 below are still READY_TO_REMOVE.
python scripts/worktree_status.py --json > /tmp/census-now.json

# (c) Per-lane liveness re-check, immediately before removing each one.
for w in wf-activity-null-results wf-brain-scratch-root-cleanup \
         wf-pr1506-verdict-landedness wf-scope-guard wf-suite-baseline \
         wf-ui-test-deployed-build wf-worktree-sweep-0722 wf-worktree-sweep-0722b; do
  P="/c/Users/Jonathan/Projects/$w"
  echo "== $w  mtime=$(stat -c %y "$P" | cut -c1-16)"
  git -C "$P" status --porcelain | head -3
  git -C "$P" log origin/main..HEAD --oneline | head -3
done
# Any output under a lane => stop and re-classify that lane.
```

### Step 1 — log the removals before making them

`AGENTS.md` requires the sweep be recorded in `.agents/worktrees.md` first. Note that file is
**modified in the primary checkout right now** — append, do not overwrite.

```bash
for w in wf-activity-null-results wf-brain-scratch-root-cleanup \
         wf-pr1506-verdict-landedness wf-scope-guard wf-suite-baseline \
         wf-ui-test-deployed-build wf-worktree-sweep-0722 wf-worktree-sweep-0722b; do
  echo "- 2026-07-22 REMOVE $w reason=swept-dead-lane audit=docs/audits/2026-07-22-worktree-lane-sweep.md" \
    >> .agents/worktrees.md
done
```

### Step 2 — remove the 8 dead lanes

Prefer `wt.py done`, which re-verifies merge status (squash-aware) and refuses an unmerged branch —
it is the sanctioned path and it re-checks rather than trusting this document:

```bash
for w in wf-activity-null-results wf-brain-scratch-root-cleanup \
         wf-pr1506-verdict-landedness wf-scope-guard wf-suite-baseline \
         wf-ui-test-deployed-build wf-worktree-sweep-0722 wf-worktree-sweep-0722b; do
  python scripts/wt.py done "$w"
done
```

`wt.py done` will refuse the 4 lanes that have no merged PR (`tmp/activity-null-results`,
`audit/suite-baseline-20260722`, `claude/worktree-sweep-0722`, `claude/worktree-sweep-0722b`) because
their branches are not merged — correctly, since they are empty rather than landed. They contain
0 commits ahead of `origin/main` and no working-tree changes, so there is nothing to lose; use
`--force` **only** after Step 0(c) shows them clean:

```bash
python scripts/wt.py done wf-activity-null-results --force
python scripts/wt.py done wf-suite-baseline        --force
python scripts/wt.py done wf-worktree-sweep-0722   --force
python scripts/wt.py done wf-worktree-sweep-0722b  --force
```

### Explicitly excluded

| Lane(s) | Why not swept |
|---|---|
| 45 × `~/.claude/jobs/aaaa5b09/tmp/wt-*` | Working directories of a **live** job (F3). Not project lanes (F1). Nothing stranded in them (F2), so there is no reason to hurry. |
| `wf-persona-note-relay-reshape` | Uncommitted tracked edits, no PR (F5). |
| `wf-probe-catalog-probe003-truth` | Committed after the census; active, no PR yet (F5). |
| 53 × `.codex-worktrees/*`, `codex-tmp/*` | 46 clones + 7 worktrees-of-clones. Not registered here — `git worktree remove` does not apply. 11 are dirty. Holds R2-1 (F6). **Needs its own audit.** |

### What `--sweep-orphaned` emits, for comparison

63 commands: 54 `git worktree remove` + 9 `git branch -D`. **45 of the 54 removes target the live
job.** The 9 `branch -D` lines are the correct core of the sweep; this audit subtracts one
(`claude/probe-catalog-probe003-truth`, now active) and keeps the other 8.

---

## The structural question: why 45 lanes reached `ORPHANED`

They did not reach it by neglect. They reached it because **the state is measured against a
convention they were never part of.**

- `ORPHANED` is defined as "no `_PURPOSE.md` + old + no upstream". That predicate encodes
  *"a project lane whose owner walked away."*
- The harness creates job-scratch worktrees under `~/.claude/jobs/<id>/tmp/`. They correctly have no
  `_PURPOSE.md`, correctly have no branch, and are correctly detached — they are ephemeral compute,
  not lanes.
- `worktree_status.py` has no notion of lane *provenance*. It reads `git worktree list` and applies
  the lane-discipline predicate to everything in it.

So the answer to "something is bypassing `wt.py done`" is: **for these 45, nothing bypassed it —
they were never `wt.py`'s to tear down.** `wt.py sweep` agrees, structurally: it only ever considers
`READY_TO_REMOVE` (F7).

The real bypasses, in order of cost:

1. **Separate clones (F6).** 53 checkouts (46 clones + 7 nested worktrees), 11 dirty, holding the current gating work — and invisible
   to the mandated tool. This is where work actually gets lost, and it is the one class with a
   demonstrated live cost (a session about to redo R2-1 from scratch).
2. **Teardown is manual (F7).** 47 `CREATE` vs 12 `REMOVE`. Creation is scripted into the fleet;
   `wt.py done` depends on an agent choosing to call it at the end of a lane, which is exactly when
   agents run out of context or get despawned.
3. **A false-positive-heavy census trains people to ignore it.** 45 of 55 flagged lanes are
   non-actionable. A cold-start tool that reports 55 things to clean, 45 of which must not be
   touched, gets skimmed.
4. **The tool has become too slow to run at session start.** `worktree_status.py` shells out
   several times per worktree (status, log, upstream, for-each-ref). At 149 lanes the first census
   in this audit completed in roughly a minute; a re-run 90 minutes later had **not finished after
   8 minutes** and had to be backgrounded, because the fleet had grown and one job's scratch
   directory now holds 1,028 entries. `AGENTS.md` mandates this at *every* session start for
   *every* provider. A mandated step that costs minutes and returns mostly non-actionable rows is
   a step that gets skipped — which is the most likely reason nobody has run this sweep, ahead of
   any of the above.

### Suggested follow-ups (not done in this lane)

- Teach `worktree_status.py` lane provenance: classify worktrees outside the repo's lane root as
  `HARNESS_SCRATCH` (informational, never swept) rather than `ORPHANED`. This alone would take the
  actionable count from 55 to 10.
- Give it a liveness signal that is not last-commit-age: directory mtime, and for
  `~/.claude/jobs/<id>/tmp/*`, the owning job's `state.json`.
- Extend it to discover unregistered clones under the repo root (F6) — the set with the real risk.
- Make `--sweep-orphaned` refuse to emit removals for lanes it has not liveness-checked, rather than
  printing a ready-to-paste block whose majority is unsafe.

---

## Cross-family review — `VERDICT: reject`, and it was right

Three dispatches. Two background `codex exec` runs (7 claims, then a narrowed 3-claim
command-driven prompt) both **timed out at 1800s** and the wrapper wrote `VERDICT: error` with
"Do NOT treat this as approve" — correct fail-closed behaviour, recorded here rather than quietly
retried. The third, an inline `mcp__codex__codex` read-only gate, returned:

> C1: Not fair on current evidence. Output 1 is `0`; output 2 says `"state": "done"`, not blocked
> or in-flight.
> C2: Adapt. Output 3 is `50`, confirming that HEAD is referenced, but the outputs do not establish
> a current concurrency risk.
> C3: Reject. Output 4 is `0`, but output 5 is `commit` in both repositories. The alleged missing
> commit and blocked live session are contradicted.
> **VERDICT: reject**

**Codex is right about the present tense, and I re-verified its outputs rather than taking either
side on faith.** Between my measurements (~22:30–23:05) and its (~00:05) the system moved:

| Claim | When measured | At re-check (00:05–00:10) |
|---|---|---|
| Job `aaaa5b09` state | `"blocked"`, mtime 22:41 | `"state": "done"`, mtime 00:05 — **but** `"tempo": "active"` with 1 task in flight, and `detail: "i compacted your context"` |
| `58430f7c` in main repo | absent | **present** — `refs/remotes/origin/fix/credential-vault-fail-closed` |
| `for-each-ref --contains` on a job HEAD | 31 refs | 50 refs |
| Nested clones in `git worktree list` | 0 | **0 — unchanged** |

So the corrections are:

- **F3 is expired, not wrong.** `blocked` was accurate at 22:41. The job has since taken another
  turn. Note it is *still not finished*: `tempo: active`, 1 task in flight. Codex read the literal
  `state` string and concluded "not live"; the adjacent fields say otherwise. The operational
  conclusion — **liveness-check before sweeping, do not trust a pasted list** — survives, and is
  now demonstrated rather than argued.
- **F6's live-cost example is resolved, and the resolution confirms the diagnosis.** `58430f7c` /
  `a727b574` are no longer missing: the lane was recovered into
  `refs/stranded/wf-credential-vault-fail-closed/*` and **PR #1549** is now open —
  *"fail closed on universe provider credentials + payer receipts (**stranded lane**, DO NOT
  MERGE)"*. Someone had to go hunting under a `refs/stranded/` namespace to retrieve it. That is
  what recovering work the mandated tool cannot see costs.
- **F6's structural claim is untouched.** `git worktree list` still reports **0** of the 53 nested
  checkouts. Codex confirmed output 4 = 0 and did not dispute the mechanism; its `reject` rests on
  the expired example, not the structure.
- **C2 stands** — Codex confirmed the refs and agreed nothing is stranded in the 45.

**The verdict is retained as `reject`, not argued down.** Every time-sensitive claim in this audit
should be read as of its stamp. This is the `stale-backlog-rows-misdirect` class turned on its
author: *a "not present" note may be correct-but-expired* — mine was, within ninety minutes.

That is also the strongest possible confirmation of **F8**: the census is a moving target. Between
census 1 and this review the lane count went 149 → 152, one lane changed state twice, another
committed, a job advanced a turn, and a stranded branch was recovered and PR'd. **The sweep block
in this document must not be pasted from this document.** Re-derive, then liveness-check, then
remove — which is what Step 0 already requires.

### Final re-census (00:15) — C1 settled on the substance

A full re-census after the review returned **165 lanes** (149 → 152 → 165 in about two hours):

```
PARKED_DRAFT 64 | ORPHANED 45 | IN_FLIGHT 22 | READY_TO_REMOVE 10 | PURPOSE_INCOMPLETE 9
NEEDS_PR_OR_STATUS 8 | NEEDS_PURPOSE 3 | IN_FLIGHT_NEEDS_PURPOSE 2 | MISSING 1 | DIRTY_CURRENT 1

job-scratch lanes still registered: 49  ->  ORPHANED 45, IN_FLIGHT 3, PARKED_DRAFT 1
```

The 45 `ORPHANED` job-scratch lanes are **still registered and still flagged**, and **3 more of
that job's worktrees are now `IN_FLIGHT`** — `IN_FLIGHT` means dirty, i.e. that job is *writing
into its scratch worktrees right now*.

Codex's C1 refutation rested on the literal `state` string reading `"done"`. On the substance —
*is this a live session whose directories a sweep would delete?* — the answer is yes, and it is now
demonstrated by dirty worktrees rather than inferred from a status field. The string was stale; the
hazard was not. Accepting the `reject` on the evidence as re-run, and keeping the operational rule:
**liveness-check each lane immediately before removing it.**
