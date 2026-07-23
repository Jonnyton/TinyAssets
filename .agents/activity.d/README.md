# `.agents/activity.d/` — one file per lane

Write your activity entry as **its own file here**. Do not append to
`.agents/activity.log`.

```
.agents/activity.d/<YYYY-MM-DD>-<lane-slug>.md
```

Example: `.agents/activity.d/2026-07-22-status-janitor.md`

Easiest way, which picks the filename for you:

```bash
python scripts/activity_append.py --lane status-janitor --body "what happened"
python scripts/activity_append.py --lane status-janitor --body-file notes.md
```

## Why this exists

`.agents/activity.log` is append-only, so every lane appends to the **end of the
same file**. Two lanes that both append therefore collide on the final hunk *by
construction* — a structural conflict, not a semantic one. The two entries have
nothing to do with each other and there is nothing to reconcile.

On 2026-07-22 that single file was the **only** conflicting path in PR #1506 and
PR #1507 simultaneously. Rebasing does not converge: an earlier lane rebased
#1507 and pushed at 02:47:22Z reporting it `MERGEABLE`; #1501 merged at
02:53:43Z touching the same file and #1507 was conflicting again — a six-minute
lifetime. During the very session that landed this directory it happened *again*:
#1506 merged and instantly re-broke #1507 a second time.

Churn went from roughly monthly to twice in one hour once the agent fleet started
running, so the collision rate scales with lane count. One file per lane removes
the shared write target, so the conflict cannot form in the first place.

## Why not `merge=union`

The obvious fix is `.agents/activity.log merge=union` in `.gitattributes`, which
makes git concatenate both sides instead of conflicting. **It was tried and it
does not work on GitHub.** Two independent checks:

1. **Bare-repo check.** Git reads `.gitattributes` from the *working tree*. A
   bare, server-side merge has no working tree, so the driver is never loaded:

   ```
   $ git merge-tree --write-tree lane-b lane-a                    # in a bare clone
   CONFLICT (content): Merge conflict in .agents/activity.log
   $ git --attr-source=lane-b merge-tree --write-tree lane-b lane-a
   (no conflict)
   ```

   Union applies only when an attribute source is supplied explicitly.

2. **Live GitHub check.** A disposable PR between two branches that both carried
   the union rule, colliding on a pure append, was reported **`CONFLICTING`** by
   GitHub (PR #1525, closed). GitHub's mergeability computation does not apply
   the union driver — and mergeability is exactly the gate that blocks the PR.

A local-only `git merge` *does* honor the rule, which makes this an easy thing to
believe you have verified when you have not. Measure it bare, or on GitHub.

Union was also the wrong semantics here for a second reason: it silently keeps
both sides. `.agents/activity.log` history contains deletions and rewrites, not
only appends, so a genuine semantic conflict — two lanes editing the same entry —
would be merged into a duplicate instead of being raised. That failure is silent,
which is worse than the conflict it replaces.

## Rules

- **One file per lane per day.** Never edit another lane's file; that reintroduces
  the shared write target.
- **Filenames must be unique.** The date + lane slug does this. If a lane writes
  twice in one day, use `-2`, `-3`, … rather than appending to the earlier file.
- **`.agents/activity.log` is frozen for new entries.** Its existing content is
  the historical record and stays exactly as it is. Read it for anything before
  2026-07-22.
- **Reading the feed** means reading both: the old log, then this directory.
