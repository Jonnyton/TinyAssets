# Branch & Worktree Lifecycle Automation

**Filed:** 2026-06-24
**Status:** building (host-approved: all 4 layers, report-first janitor)
**Owner:** claude-code (background session)

## Problem

The primary checkout drifted to **1,209 commits behind** `main` while sitting
on a dead feature branch, with **458 branches** and **177 worktrees**
accumulated across Codex / Cursor / Claude Code / Cowork sessions. The host
("an agentic engineer") correctly read this as a *missing automation* signal,
not a one-off cleanup.

Root cause: the repo has rich hygiene **conventions** (`claim_check.py`,
`worktree_status.py`, `_PURPOSE.md`, `.agents/worktrees.md`, the AGENTS.md
"Parallel Dispatch" ritual) but **zero enforcement automation**. Every ritual
is something a human or agent is *supposed* to run, so nothing ran. Two
concrete gaps confirmed the diagnosis:

- No branch-cleanup or worktree-prune GitHub Action existed (26 workflows,
  none for hygiene).
- `fetch.prune` was not set, so deleting a branch on GitHub never cleaned up
  local refs. Table-stakes hygiene was off.

## Industry direction (2026 research)

1. **Delete-on-merge is a habit, not a batch job.** The winning move is
   auto-deleting a PR's head branch the moment it merges. GitHub exposes this
   as a one-click repo setting (`delete_branch_on_merge`).
2. **Trunk-based development with sub-1-day branches** is the DORA-backed
   standard and maps doubly well to AI agents: "by the time you merge, half the
   agent's assumptions are wrong." Small, verified, frequent merges + a green
   `main` is the loop agents thrive in.
3. **One task -> one branch -> one worktree -> one agent**, sibling dirs,
   committed lifecycle scripts, a manifest. TinyAssets already invented this; it
   just never automated the teardown half.
4. **Stale-branch janitors run server-side on a schedule**, report-first
   (2-4 week dry run), with hard guardrails: protect `main`, never touch
   branches with open PRs or commits in the last 7 days, grace period before
   deletion.

Sources reviewed: GitHub Docs (auto-delete head branches, merge queue),
trunkbaseddevelopment.com / Atlassian (trunk-based + DORA), MindStudio /
Augment / appxlab (worktrees for parallel AI agents), stale-branch-cleaner
GitHub Action patterns.

## Design — four layers

Principle alignment: runs with **zero hosts online** (Forever Rule) and makes
drift **detected, not discovered** (loop-telemetry philosophy).

### Layer 0 — Native delete-on-merge + local prune (table stakes)
- `delete_branch_on_merge=true` on the repo (DONE 2026-06-24 via `gh api`).
- `fetch.prune=true`, `fetch.pruneTags=true`, `rerere.enabled=true` global git
  config; `scripts/setup_git_hygiene.py` makes this idempotent + repeatable on
  any machine / provider.

### Layer 1 — Scheduled janitor (`scripts/branch_janitor.py` + workflow)
Daily GitHub Action, **host-independent**. Classifies every remote branch:
- `MERGED` (ancestor of `origin/main`) -> safe to delete immediately; the
  commits are already on main.
- `STALE_FLAG` (unmerged, no commits in `STALE_DAYS=7`, no open PR) -> flag in
  a single rolling tracking issue.
- `STALE_DELETE` (flagged + still untouched past `GRACE_DAYS=14` total) ->
  delete in `--apply` mode.
- `PROTECTED` / `ACTIVE` -> never touched.

**Guardrails (hard):** never delete `main`/`master`/`production`/`release/*`;
never delete a branch with an open PR; never delete a branch with a commit
younger than `RECENT_DAYS=7`, regardless of total age. (Thresholds tightened
from 30/45 to 7/14 per host directive 2026-06-25 — minimal lingering.)

**Rollout (host directive 2026-06-24):** the report-first wait was waived. The
scheduled run defaults to `apply-all`, so once the workflow lands on `main` its
first run sweeps the backlog (MERGED + STALE_DELETE) and it self-maintains
daily thereafter. Hard guardrails still protect main/release, open-PR branches,
and commits < 7d. `report` remains available as an on-demand dry-run via
`workflow_dispatch`.

### Layer 2 — `wt` lifecycle wrapper (`scripts/wt.py`)
One command for both halves of the loop so teardown stops being optional:
- `wt new <slug>` — `fetch --prune` -> `git worktree add` off `origin/main` ->
  scaffold `_PURPOSE.md` -> append create event to `.agents/worktrees.md`.
- `wt done [slug]` — verify the branch merged into `origin/main` (refuse
  otherwise unless `--force`) -> remove worktree -> delete branch -> append
  remove event.
- `wt list` — thin pass-through to `worktree_status.py`.

### Layer 3 — Session-start sync gate (`scripts/session_sync_gate.py`)
Provider-agnostic. Run at session start by every provider (Claude Code wires
it as a `SessionStart` hook; Codex/Cursor call the script):
- `git fetch --prune` (quiet).
- Warn loudly if the primary checkout is **off `main`** or **behind
  origin/main** — the exact "1,209 behind / dirty" trap.
- Never mutates the working tree; advisory only (honors hard rule #13).

### Layer 4 — Weekly health report
The janitor workflow's `health` job posts branch count / worktree-ref count /
oldest-stale-age / behind-count to the rolling tracking issue, so drift is a
number the host watches, not a surprise.

## Files
- `scripts/branch_janitor.py`, `tests/test_branch_janitor.py`
- `scripts/wt.py`
- `scripts/session_sync_gate.py`
- `scripts/setup_git_hygiene.py`
- `.github/workflows/branch-janitor.yml`
- `.claude/hooks/session_sync_gate_hook.py` (+ settings.json wiring)

## Open items / host decisions
- Optional later: GitHub **merge queue** to keep `main` green under heavy
  parallel agent merges (note the 2026-04-23 merge-queue silent-drop incident —
  enable only with the `merge_group` CI event wired).
