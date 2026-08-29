# The tracked `_PURPOSE.md` makes every concurrent PR `DIRTY` the moment another lands

**Filed:** 2026-08-29
**Verified:** yes — five times in one afternoon: #2676 (after #2671), then #2680
and #2682 twice each (after #2677/#2678, then again after #2679/#2681/#2683
landed from another session within 25 minutes), every time with all checks
green and auto-merge armed, blocked until a human merged `main` and re-pushed.
A merge→deploy watcher timed out on #2680 for exactly this reason.
**Severity:** P2 — nothing breaks, but "auto-merge armed" silently becomes
"waiting for a person" for every PR but the first, which is the opposite of
what the worktree flow promises.

## The claim

`python scripts/wt.py new <slug>` writes `_PURPOSE.md` at the repo root and it
is **tracked**, so every worktree edits the same path with different content.
Any two open PRs conflict on it; whichever lands first turns the rest `DIRTY`
(`gh pr view N --json mergeStateStatus`), and GitHub's auto-merge never fires
on a dirty PR. The resolution is always the same and always manual: merge
`main`, keep the branch's own version, push.

## Options

1. Name the file per branch (`.worktrees/<slug>.md`, or `_PURPOSE.<slug>.md`)
   so concurrent lanes never touch the same path; `wt.py` and the readers of
   `_PURPOSE.md` (grep them) move together.
2. Untrack it: `.gitignore` `_PURPOSE.md`, keep it as a local worktree note.
   Loses the "why does this branch exist" record from the PR diff — unless
   the PR body carries it, which it already does.
3. A merge driver (`.gitattributes` `_PURPOSE.md merge=ours`) — keeps the
   file tracked and picks the branch's version automatically, but GitHub's
   server-side merge does not run custom drivers, so it would not unblock
   auto-merge.

Option 1 keeps the record and removes the conflict; it is the one to build.

**Interim workaround (used on #2680 and #2682, 2026-08-29):** carry `main`'s
`_PURPOSE.md` in the branch (`git show origin/main:_PURPOSE.md > _PURPOSE.md`,
commit) so the PR has no diff on the file and nothing landing can conflict it;
the purpose goes in the PR body, and the branch's own version stays in its
history.

## How to resolve this file

Delete it when two PRs opened from different worktrees can land back to back
with auto-merge armed and neither goes `DIRTY` on the purpose file.
