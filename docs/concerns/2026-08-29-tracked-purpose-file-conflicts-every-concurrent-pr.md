# The tracked `_PURPOSE.md` makes every concurrent PR `DIRTY` the moment another lands

**Filed:** 2026-08-29. **Researched:** 2026-08-29 (founder asked for the better approach).
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

## Measured (2026-08-29, `git log origin/main`, this checkout's rerere cache)

| File | Changed by PRs on `main`, last 30 days | Recorded conflict resolutions (`.git/rr-cache`) | Read by any script? |
|---|---|---|---|
| `_PURPOSE.md` | 36 (all 6 of today's landings) | 40 | No — only `wt.py new` writes it; `wt.py done` ignores it |
| `.agents/worktrees.md` | 82 | ~227 | No — `wt.py list` computes the live inventory from git (`worktree_status.py`) |

`main`'s branch protection is `strict: false` (no "up to date" requirement),
so once a PR is mergeable, auto-merge fires. These two files are the only
thing standing between "checks green" and "merged".

Both are the STATUS.md failure mode again (retired 2026-08-25 for the same
reason): one tracked file that every lane must edit is a serialization point
across lanes. AGENTS.md already assigns "who is working on what" to *git
branches and open PRs* — `.agents/worktrees.md` duplicates that by hand.

## Options, with what rules each out

1. **`.gitattributes` merge driver (`merge=union` / `merge=ours`).** Dead on
   arrival: GitHub performs its own server-side merge and ignores user merge
   drivers; kubernetes removed its union driver for exactly this reason
   (kubernetes/kubernetes#70576; github/community discussion #9288). Would
   only help local merges, which are not where the block happens.
2. **Merge queue / "update branch".** A merge queue evicts a conflicting PR;
   GitHub's update-branch is a button, not automation. Neither removes the
   conflict, they just move where a human clicks.
3. **Per-lane tracked path** (`.agents/lanes/<slug>.md`). Removes the
   conflict (no two lanes share a path) and keeps the purpose in the PR diff.
   Cost: one file per landed lane accumulates on `main` (~36/month) unless a
   janitor prunes files whose branch is gone — a second mechanism to keep
   honest, and the closed-branch index already curates history by hand.
4. **Local-only purpose, PR body as its published form.** `_PURPOSE.md` stays
   exactly where the convention puts it (the lane root, readable by any agent
   or the cross-family reviewer running in that worktree) but is **ignored**
   (`.gitignore`), and `wt.py` grows a `pr` helper that opens the PR with the
   purpose as the body (`gh pr create --body-file _PURPOSE.md`), so the
   durable, shared record is the PR — which outlives the worktree anyway and
   is what `wt.py done` already keys on. Zero conflicts, zero accumulation,
   nothing new to prune. Cost: one modify/delete conflict for lanes already
   open when the tracked copy is removed from `main`, then never again.

**Recommendation: option 4**, and retire `.agents/worktrees.md` as a tracked
file at the same time (it is derivable: `python scripts/wt.py list`, plus
`gh pr list`). If the founder wants purposes visible on `main` after landing,
option 3 is the fallback, with a prune step in `wt.py sweep`.

### The change, when approved

- `.gitignore`: `_PURPOSE.md`; `git rm --cached _PURPOSE.md` on the landing PR.
- `scripts/wt.py`: `new` unchanged (still scaffolds the file); add `pr`
  (`gh pr create --base main --head <branch> --body-file _PURPOSE.md`, title
  from the first `Purpose:` line unless given) so the purpose is published
  the moment the lane goes public; `done` unchanged.
- `docs/reference/worktree-discipline.md`: the durable memory layer is the
  **PR body**; `_PURPOSE.md` is its local draft. Drop the `.agents/worktrees.md`
  step; drop `STATUS.md` mentions still there from before the retirement.
- `.agents/worktrees.md`: `git rm`; `wt.py list` is the inventory.
- Open lanes from the other session hit one modify/delete conflict on the
  file (resolve: `git rm _PURPOSE.md` in the branch, purpose into the PR
  body) — say so in the PR that lands this.

**Interim workaround (used on #2680 and #2682, 2026-08-29):** carry `main`'s
`_PURPOSE.md` in the branch (`git show origin/main:_PURPOSE.md > _PURPOSE.md`,
commit) so the PR has no diff on the file and nothing landing can conflict it;
the purpose goes in the PR body, and the branch's own version stays in its
history.

## How to resolve this file

Delete it when two PRs opened from different worktrees can land back to back
with auto-merge armed and neither goes `DIRTY` on a purpose or inventory file.
