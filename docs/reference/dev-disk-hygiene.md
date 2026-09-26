# Dev-box disk hygiene (automatic)

On 2026-09-26 the Windows dev box's C: drive (931 GB) reached **0 bytes free** and
broke every agent lane. None of it was project data. It was agent scratch:
126 pytest `--basetemp` directories holding 7.9 GB, ~330 git worktrees of this
repo, Docker build cache, and repo scratch folders. The production droplet
already self-cleans (`scripts/daemon_image_retention.py` count-based retention
plus the `disk_watch.py` timer); the dev side had nothing, so the founder was
being asked about it periodically instead.

Founder directive 2026-09-26: **disk cleaning is part of the architecture, not a
question.** `scripts/dev_hygiene.py` is that part.

## What runs by itself

| Mechanism | What it does | Cost |
|---|---|---|
| `.claude/hooks/dev_hygiene_hook.py` (SessionStart) | `--apply` on the two cheap classes (`basetemp,scratch`) every session start; injects an escalation into session context when free space is under the floor | ~4 s (measured 2026-09-26: basetemp 3.4 s, scratch 0.3 s) |
| `scripts/install_dev_hygiene_task.ps1` | registers `TinyAssets-DevHygiene`, an hourly unelevated Task Scheduler job running the **full** pass with `--if-low-disk`; writes `.claude/logs/dev-hygiene-full.json` | ~2.5 min, off-session |

The hook is the primary mechanism because it already exists here, needs no
elevation or install step, is version-controlled with the repo (so every lane on
the box gets it), and sessions are what create the garbage. Its only gap is that
it fires only when a session starts — the scheduled task covers the hours a long
background lane runs unattended. The hook reads the task's summary file, so an
unattended escalation is seen at the next session start without the session
paying for its own full scan.

Neither can block or fail a session: the hook always exits 0, and a pass that
times out injects nothing.

## The four classes and what proves each disposable

| Class | Removed only when | Never |
|---|---|---|
| `basetemp` | directly under the OS temp root, name matches an agent-convention prefix, **and every child** is a pytest artifact (a `<slug><N>` numbered dir, `.lock`, `garbage-*`, a `*-current` link), untouched for `--min-age-hours` (6) | anything with one unrecognised child; anything containing a reparse point |
| `worktree` | a worktree of **this** repo per `git worktree list --porcelain`, clean of tracked *and* ignored content, idle for `--worktree-idle-hours` (24) by **recursive** newest mtime, and content-merged into `origin/main` (or PR closed with every commit on a remote) | the primary checkout, `main`/`master`/`production`, a detached HEAD, another project's repo |
| `docker` | `docker builder prune` with a keep budget whose flag was probed from `--help`, only when the engine answers | volumes, images, containers, `system prune`, `-a` |
| `scratch` | a name on a closed allowlist in the repo root, `git check-ignore` confirms it is ignored, older than `--min-age-days` (7) | `output/`, `universes/`, `logs/`, `data-room/`, `.secrets/`, `.codex-worktrees/`, `.tmp/`, `.review/`, or anything tracked |

A branch ref is deleted only on the `merged_and_clean` path, with `git branch -d`.
A PR-closed lane loses its worktree and **keeps its branch ref** as the recovery
path: `git log --not --remotes` and `git branch -d` both read *local* tracking
refs, so neither can tell a live remote branch from a tracking ref that was pruned
after the PR closed. A ref costs ~41 bytes; the worktree is the disk win.

**Every unknown is a KEEP.** An undecidable git query, an unrecognised directory
shape, a tree over the entry budget, and a tree containing a symlink or junction
all fail closed. Each pass is also capped at `--max-removals` (25) per class —
the same idea as `daemon_image_retention.MAX_REMOVALS` on the droplet, so a pass
that runs by itself can never do something enormous and a logic bug shows up in
the log before the next pass.

### The guard that matters most

`git worktree remove` decides cleanliness with `git status --porcelain`, which
**omits ignored files entirely**. That is how a checkout that looked like stale
cruft came to hold 4,711 lines of unique research on 2026-08-26 (Hard Rule 13).
So a worktree is also scanned with `--ignored=matching`, and any ignored path
outside a short disposable allowlist (`.venv/`, `__pycache__/`, caches,
root-only `_PURPOSE.md`, `.agents/supervisor/` session telemetry) keeps the
worktree and names the path in the escalation. `.claude/agent-memory/`, `output/`,
`universes/`, `.env`, and `.secrets/` are all unique work by this rule.

On the real inventory this held back 75 of 328 worktrees, and the shape gate on
`basetemp` held back whole stale repo checkouts (`ta-base-tree`, `ta-baseline-*`)
kept deliberately as audit oracles — a prefix match alone would have destroyed
them.

Three properties of that allowlist are load-bearing, each one a defect cross-family
review found before this shipped:

* **Matching is by path component**, never substring or bare prefix. A rule of
  `startswith` accepted `_PURPOSE.md-git-credentials.txt`, and a nested
  `docs/_PURPOSE.md` was accepted as disposable although `wt.py` only ever
  archives the root copy.
* **An extension is not a provenance.** `*.db` was on the allowlist because this
  repo ignores it for the SQLite mirror of its YAML catalog. The same pattern
  covers a user's own database — on the real box it would have removed a 103 MB
  worktree holding `test.db`.
* **A collapsed directory entry is not a content check.** `--ignored=matching`
  reports a wholly-ignored directory as one line, so accepting `.agents/supervisor/`
  says nothing about what is in it. Its contents are verified against the
  filenames its producers actually emit (`events.jsonl`, `seen.json`,
  `keep-working-*.json`); anything else keeps the worktree.

### Idleness is a recursive mtime, and nothing else

