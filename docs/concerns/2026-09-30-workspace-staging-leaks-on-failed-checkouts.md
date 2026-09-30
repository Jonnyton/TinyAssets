---
severity: P1
title: Failed workspace checkouts leak their staging directory; one universe holds 2.8 GiB of it
filed: '2026-09-30'
summary: '`effectors/workspace.py` removes `<universe>/.workspace-staging/<run>/<node>-<nonce>` only on the success path, right before publish. Any checkout that raises earlier leaves the credentialed clone and bundle behind, and nothing sweeps them. Production has 334 such directories in one universe (2026-09-09 to 09-21), 2.8 GiB in total. That is 97% of that universe''s non-runtime bytes, and it blocks enforcing the 2 GiB free storage quota.'
---

# Failed workspace checkouts leak their staging directory

**Filed:** 2026-09-30. **Measured:** 2026-09-30 ~18:10Z, on the production
droplet, read-only. Command:
`python scripts/droplet.py ssh -- "docker exec -i tinyassets-daemon python -" < probe`,
which walks `/data/<uid>` with `os.scandir` and no writes.

## Evidence

| path | size | files |
|---|---|---|
| `/data/u-01kxm1vszd8hwp7em418asq8h9/.workspace-staging` | 2,800.2 MiB | 1,302 |
| of which, about 30 dirs at 90.8 MiB each (e.g. `e96573a60bfd3829`) | | 42 each |
| everything else in that universe except `.runtime` | about 98 MiB | |

There are 334 staging directories, with mtimes from 2026-09-09T07:40 to
2026-09-21T06:52.

## Cause

`_staging_root` (`effectors/workspace.py:737`) creates
`<universe>/.workspace-staging/<run>/<node>-<nonce>`. The only removal is the
checked `shutil.rmtree(staging)` just before publication
(`effectors/workspace.py`, the "staging could not be removed, so nothing was
published" block). Every earlier `_Refused` or exception path returns without
removing it, and no sweeper exists for `.workspace-staging`. Staging holds the
credentialed clone, so a leaked directory is a disk leak and possibly also
retained credential material.

## Why it matters now

`account-storage-quota` task 1.1 measured this account at 2.9 GiB, against a
2 GiB free quota. Almost all of it is this debris. Enforcing the quota before
this is fixed would refuse the founder's own writes because of platform garbage
they never created.

## Fix direction

1. Remove staging in a `finally` on every checkout/push path.
2. Add a startup and periodic sweep of `.workspace-staging` entries that no live
   run owns. This follows memory `disk-hygiene-is-automatic`: inventory first.
3. `storage_accounting` treats `.workspace-staging` as platform-transient and
   excludes it from `universe_files`, the same as `.runtime`.

Deleting the existing 334 directories on production is a destructive step, so
it waits for explicit approval (Hard Rule 13).
