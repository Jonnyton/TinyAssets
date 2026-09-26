# Worktree discipline

One work item = one branch = one worktree = one PR. Ownership is a branch or an
open PR, never a table.

- `python scripts/wt.py new|pr|done|list` is the loop: `new` branches off
  `origin/main` and scaffolds `_PURPOSE.md`; `pr` pushes and opens the PR with
  that file as the body (`--auto` arms squash auto-merge); `done` verifies the
  merge before cleanup; `list` derives the inventory from git.
- `_PURPOSE.md` is git-ignored on purpose. A tracked copy made every concurrent PR
  `DIRTY` the moment another landed — five times in one afternoon.
- **Never switch a dirty worktree to `main`**, and never delete a lane's work to
  tidy up: prove the path is on a remote or reachable in history first.
- Branch hygiene is automated, not remembered: `delete_branch_on_merge=true` plus
  `fetch.prune`/`rerere` via `python scripts/setup_git_hygiene.py`, and
  `scripts/branch_janitor.py` (driven daily by `.github/workflows/branch-janitor.yml`)
  which never touches `main`, open-PR branches, or commits under 7 days old.

Retired 2026-08-26: `STATUS.md` rows and `scripts/claim_check.py`. Any procedure
that needed either is gone with them — `python scripts/wt.py list` and the open
PRs are the inventory now.
