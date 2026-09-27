# Dev-box disk hygiene (automatic)

The dev box hit **0 bytes free** on 2026-09-26 and broke every lane; none of it was
project data. Founder directive: *disk cleaning is part of the architecture, not a
question.* `scripts/dev_hygiene.py` is that part; why each rule exists is in its
docstrings. This is the operator's page.

## Runs by itself

| Mechanism | Does | Cost |
|---|---|---|
| `.claude/hooks/dev_hygiene_hook.py` (SessionStart) | `--apply` on the two cheap classes; injects an escalation under the floor | ~4 s |
| `scripts/install_dev_hygiene_task.ps1` | registers `TinyAssets-DevHygiene`, hourly, unelevated, full pass with `--if-low-disk` | ~4 min, off-session |

## The four classes, and what proves each disposable

| Class | Removed only when | Never |
|---|---|---|
| `basetemp` | under a configured temp root (OS temp, plus the repo's drive root for `ta-*` only), and **every child** is a pytest artifact, untouched for `--min-age-hours` (6) | one unrecognised child, or a `.git` entry — those go to the worktree class |
| `worktree` | a worktree of **this** repo, no open PR, idle `--worktree-idle-hours` (24) by recursive mtime, clean of tracked *and* ignored content, content-merged into `origin/main` | the primary checkout, `main`/`master`/`production`, detached HEAD, another project |
| `docker` | `docker builder prune` with a probed keep-budget flag, engine up | volumes, images, containers, `system prune`, `-a` |
| `scratch` | a closed allowlist of repo-root names, `git check-ignore` confirms ignored, older than `--min-age-days` (7) | `output/`, `universes/`, `logs/`, `data-room/`, `.secrets/`, `.codex-worktrees/`, `.tmp/`, `.review/`, anything tracked |

**Every unknown is a KEEP** — an undecidable git query, an unrecognised shape, a
tree over its entry budget, an unstattable entry, a link (a link counts nothing and
is never followed). Each pass is capped at `--max-removals` (25) per class, as
`daemon_image_retention.MAX_REMOVALS` is on the droplet. Branch refs are deleted
only on the merged path, with `-d`.

**The gate git does not have:** `git worktree remove` decides cleanliness with
`git status --porcelain`, which omits ignored files — how a checkout that looked
like cruft held 4,711 lines of unique research (Hard Rule 13). Worktrees are also
scanned `--ignored=matching`, matched **by path component**, and both scans re-run
immediately before removal.

## By hand

```bash
python scripts/dev_hygiene.py             # dry-run inventory (the default)
python scripts/dev_hygiene.py --verbose    # plus every KEEP and its reason
python scripts/dev_hygiene.py --apply --if-low-disk 40 --escalate-below 40
```

Exit `3` is escalation: the disposable set cannot clear the threshold, and the
block printed names every refused item and why. `--apply` is the only mode that
deletes; it logs path, size and reason to `.claude/logs/dev-hygiene.log`.

## The one thing it asks a human for

Sandbox-token ACLs. A lane that pointed `--basetemp`/`TMPDIR` under a restricted
token leaves directories the interactive user cannot read, list, or delete.
Reported as `acl_locked_needs_elevation`; cleared with an **elevated**
`scripts/clear_sandbox_temp_dirs.ps1 -Apply`. Prevention is in `tests/conftest.py`.

Otherwise it escalates only lanes needing a decision — dirty, unmerged, unpushed,
or holding unique ignored content. Land or abandon them; it will not choose.
`scripts/wt.py sweep` remains the interactive reaper.

## Scaling later (not built)

Dev box only for now (founder, 2026-09-26: *"scaled with users as needed, but
that's mostly later"*). The rules above are written to survive the move: they
apply unchanged to the production host and per-universe scratch, and every
machine-specific value — prefixes, classes, age floors, keep budget, per-pass cap,
roots — is a constant or a flag, with the extra temp root defaulting to the repo's
own drive rather than a literal `C:\`. Three classes would have to be added, and
are not: **per-universe quotas** (a reclaim decision needs a tier quota, not one
global floor), **scratch-lease reclamation** (the proof becomes "the lease
expired", not "the mtime is old"), and **host disk expansion** (escalation should
be able to end in "grow the volume"). Production pressure stays
`DISK_AUTOPRUNE_PCT` + `scripts/daemon_image_retention.py`, untouched here.
