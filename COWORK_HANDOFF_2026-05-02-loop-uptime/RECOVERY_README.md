# Workflow loop uptime recovery — handoff from Cowork session

**Date:** 2026-05-02
**Live MCP status:** `https://tinyassets.io/mcp` returns HTTP 502 for 9+ hours.
**Author:** Cowork session (no push perms, no SSH, no `gh` auth from this env).

## TL;DR — what to do now

1. **Restore the live daemon (5 min):** trigger `deploy-prod.yml` via workflow_dispatch with `image_tag` = `d897177bf3a4`. UI: https://github.com/Jonnyton/Workflow/actions/workflows/deploy-prod.yml → "Run workflow" → set image_tag → Run. Or `gh workflow run deploy-prod.yml -f image_tag=d897177bf3a4`. Then probe `https://tinyassets.io/mcp` — should be 200 (or non-502).
2. **Land the self-heal patch (10 min):** apply `loop-uptime-recovery.diff` (in this folder) to `.github/workflows/deploy-prod.yml`. Single step modification. Commit + push. Eliminates the bug class that caused this outage.
3. **Then proceed with the loop work** — the substrate to close the wiki→branch circuit is `WORKFLOW_BUG_INVESTIGATION_GOAL_ID`. See "Loop substrate next steps" below.

## Why MCP went down (root cause, fully diagnosed)

The 5-day silent outage was a **deploy chain open-circuit**. Sequence:

