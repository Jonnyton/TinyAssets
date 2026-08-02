# OpenSpec Drain Autostart — Claude Safety Review

Date: 2026-07-28
Reviewer: Claude Code peer
Scope: recovery safety, Windows integration, duplicate-dispatch prevention

## Initial verdict: ADAPT

The reviewer confirmed that a dry-run attached to the existing live controller
without creating another supervisor. The current-user Task Scheduler surface,
finite supervisor budgets, fail-closed terminal handling, and three
single-instance layers were also sound.

The review required these changes before installation:

1. Promote `starting` / `recovering` to healthy once the supervisor lock PID is
   live, so the tray cannot stay yellow forever after a successful launch.
2. Resume with the provider and model persisted in the run state and make an
   early supervisor exit a sticky down state, preventing a relaunch hot loop.
3. Remove a stale restart marker before initial discovery, preventing an old
   request from bypassing adoption of a live manual controller.
4. Retry atomic health replacement across transient Windows sharing
   violations, so tray polling cannot crash the watchdog.
5. Include the supervisor's exact default `output/openspec-drain` directory in
   discovery.
6. Explain that automatic mode must be stopped through the watchdog, and that
   uninstall should follow a completed watchdog stop.

Each blocking item has a focused regression test. A narrow follow-up review is
required after the fixes and before installation.

## Follow-up verdict: APPROVE

Claude re-read the adapted implementation and independently confirmed:

- live `starting` / `recovering` controllers now become healthy;
- resume preserves the persisted provider/model and early death stays
  explicitly down rather than hot-looping;
- startup clears stale restart intent before discovery;
- Windows health-file sharing violations are retried;
- the exact default run directory is discovered;
- a tray restart can revive a dead watchdog while the watchdog lock,
  supervisor lock, tray mutex, and graceful stop-before-restart sequence prevent
  duplicate dispatch.

The reviewer found no installation blocker. Local evidence on 2026-07-28,
Windows 11:

- `68 passed` for focused supervisor/watchdog tests;
- Ruff clean;
- both PowerShell files parsed cleanly;
- strict OpenSpec validation passed;
- a temporary scheduled task registered with three one-minute restart attempts
  and uninstalled cleanly;
- a dry-run attached to live controller PID 41220 with identity
  `drain-20260728-193150-076c7c`, while the supervisor process-match count
  remained unchanged.