The first version answered "is a session still using this lane?" with a cheap scan
of the worktree's direct children plus its gitdir's `index`/`HEAD`. That
measurement is **invalidated by its own caller**: the collector runs `git status`
first, which rewrites `gitdir/index`. Measured on 2026-09-26 — 72.0h before the
status call, 0.0h after. It has been deleted rather than kept as a second opinion;
the recursive newest mtime from the size walk is the whole answer, it was already
being computed, and `git status` does not touch the worktree tree (a linked
worktree holds only a `.git` *file*).

### Everything is re-verified at the removal boundary

Inventory and removal are minutes apart on a full pass, and `git worktree remove`
re-checks tracked cleanliness but not ignored content. So a worktree's dirty and
ignored scans both run again immediately before removal, and a `_PURPOSE.md`
archive that fails **aborts** the removal rather than logging and continuing —
that archive is the only thing preserving an unpublished lane draft.

## Running it by hand

```bash
python scripts/dev_hygiene.py                       # dry-run inventory (default)
python scripts/dev_hygiene.py --verbose              # plus every KEEP and its reason
python scripts/dev_hygiene.py --json                 # machine-readable
python scripts/dev_hygiene.py --apply --classes basetemp
python scripts/dev_hygiene.py --apply --if-low-disk 40 --escalate-below 40
```

Exit `3` means escalation: the disposable set cannot bring free space above the
threshold, and the block printed names every item it refused to remove with the
reason. `--dry-run` is the default; `--apply` is the only mode that deletes, and
it appends every removal (path, size, reason) to `.claude/logs/dev-hygiene.log`.

## Escalation is the only thing it asks you for

Two founder-facing classes it will not resolve on its own:

* **ACL-locked temp dirs.** A sandbox agent that pointed `--basetemp`/`TMPDIR` at
  a path under a restricted token leaves a directory the interactive user cannot
  read, list, or delete (68 of them on 2026-09-26, plus two inside the repo:
  `.codex-test-tmp/`, `.pytest-tmp/`). Reported as
  `acl_locked_needs_elevation`; cleared with an **elevated**
  `powershell -ExecutionPolicy Bypass -File scripts/clear_sandbox_temp_dirs.ps1 -Apply`.
  Prevention is in `tests/conftest.py`, which refuses a temp root inside the repo.
* **Lanes needing a decision.** Dirty, unmerged, unpushed, or ignored-content
  worktrees. Land them or abandon them (`python scripts/wt.py done --force
  --reason '...'`); the tool will not choose.

## Relationship to the existing tools

`scripts/wt.py sweep` is the interactive worktree reaper and stays the right tool
when a human is driving; `dev_hygiene.py` reuses its `_archive_purpose` so a
lane's unpublished `_PURPOSE.md` still lands in
`.git/tinyassets-worktrees.log` before anything is removed, and it reuses
`git_squash_merge.is_merged_into` for the squash-aware merge proof. It adds the
three gates `wt.py` does not have: ignored-content, idleness, and
commits-on-no-remote.

### On the unpushed-commits check

`git log <head> --not --remotes` is non-empty for **every** squash-merged branch —
its pre-squash history is reachable from no remote. The invariant that check
protects is "no work exists only here", and `is_merged_into` already proves the
branch's cumulative diff is on the base, so for a merged branch those commits are
duplicates of landed content. The check therefore gates the *not-merged* path,
where an unreachable commit is real unique work and the worktree is kept.

Known limit, accepted: `is_merged_into`'s squash path ends in `git cherry`, which
compares patch IDs, and patch IDs normalize whitespace. A branch differing from
the base by whitespace alone therefore reads as merged. The bounded consequence is
that such a lane's *working files* are removed while its branch ref survives —
`git branch -d` refuses a branch git does not consider merged, and the tool
reports "branch kept as the recovery ref". `is_merged_into` is the repo's shared
squash-merge oracle (`scripts/wt.py` and `scripts/worktree_status.py` both use
it); a second definition here would be worse than the limit.

### Links, and platform notes

**One rule for every link, on every platform: it contributes nothing to a size and
is never descended into.** Two different mechanisms, one fact:

* `entry.is_dir(follow_symlinks=False)` returns **True** for a Windows junction, so
  a naive walk crosses into the target and counts its bytes (measured: 4,106 where
  10 were inside).
* A POSIX symlink is not descended into, but its **own** `lstat` size is the length
  of its target path — 38 bytes in a WSL probe — which is not content in this tree
  either. Counting it is what made the assertion `size == 10` red on Linux CI at
  48.

Both returns of `tree_stats` are load-bearing (size ranks the escalation, newest
mtime is the idleness gate), so counting either would be a lie about a different
directory. An earlier version raised `Undecidable` on any reparse point; that was
unnecessary once nothing is counted or followed, and it cost real coverage — 2
worktrees and 7 temp dirs permanently un-inventoriable, and it would have refused
every POSIX tree holding a `.venv/bin` symlink. The remaining guard is at the
deletion boundary: `remove_path` refuses a link handed to it directly. `shutil.rmtree`
does **not** delete through a nested junction either — `shutil._rmtree_islink` tests
`IO_REPARSE_TAG_MOUNT_POINT` (Python 3.14) and a 2026-09-26 probe confirmed the
target survived removal of the parent.
* Git writes loose objects read-only, so `shutil.rmtree` raises WinError 5 on any
  basetemp holding a checkout — which is most of them. The remover does one chmod
  sweep and retries; a failure after that reports **partial** removal, because
  `rmtree` deletes as it walks and "kept" would imply the path is intact.
* Status parsing uses `--porcelain -z`. The newline form quotes and escapes a path
  with spaces or non-ASCII bytes, and stripping the quotes leaves the escapes
  undecoded.
