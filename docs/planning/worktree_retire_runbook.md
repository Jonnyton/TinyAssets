# Worktree Retire Runbook: `claude/inspiring-newton`

**Author:** planner
**Date:** 2026-04-13
**Destructive op — requires user sign-off.**

Retires the `claude/inspiring-newton` worktree per the Phase 7
reconciliation plan. Branch stays in refs; only the worktree
directory + optional branch deletion are destructive.

## 1. Pre-flight

Run from repo root `C:\Users\Jonathan\Projects\TinyAssets`.

1. **Confirm branch tip is pushed** (or accept that it won't be —
   this is a discarded branch). `git log claude/inspiring-newton
   --oneline -1` should show `b5e75a9`. Branch has never been
   pushed to origin; its only copy is local.

2. **Capture the only assets worth keeping** — the
   Custom-GPT-driver testing approach in the worktree's
   `tinyassets/testing/gpt_builder.py` + `gpt_harness.py`. Add an
   `ideas/INBOX.md` pointer entry BEFORE removal:

   ```
   - [2026-04-13] gpt_builder.py / gpt_harness.py at
     b5e75a9:tinyassets/testing/ — Custom-GPT-driver testing harness
     from the pre-Community-Branches worktree. Revive if
     Custom-GPT testing ever earns a second look. Code addressable
     via `git show b5e75a9:tinyassets/testing/gpt_builder.py`.
   ```

3. **Confirm no uncommitted changes in the worktree.**
   `git -C .claude/worktrees/inspiring-newton status --short`
   should be empty. If not empty, STOP and investigate — there's
   unsaved work to rescue first.

4. **Confirm main is clean** (this session's landings already
   committed as `d8125b1`). `git status --short` at repo root
   should show only the planning/scratch files you know about.

## 2. Exact commands

```bash
# From repo root
git worktree remove .claude/worktrees/inspiring-newton
git worktree prune

# Optional — delete the branch ref. Hold if the user wants to keep
# it addressable by name. Branch's commit stays reachable via sha
# b5e75a9 regardless (reflog retains it).
git branch -D claude/inspiring-newton
```

`git worktree remove` refuses if the worktree has uncommitted
changes or is locked. Do NOT pass `--force` without reading the
refusal reason.

## 3. Post-flight verification

1. `git worktree list` shows only the main worktree:
   ```
   C:/Users/Jonathan/Projects/TinyAssets   d8125b1 [main]
   ```
2. `ls .claude/worktrees/` directory either empty or absent.
3. `git branch -a` no longer lists `claude/inspiring-newton` (only
   if step 2 branch -D ran).
4. Commit `b5e75a9` is still reachable: `git show b5e75a9 --stat
   | head -5` succeeds. Files in that commit remain addressable
   via `git show b5e75a9:<path>` for archival purposes.

## 4. Rollback

Worktree directory is gone — recoverable from git history only.
Commit itself is preserved:

- **Recover the branch ref** (if `branch -D` was run):
  `git branch claude/inspiring-newton b5e75a9`.
- **Recover any file from that commit:**
  `git show b5e75a9:<path> > <output>` or
  `git restore --source=b5e75a9 -- <path>`.
- **Restore the worktree directory:**
  `git worktree add .claude/worktrees/inspiring-newton
  claude/inspiring-newton` (after recovering the branch ref).

Reflog window (~90 days default) keeps `b5e75a9` reachable even
after branch deletion. If `git gc` has run and pruned it, check
packed-refs first; worst-case GitHub never saw it, so full recovery
depends on local reflog. Do not run `git gc --prune=now` during the
rescue window.
