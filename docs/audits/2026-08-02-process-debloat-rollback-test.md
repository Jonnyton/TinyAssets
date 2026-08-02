# Process de-bloat: drain rollback test (host directive 2026-08-02)

**Freshness:** 2026-08-02, measured on origin/main + live Windows host.
**Authority:** host directive 2026-08-02 ("proceed as the research suggests"),
following a four-source research pass (three primary-source sweeps + two
adversarial Codex reviews, both `partially-confirmed`).

## What was found

- STATUS.md was modified in 180 of the last 200 origin/main commits.
- ~30% of the last 500 commit subjects were coordination ceremony
  (reproducible regex count 148/500) vs a 0.6% baseline (3/500) three
  weeks earlier.
- 552 local `wf-*` worktrees; 167 coordination-purpose. OpenAI's default
  worktree retention is 15.
- 39 live `openspec/changes/` vs 28 as-built specs. OpenSpec's own docs
  prescribe no refinery, no blocker grooming, and a fast
  propose→apply→archive loop.
- The drain incident of record: 32 attempts, 0 delivery slices, all
  health signals green (`docs/audits/2026-08-01-drain-coordination-churn.md`).
- Frontier consensus (Anthropic harness post 2026-03, Cognition 2026-04,
  Berkeley MAST, DORA 2025): ~75% of multi-agent failures originate in
  coordination/system design; scale the verification layer, shrink the
  coordination layer; scaffolds encode model-weakness assumptions that
  must be re-tested each model generation.

## What was done (phase 1 — controlled rollback probe)

| Step | Detail | Timestamp (UTC) |
|---|---|---|
| Graceful stop | `wf-openspec-drain-controller/output/openspec-drain-watchdog/stop.request` written | 2026-08-02T06:39:16Z |
| Autostart off | Scheduled tasks `TinyAssets OpenSpec Drain` + `TinyAssets OpenSpec Drain Guard` **disabled** (not deleted) | 2026-08-02T06:41Z |

Run state at stop: identity `drain-20260801-215608-88f22d`, 8 attempts,
2 completed slices (recorded for fairness — this run was performing
better than the 32/0 incident run).

## Measurement plan (re-run on/after 2026-08-09)

Compare OFF-week vs the prior week, all on origin/main:

1. Delivered OpenSpec slices (implementation commits landed + changes
   archived/synced), not attempts.
2. Product share of line churn (`tinyassets/` vs total,
   `git log --numstat`).
3. Coordination-commit share of subjects (the 148/500 regex).
4. STATUS.md touch rate per 200 commits.
5. Merged PRs touching `tinyassets/` or `tests/` (product) vs
   coordination-only PRs.

Decision rule: if delivered slices and product share hold or improve
with the drain off, retire the drain machinery permanently (its spec
lane too); if they degrade materially, restore and redesign the drain
to emit implementation lanes only.

## Restore steps (if the test says restore)

```powershell
Enable-ScheduledTask -TaskName "TinyAssets OpenSpec Drain"
Enable-ScheduledTask -TaskName "TinyAssets OpenSpec Drain Guard"
# then delete the stop marker or start with --clear-stop:
Remove-Item "C:\Users\Jonathan\Projects\wf-openspec-drain-controller\output\openspec-drain-watchdog\stop.request"
```

## During the test week

- Do NOT restart the drain or create new refinery/coordination-only
  lanes ("correct the exact STATUS blocker; coordination only" lanes).
- Product work, uptime work, canaries, deploys continue completely
  unchanged — the drain is coordination-only and not load-bearing for
  the Forever Rule (verified: it requires interactive Windows sign-in
  and is separated from host-independent uptime in PLAN.md).
- The `codex-gpt5-desktop-cloud` "cloud drain as user-built MVP fixture"
  lane (STATUS row) is unaffected and already anticipated stopping the
  local tray after cloud acceptance.

## Later phases (tracked in the STATUS Work row)

2. Lossless worktree sweep: remove only worktrees with a clean tree
   (`_PURPOSE.md`-only allowed) whose HEAD is an ancestor of
   origin/main; no branch deletion; skip `.codex-worktrees/` and the
   drain controller.
3. OpenSpec backlog triage: force-archive to actively-built changes,
   adopt a WIP limit and a skip-threshold (small changes need no spec).
4. AGENTS.md/CLAUDE.md shrink toward "short, accurate"; convert rules
   that matter into executable checks; gate the cross-family dispatch
   reflex to judgment-class decisions.
