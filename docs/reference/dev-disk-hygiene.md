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
| `basetemp` | directly under the OS temp root, name matches an agent-convention prefix, **and** the contents have pytest's numbered-dir shape, untouched for `--min-age-hours` (6) | anything whose shape it does not recognise; anything containing a reparse point |
| `worktree` | a worktree of **this** repo per `git worktree list --porcelain`, clean of tracked *and* ignored content, idle for `--worktree-idle-hours` (24), and content-merged into `origin/main` (or PR closed with every commit on a remote) | the primary checkout, `main`/`master`/`production`, a detached HEAD, another project's repo |
| `docker` | `docker builder prune` with a keep budget, only when the engine answers | volumes, images, containers, `system prune`, `-a` |
| `scratch` | a name on a closed allowlist in the repo root, `git check-ignore` confirms it is ignored, older than `--min-age-days` (7) | `output/`, `universes/`, `logs/`, `data-room/`, `.secrets/`, `.codex-worktrees/`, or anything tracked |

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
`_PURPOSE.md`, `.agents/supervisor/` session telemetry) keeps the worktree and
names the path in the escalation. `.claude/agent-memory/`, `output/`,
`universes/`, `.env`, and `.secrets/` are all unique work by this rule.

On the first real inventory this held back 71 of 328 worktrees, and the shape
gate on `basetemp` held back whole stale repo checkouts (`ta-base-tree`,
`ta-baseline-*`) kept deliberately as audit oracles — a prefix match alone would
have destroyed them.

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
  read, list, or delete (68 of them on 2026-09-26, plus three inside the repo:
  `.codex-test-tmp/`, `.pytest-tmp/`, `.tmp/`). Reported as
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
