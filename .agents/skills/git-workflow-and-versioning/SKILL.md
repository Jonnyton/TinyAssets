---
name: git-workflow-and-versioning
description: Structures git workflow — commits, branches, worktrees, and branch completion. Use when making any code change, committing, branching, setting up an isolated workspace, or deciding how to merge/PR/clean up finished work.
---

# Git Workflow and Versioning

## Overview

Git is your safety net: commits are save points, branches are sandboxes, history
is documentation. With agents generating code fast, disciplined version control
keeps changes reviewable and reversible.

## Commit discipline

- **Trunk-based default.** Keep `main` always deployable; short-lived feature
  branches merge within 1–3 days. Long-lived branches accumulate merge risk;
  prefer feature flags over weeks-long branches.
- **Commit early and often, atomically.** Each successful increment is its own
  commit doing one logical thing. Work pattern: implement slice → test → verify →
  commit → next. Never accumulate giant uncommitted changes.
- **Descriptive messages explain *why*.** `<type>: <short description>` then an
  optional body. Types: feat, fix, refactor, test, docs, chore. Not "update
  auth.ts".
- **Keep concerns separate.** Don't mix formatting with behavior, or refactor
  with feature — separate commits, ideally separate PRs.
- **Size changes** ~100 lines (good) / ~300 (ok if one logical change) / ~1000
  (split — see `code-review-and-quality`).
- **Change summaries** after modifications: CHANGES MADE / THINGS I DIDN'T TOUCH
  (intentionally) / POTENTIAL CONCERNS. The "didn't touch" section proves scope
  discipline.
- **Pre-commit hygiene:** `git diff --staged` (scan for secrets:
  password/secret/api_key/token), run tests, lint, typecheck. Automate via hooks.
- **`.gitignore`** covers `node_modules/`, `dist/`, `.env*`, `*.pem`. Never commit
  build output, env files, or secrets.
- **Branch naming:** `feature/…`, `fix/…`, `chore/…`, `refactor/…`. Delete
  branches after merge.
- **Git for debugging:** `git bisect` to find the introducing commit; `git blame`,
  `git log --grep`.

## Creating an isolated worktree

Before feature work that needs isolation: **detect existing isolation first, then
prefer native tools, then fall back to git. Never fight the harness.**

1. **Detect (Step 0).** Compare `git rev-parse --git-dir` vs `--git-common-dir`;
   if they differ (and `git rev-parse --show-superproject-working-tree` is
   empty, ruling out a submodule), you're already in a linked worktree — skip
   creation. Otherwise it's a normal checkout; get consent before creating one.
2. **Create.** Use a native worktree tool/command/flag if the harness provides
   one (it manages placement, branch, cleanup). Only if none exists, fall back to
   `git worktree add "$LOC/$BRANCH" -b "$BRANCH"`, choosing the directory by
   priority: explicit user preference > existing `.worktrees/` (wins) or
   `worktrees/` > default `.worktrees/`. **Verify the dir is git-ignored**
   (`git check-ignore`) before creating; add to `.gitignore` + commit if not. On
   a sandbox permission error, work in place and say so.
3. **Set up + baseline.** Auto-detect and run setup (npm install / cargo build /
   pip install / go mod download), then run the test suite to confirm a clean
   baseline. Tests fail → report and ask before proceeding.

### TinyAssets Project Worktree Discipline

Canonical full procedure: `docs/reference/worktree-discipline.md` (`AGENTS.md`
keeps the inline invariants + a pointer). This section is the on-demand summary.

For this repo, conform to GitHub's branch/PR model:

- One buildable work item maps to one Git branch, one local `../wf-<slug>`
  worktree, and one PR or draft PR when pushed.
- `STATUS.md` is the claim and collision surface. GitHub is the durable
  branch, commit, review, and merge surface.
- Branches are not memory. A branch remembers commits, not why the lane
  exists, whether it is live-safe, what blocks it, what ideas are parked in it,
  who owns it, or whether it should merge, split, be abandoned, or become a
  PR. `_PURPOSE.md`, `.agents/worktrees.md`, `STATUS.md`, idea files, and
  draft PR bodies are the memory layer.
- Every branch/worktree is one of four states:
  - Active lane: actionable now; has a `STATUS.md` row with exact Files /
    Depends / Status, a branch, local worktree path, and `_PURPOSE.md`.
  - Parked draft lane: pushed branch + draft PR; PR body or `_PURPOSE.md`
    records ship/abandon condition, blockers, review gates, memory refs,
    related implications, and pickup hints.
  - Idea/reference only: captured in `ideas/INBOX.md`, `ideas/PIPELINE.md`, or
    bottom "Idea feed refs"; not build authority until promoted into
    `STATUS.md` and checked against `PLAN.md`.
  - Abandoned/swept: worktree removed or logged abandoned in
    `.agents/worktrees.md`; useful ideas extracted first.
- Every new worktree gets `_PURPOSE.md` at its root. See
  `docs/reference/worktree-discipline.md` for the canonical 12-field template.
