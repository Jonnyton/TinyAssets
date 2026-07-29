## Context

The drain supervisor is bounded and recoverable, but today a host must remember
to launch it and can observe it only through files or a separate watcher. The
current Windows host normally shuts down without giving the controller a
graceful stop. Codex subscription authentication and a tray icon both belong to
the interactive user session, so a true pre-login Windows service is the wrong
boundary.

## Goals / Non-Goals

**Goals:**

- Start at user sign-in with no daily prompt or terminal.
- Attach to a live drain without duplication and resume the same identity after
  abrupt termination.
- Run for the signed-in computer session while retaining finite per-controller
  budgets and fail-closed provider failure stops.
- Make health continuously visible through a system-tray icon and simple menu.
- Install and uninstall idempotently under the current Windows user.

**Non-Goals:**

- Run before user sign-in or without the user's subscription credentials.
- Suppress failure budgets or restart fatal/failure-budget outcomes forever.
- Stream private model reasoning or make the headless CLI interactive.
- Turn the drain into a multi-worker fleet.

## Decisions

### 1. A stdlib watchdog owns continuity, not task selection

`openspec_drain_watchdog.py` discovers the newest unfinished drain, checks the
recorded lock PID using the supervisor's Windows-safe liveness probe, and takes
one of four actions: attach, resume, start new, or remain down. It delegates all
selection, claims, workers, merge proof, and budgets to the existing supervisor.

An unended run with a live controller is attached. An unended run with a dead
controller is resumed with the same run directory and identity. A clean ended
budget starts a fresh run. Fatal and failure-budget outcomes remain down until
an explicit tray restart.

Alternative: always create a new run on boot. Rejected because an abruptly
killed worker may hold a same-day claim owned by the old drain identity.

### 2. Sign-in Task Scheduler boundary

The installer registers one current-user `AtLogOn` task with
`MultipleInstances=IgnoreNew` and no execution time limit. The task launches the
tray script, which starts or attaches to the watchdog. This is the first reliable
moment when the user's Codex credentials and interactive notification area are
both available.

Alternative: `AtStartup` SYSTEM task. Rejected because it has no interactive
tray and must not inherit or copy the user's subscription credentials.

### 3. Health is a compact watchdog file plus a tray projection

The watchdog atomically writes `health.json` with state, active run directory,
controller PID, last transition, and diagnostic message. The tray polls it and
maps `running` to an information/healthy icon, blocked/idle/recovering/stopping
to warning, and failed/stale/down to error. The context menu opens status/logs
and writes explicit restart/stop request markers.

Closing the tray hides only the indicator. `Stop until next sign-in` asks the
supervisor to stop and exits the watchdog after the active worker returns.

### 4. Session-long operation remains bounded

Watchdog-launched supervisors use one worker, a 24-hour runtime budget, 100
merged-slice ceiling, 90-minute worker timeout, and two consecutive failures.
Clean runtime/slice exhaustion may roll into a new bounded run while the
watchdog remains alive. Failure/fatal outcomes never auto-roll.

### 5. Existing manual run is adopted during installation

Discovery prioritizes any unended run over ended smoke/history directories, so
installing while today's manual drain is alive attaches rather than duplicating
it. After merge, the permanent clean controller worktree is advanced to current
main before the scheduled task is installed.

## Risks / Trade-offs

- **Windows shutdown kills state writers abruptly.** -> Atomic state/health
  writes and exact-identity resume treat missing `ended_at` as interrupted.
- **Task or tray starts twice.** -> Task Scheduler ignores duplicate instances;
  watchdog and tray also hold independent single-instance locks/mutexes.
- **Provider repeatedly fails.** -> Supervisor failure budget produces red/down;
  watchdog requires explicit restart.
- **Tray process exits while work continues.** -> Health stays on disk and the
  watchdog continues; the scheduled task restores the tray at next sign-in.
- **Permanent controller checkout becomes stale.** -> Stability wins over
  self-mutating startup. Installer records the exact path; future upgrades
  advance that dedicated clean checkout before reinstall.
- **No tool-level live stream.** -> The tray shows honest lifecycle health and
  completed result/log transitions, not fabricated progress.

## Migration Plan

1. Land the watchdog, tray, installer, tests, docs, and spec.
2. Advance the dedicated controller worktree to merged `origin/main`.
3. Run watchdog decision tests and a no-dispatch isolated smoke.
4. Register the current-user sign-in task idempotently.
5. Start it once; verify it attaches to today's live drain, creates green health,
   and exposes menu actions without dispatching a second worker.
6. Reboot/sign-in proof remains the next real machine-cycle observation; the
   installed task and recovery decision are inspectable beforehand.

Rollback: unregister `TinyAssets OpenSpec Drain`, close the tray/watchdog, and
continue using the existing manual supervisor commands. Runtime artifacts remain
under ignored `output/`.

## Open Questions

None.
