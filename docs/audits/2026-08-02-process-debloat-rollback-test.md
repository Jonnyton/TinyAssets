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

## Codex plan review (reject → adapted, 2026-08-02)

The cross-family review of the execution plan returned `reject` with
findings that were each adopted:

- **`restart.request` was live** (written 23:46 PT, after the stop
  request): the watchdog was in "stopping before restart" mode and
  would have relaunched. Deleted at 2026-08-02T06:50Z; health now
  reads "stopping until next sign-in".
- **`stop.request` is not durable**: every fresh watchdog start deletes
  it and resumes orderly-stopped drains. Fix: a `drain.off` marker in
  the watchdog dir that both entry points honor and never auto-clear
  (`scripts/openspec_drain_watchdog.py` + `openspec_drain_supervisor.py`,
  covered by `tests/test_drain_off_marker.py`; also applied to the live
  controller worktree copies and the marker created). Removing the file
  is the only re-enable — add that to the restore steps below.
- **STATUS Concern rows are advisory**: the supervisor parses Work
  rows, not Concerns. Machine enforcement is the drain.off marker; the
  Concern text remains for humans and provider sessions.
- **Sweep losslessness had two counterexamples**: (1) gitignored
  worktree-local artifacts are silently deleted by `git worktree
  remove` — `wf-activity-null-results` holds a 69-byte git-credentials
  artifact and is force-skipped + flagged to the host; the sweep now
  skips any lane whose ignored files fall outside a known-disposable
  set (caches, pycache, sandbox test-temp). (2) HEAD-reflog-only
  commits lose their recovery path — the sweep now creates
  `refs/debloat-backup/<lane>/<sha>` for any reflog sha not reachable
  from the branch tip or origin/main before removal.
- The in-flight worker attempt may land one final refinery PR before
  the supervisor observes the stop; accepted rather than hard-killing
  mid-write.

## Codex re-review round 2 (adapt → adopted, 2026-08-02)

- **The drain re-armed itself once more**: the still-running task tree
  restarted the (old-code) watchdog, which deleted `stop.request` at
  startup and re-attached to the live supervisor (attempt 9). Adopted:
  runtime polling of `drain.off` inside both loops —
  `wait_interruptibly(off_file=...)` in the supervisor and
  `stop_restart_signals()` in the watchdog loop (off forces stop and
  vetoes restart requests) — so a marker appearing mid-run stops the
  drain without a process restart. Stop was re-armed
  (`supervisor.stop` + `stop.request`) with a bounded hard-stop
  fallback (`Stop-ScheduledTask`) if the graceful window expires.
- **Credential-scatter root cause found and fixed**: the main repo's
  local `.git/config` set
  `credential.helper = store --file C:\...\Projects\Workflow\...`
  (pre-rename path, unquoted backslashes, shared by every worktree) —
  any credential fill wrote the mangled flat file into the CWD, which
  is how ~450 copies accumulated, including one in a worktree created
  the same day. Fixed to the canonical TinyAssets path with forward
  slashes. All residual copies (19 more under `.claude/worktrees/` and
  nested lanes) verified byte-identical to the canonical file, then
  deleted; fleet-wide count is now 0. Token rotation remains a host
  ask.
- **Sweep executor hardened further**: per-lane revalidation
  immediately before each removal (clean + landed + ignored-screen +
  reflog), and a detached-HEAD backup ref (a detached HEAD is
  reachable from itself, so it previously earned no backup yet lost
  its only ref on removal — latent, no current lane matches).

## Restore steps (if the test says restore)

```powershell
Enable-ScheduledTask -TaskName "TinyAssets OpenSpec Drain"
Enable-ScheduledTask -TaskName "TinyAssets OpenSpec Drain Guard"
# remove BOTH markers (drain.off is the durable off switch):
Remove-Item "C:\Users\Jonathan\Projects\wf-openspec-drain-controller\output\openspec-drain-watchdog\drain.off"
Remove-Item "C:\Users\Jonathan\Projects\wf-openspec-drain-controller\output\openspec-drain-watchdog\stop.request" -ErrorAction SilentlyContinue
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

## Phase 2 executed: worktree sweep (2026-08-02)

154 lanes removed, 0 skipped, 213 backup refs under
`refs/debloat-backup/` (reflog shas unreachable from the branch tip and
origin/main, plus detached-HEAD protection). Each lane was revalidated
immediately before removal: clean tree (`_PURPOSE.md`-only allowed) AND
landed (HEAD ancestor of origin/main, or HEAD exactly equal to a merged
PR's `headRefOid` — the squash-merge-safe proof) AND ignored files all
in the disposable set. No branches deleted; no `--force`. 63 lanes with
unique local artifacts (review briefs, `knowledge.db`, dist builds)
were left in place, as were all dirty and genuinely-unmerged lanes.
Fleet: 552 → ~405 worktrees.

## Later phases (tracked in the STATUS Work row)
3. OpenSpec backlog triage: force-archive to actively-built changes,
   adopt a WIP limit and a skip-threshold (small changes need no spec).
4. AGENTS.md/CLAUDE.md shrink toward "short, accurate"; convert rules
   that matter into executable checks; gate the cross-family dispatch
   reflex to judgment-class decisions.

## ADDENDUM 2026-08-02 ~13:10 PT — experiment CONTAMINATED (third drain resurrection)

The OFF condition held ~13h (23:39 Aug 1 → 12:55 Aug 2 PT), then was
externally reversed while a Claude session was live:

- `drain.off` marker DELETED (actor unknown; the tray/watchdog scripts
  never delete it — this was a separate deliberate or destructive act).
- Both schtasks RE-ENABLED between two checks minutes apart (Disabled at
  ~13:04, Ready/Running at ~13:08). Task Scheduler operational log is
  disabled — no attribution. A Codex session with
  `--dangerously-bypass-approvals-and-sandbox` had been running since 12:17.
- **Third automation layer found** (never covered by the shutdown):
  "TinyAssets OpenSpec Drain" (logon trigger) and "TinyAssets OpenSpec
  Drain Guard" (daily + 1-minute repetition) both run
  `launch_openspec_drain_tray.vbs` → hidden `openspec_drain_tray.ps1`
  → watchdog relaunch. The patched watchdog gate passed legitimately
  because the marker was already gone; it auto-resumed run
  20260801-215608 (attempt 11) with a live peer write-worker on
  bind-host-principal prompt 011.
- Deliberately NOT re-killed: an active concurrent agent is maintaining
  it (restart-loop fight risk; mid-write worker corruption risk; the
  cloud-drain-vs-rollback host decision is still open).

**Consequence:** the 2026-08-09 re-measurement is INVALID as designed
(the OFF window is 13h, not 7d). Options for the host decision row:
(a) drain stays ON → re-purpose the baseline as a with-drain measurement
and skip the rollback; (b) drain goes OFF again → disable BOTH schtasks
AND delete both tray launch scripts (or add drain.off honoring to the
tray), recreate `drain.off`, restart the 7-day clock; (c) fold into the
cloud-drain decision and retire the local drain machinery entirely.