- Append create/remove/sweep events to `.agents/worktrees.md`.
- Run `python scripts/worktree_status.py` at session start to see active lanes,
  parked drafts, dirty current checkouts, missing/incomplete `_PURPOSE.md`,
  orphaned/missing paths, and PR/STATUS promotion gaps.
- Run `python scripts/provider_context_feed.py --provider <provider> --phase <claim|plan|build|review|foldback|memory-write>`
  at every lifecycle checkpoint where work narrows or advances. This catches
  Claude/Codex/Cursor/shared memories, loose ideas, research artifacts,
  provider automation notes, and worktree handoffs that should feed the lane.
  Phase filters are coarse triage; use `--limit 10` for compact hook-like
  output and a larger limit when auditing whether a category is absent.
- When taking over work, read memory refs from `_PURPOSE.md`,
  `.agents/worktrees.md`, the STATUS row, and the PR body before coding. If
  none are listed, search `.claude/agent-memory/`, `.agents/activity.log`,
  recent audit artifacts, and branch/PR notes by task slug.
- Cross-consider related implications at planning, build, review, and
  fold-back. Relevant `PLAN.md` modules are the project/module understanding
  and must be reviewed for the lane. Related `STATUS.md` lanes,
  `ideas/PIPELINE.md` rows, research artifacts, design notes, or memory refs
  stay live context until the PR folds back or the lane is explicitly
  rejected/deferred. `ideas/INBOX.md` captures are only idea-feed reminders;
  carry them at the bottom of the lane when useful, but do not treat them as
  design truth or build authorization.
- Review-blocked ideas still get a branch/worktree lane. Keep the row
  `pending` with Depends naming the review artifact/verdict; do not advance
  runtime implementation, push, live rollout, or acceptance-test claims until
  review returns `approve` or `adapt`.
- Branch-selector safety: a non-main branch is isolated from live deploy until
  merged to `main`; merging to `main` affects the live MCP/backend deploy
  chain and requires the right gates. Do not switch a dirty checkout to `main`.
  Start a clean session/worktree from `main` for new live-ready work. Leaving a
  branch parked is safe only when it has durable lane metadata.

Legacy planning docs (`ideas/PIPELINE.md`, `docs/vetted-specs.md`,
`docs/exec-plans/active/*`, old audits, and agent memories) are context, not
build queues. Before building from them, refactor the item into current
project state: re-check relevant `PLAN.md` modules, `STATUS.md`,
`ideas/PIPELINE.md`, recent commits, active review gates, prior-provider
memories, related implication lanes, and the provider-context feed for the
current phase; then add/update a STATUS row with exact Files, Depends, branch,
worktree, PR expectation, PLAN module refs, memory refs, and related
implication refs. If there are relevant `ideas/INBOX.md` captures, park them
at the bottom of the lane as Idea feed refs.


## The Save Point Pattern

After each change: test passes → commit → continue; test fails → revert to last
commit → investigate. You never lose more than one increment; `git reset --hard
HEAD` returns to the last good state if an agent goes off the rails.

## Finishing a branch

When implementation is complete: **verify tests → detect environment → present
options → execute → clean up.**

1. **Verify tests pass first.** Failing? Stop — fix before merge/PR.
2. **Detect environment** (git-dir vs git-common-dir) and **base branch**
   (`git merge-base`).
3. **Present exactly these options** (3 for a detached HEAD — no local merge):
   1) merge back to base locally, 2) push and open a PR, 3) keep as-is, 4)
   discard. No extra explanation.
4. **Execute:**
   - *Merge:* `cd` to main repo root, checkout base, pull, merge, re-run tests on
     the result; only then clean up worktree and `git branch -d`.
   - *PR:* `git push -u origin <branch>` — do NOT remove the worktree (needed for
     PR iteration).
   - *Keep:* preserve branch and worktree.
   - *Discard:* require a typed "discard" confirmation, then clean up and
     `git branch -D`.
5. **Cleanup (options 1 & 4 only).** Only remove worktrees you created (under
   `.worktrees/`/`worktrees/`); `cd` to main root first, `git worktree remove`
   then `git worktree prune`. Harness-owned workspaces: leave in place / use the
   platform's exit tool. Never delete the branch before removing its worktree.

## Red Flags

Large uncommitted changes piling up · messages like "fix"/"update"/"misc" ·
formatting mixed with behavior · committing `node_modules`/`.env`/build artifacts
· long-lived diverging branches · force-pushing shared branches · creating a
worktree when already isolated · using `git worktree add` when a native tool
exists · merging/finishing with failing tests · discarding work without
confirmation.

## Verification

- [ ] Each commit does one logical thing; message explains the why
- [ ] Tests pass before committing; no secrets in the diff
- [ ] No formatting-only changes mixed with behavior
- [ ] New worktrees are git-ignored and start from a clean test baseline
- [ ] Branch completion verified tests before merge/PR; cleanup only for worktrees you created