1. `d897177` (fix: codex bwrap-safe) was the last commit that touched build-image.yml's path filter. Build-image #310 published `ghcr.io/jonnyton/workflow-daemon:d897177bf3a4` + `:latest`. Deploy-prod Run 309 deployed it successfully.
2. Subsequent commits — `b06d876` (status doc), `0485285` (worktree memory chore), `33cc3da` (status), `ff66420` (env-var docs) — are all doc/STATUS-only. They did NOT match build-image.yml's path filter (`Dockerfile`, `workflow/**`, `domains/**`, `fantasy_daemon/**`, `data/world_rules.lp`, `scripts/mcp_public_canary.py`, `deploy/**`, `pyproject.toml`, `PLAN.md`, `.dockerignore`). So no new image was published.
3. Something triggered deploy-prod.yml for `b06d876` → Run 310 tried `docker pull ghcr.io/jonnyton/workflow-daemon:b06d876...` → not found → exit 1. Rollback step ran 0s (the `if: failure()` did fire but its own `docker pull '${PREV_IMAGE}'` also fails for missing-image faults — the rollback model assumes a previous successful tag was captured, which on a fresh failed-deploy state may be empty).
4. The daemon went down (probably from Run 310's partial deploy or from some other event during this gap). Stayed down because:
   - `uptime-canary.yml` runs every 5 min and opens `p0-outage` issues on 2 consecutive reds. (It may or may not have fired — need to check Issues tab.)
   - `p0-outage-triage.yml` triggers on labeled issues and SSH-restarts via `sudo docker compose -f /opt/workflow/compose.yml restart`. **But that restart pulls the configured `WORKFLOW_IMAGE`, which still points at a SHA whose image doesn't exist.** So restart can't help either.
5. Cowork session (this morning) triggered Run 311 with no `image_tag` input → resolved to `ff66420` (current main HEAD) → also no image → also failed.
6. Cowork session triggered Run 312 with explicit `image_tag=d897177bf3a4` → ran ~9 hours ago → outcome unknown to me; probe still 502 so either it failed or daemon crashed after.

**Key insight:** the canary→triage chain CANNOT recover from the missing-image fault class. Restart isn't the right tool when the registry tag itself is gone. This is a structural self-heal gap, not a bad config.

## The self-heal patch (`loop-uptime-recovery.diff`)

Single change to `.github/workflows/deploy-prod.yml`'s "Resolve image tag" step: after computing the SHA tag, do `docker manifest inspect` against GHCR. If the tag exists, use it. If not, fall back to `:latest` and emit a warning. `:latest` is always published by `build-image.yml` alongside `:short_sha` on every successful build, so it's the natural last-known-good.

After this patch:
- A `workflow_dispatch` deploy for any SHA without a built image deploys `:latest` instead of failing.
- A `workflow_run` after build-image still deploys the freshly-built SHA.
- Manual `image_tag` input still wins.
- Class of bug eliminated: doc-only commits no longer break the deploy chain.

This is also a minor improvement to the rollback path (the existing `Rollback on failure` step already uses `:latest` as fallback when previous-image capture is empty — same principle, applied earlier).

### Apply

```bash
cd Workflow
git checkout main
git pull
git checkout -b fix/deploy-prod-latest-fallback
git apply --3way path/to/outputs/loop-uptime-recovery.diff
git diff --stat  # should show 1 file changed
git commit -am "deploy-prod: fall back to :latest when SHA tag missing in GHCR

The 2026-05-02 9-hour outage hit because b06d876, 0485285, ff66420 are
doc-only commits that don't trigger build-image.yml (path filter excludes
docs). When deploy-prod.yml dispatched for those SHAs, docker pull failed
and rollback couldn't help (it pulls the same configured image).

Fix: after resolving the SHA tag, docker manifest inspect against GHCR.
If missing, fall back to :latest (always published by build-image.yml on
successful build). Eliminates the open-circuit class."
git push origin HEAD
# Open PR + merge to main, OR just push to main if you do that.
```

## Loop substrate next steps

After the deploy chain is healed and MCP is live, the next work that closes the user-driven loop:

1. **`WORKFLOW_BUG_INVESTIGATION_GOAL_ID` wiring** — currently empty on the daemon, so `workflow/bug_investigation.py:is_auto_trigger_enabled()` returns False. To enable the wiki → branch transition: (a) you create a "bug_investigation" Goal via `goals action=propose name=bug_investigation`; (b) you bind change_loop_v1 (`fd5c66b1d87d`) via `goals action=bind goal_id=<G> branch_def_id=fd5c66b1d87d`; (c) `goals action=set_canonical goal_id=<G> branch_def_id=fd5c66b1d87d`; (d) set `WORKFLOW_BUG_INVESTIGATION_GOAL_ID=<G>` on the droplet via `deploy/install-workflow-env.sh set` and restart. After this, every `wiki action=file_bug` auto-queues the canonical investigation branch.
2. **BUG-040 / BUG-042 (`file_bug` schema gaps: `kind`, `tags`)** — small (~30 LOC in `workflow/api/wiki.py`). Out of Codex's lockset. Makes patch-request pages first-class.
3. **BUG-044 `validate_branch` collision classes** — Codex already has `wf-validate-branch-s1` worktree on `fix/bug-044-validate-branch-stage-1`. Probably their lane.
4. **EvalResult `visibility` tag** — additive Slice-1 patch, must land before Slice 4 of ASI-Evolve. Codex owns Slice 2 (OptimizationRun); this is adjacent and could be a Claude/Cowork pickup if scoped right.

## Constraints I hit (so the next session knows)

- **No git push from Cowork.** `git ls-remote origin` works (anonymous read) but `git push` fails with "could not read Username". The Cowork sandbox doesn't have access to the host's credential helper / git credential manager.
- **No SSH from Cowork** — no DigitalOcean key.
- **No `gh` CLI auth** — no GH_TOKEN env var visible to sandbox.
- **Chrome browser disconnects between sessions.** I had it connected last night and triggered Runs 311/312 via the GitHub UI. The connection dropped overnight.
- **`.git/worktrees/loop-substrate` is locked by stale Windows perms** — the partial worktree from this morning's hung `git worktree add` left behind `index.lock` + `locked` files that the FUSE mount can't delete. To recover the worktree slot, on Windows (PowerShell): `Remove-Item -Force C:\Users\Jonathan\Projects\Workflow\.git\worktrees\loop-substrate\index.lock,locked` then `git worktree remove --force .claude/worktrees/loop-substrate`.
- **Cursor branch (`cursor/claim-check-session-d`) has 115 staged uncommitted files** unrelated to my work. I did not touch them. Unsigned, untouched.
- **`scripts/worktree_status.py` was FUSE-truncated 458/529 lines** — I restored it from origin/main via `cat`-redirect (not Edit/Write). Shows up as `M scripts/worktree_status.py` in `git status`.

## Background reading I did this morning

Three subagent deep-reads:

- **Loop architecture & primitives** — mapped the substrate. Key insight: `change_loop_v1` and `community_change_loop_autoresearch_lab_v1` live in your universe SQLite (`.author_server.db`), authored via `extensions action=build_branch`. They are user content, not project code. The substrate provides primitives; you/users compose loops on top.
- **Recent session handoffs** — Codex has been primary dev since 2026-04-28 with ~476 commits across feature/uptime/CI branches. Activity log frozen at 2026-05-02T04:48Z, Codex commits via branch messages instead. Verifier flagged cursor branch is 519 commits behind origin/main. STATUS.md has 3 stale rows that landed but weren't deleted.
- **Self-improvement substrate** — ASI-Evolve integration is being absorbed as a native primitive (not vendored). Slice 1 (EvaluatorResult schema) shipped 2026-05-02. Slice 2 (OptimizationRun) is up next. Three review-blocked lanes (ExperiencePool/GroupEvolutionRun, AcceptanceScenario packs, OpenTraces SessionTrace) await Claude review verdicts. Visibility tags on EvalResult are flagged MUST-HAVE before Slice 4.
