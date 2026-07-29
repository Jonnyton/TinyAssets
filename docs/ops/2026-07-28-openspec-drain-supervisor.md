# OpenSpec all-day drain supervisor

## Purpose

Use one small persistent controller to drain OpenSpec delivery debt for a
bounded workday. The controller launches one fresh subscription-authenticated
Codex or Claude CLI worker at a time. Each worker may deliver at most one PR;
after the worker exits, the controller verifies merge state, persists compact
state, and launches a fresh context for the next slice.

This is queue contraction, not a utilization floor. Do not run
`fleet_supervisor.py` at the same time.

## Automatic Windows mode

Normal daily operation is automatic. The one-time installer registers
`TinyAssets OpenSpec Drain` for the current user at Windows sign-in:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_openspec_drain_autostart.ps1 `
  -Repo C:\Users\Jonathan\Projects\wf-openspec-drain-controller
```

Sign-in is the correct boot boundary: Codex/Claude subscription credentials and
the notification-area tray icon exist only in the interactive user session.
The task has no execution-time limit and ignores duplicate starts.

The tray indicator maps:

- information/healthy icon: watchdog and drain controller are running;
- warning icon: starting, recovering, blocked, idle, or stopping;
- error icon: health is stale, the controller is down, or a terminal failure
  requires explicit restart.

Its menu opens the active run, opens a live status watcher, requests a bounded
restart, stops until the next sign-in, or exits only the indicator. Closing the
indicator does not stop the watchdog.

The watchdog adopts an existing manual drain without dispatching another
worker. After an abrupt shutdown it resumes the newest unfinished run directory,
preserving the exact `drain-<run-id>` identity and any live STATUS claim.
Runtime/slice budget completion can start another finite run during the same
computer session; fatal/failure-budget outcomes remain down.

Yellow `idle` is valid only after proved exhaustion. A worker must process
claimable rows, policy-qualified stale claims, current blocker evidence, and
safe cross-cutting recovery in that order. After a `NO_CANDIDATE` marker, the
controller independently runs `claim_check.py --json`; any nonzero claimable,
stale, or exact-drain-owned count rejects the result and consumes a bounded
failure strike. Two ignored rejections therefore become visibly down instead
of burning subscription in an endless false-idle loop.

Direct health commands:

```powershell
py scripts/openspec_drain_watchdog.py status
py scripts/openspec_drain_watchdog.py restart
py scripts/openspec_drain_watchdog.py stop
```

Uninstall without deleting run evidence:

```powershell
py scripts/openspec_drain_watchdog.py stop
powershell -ExecutionPolicy Bypass -File scripts/install_openspec_drain_autostart.ps1 -Uninstall
```

Wait for the tray to show down before uninstalling. The installer removes the
sign-in task and indicator; the watchdog stop request is what safely prevents a
new worker from starting.

## Safety model

Write-capable peer workers are not reliably OS-sandboxed on this Windows host:
the Codex shim bypasses approvals/sandboxing and Claude uses
`--dangerously-skip-permissions`. Safety therefore comes from:

- a clean current-main controller checkout;
- a new purpose-named worktree for every worker lane;
- exact STATUS file claims and collision/admission checks;
- one acceptance contract and one PR per worker;
- finite worker/workday/slice/failure budgets;
- required independent review and GitHub CI/auto-merge;
- controller-side `gh pr view` verification before a slice counts;
- persistent prompts/results/state and a graceful stop file.

Do not run the controller against the dirty primary checkout.

## First acceptance run

From any checkout, create a clean detached controller worktree:

```powershell
git fetch --prune origin
$drainController = "C:\Users\Jonathan\Projects\wf-openspec-drain-controller"
git worktree add --detach $drainController origin/main
Set-Location $drainController
```

Generate and inspect one worker prompt without dispatch:

```powershell
py scripts/openspec_drain_supervisor.py run `
  --repo $drainController `
  --run-dir output/openspec-drain-smoke `
  --hours 1 `
  --max-slices 1 `
  --dry-run
```

Use a new run directory for the single-worker live acceptance:

```powershell
py scripts/openspec_drain_supervisor.py run `
  --repo $drainController `
  --run-dir output/openspec-drain-once `
  --hours 2 `
  --max-slices 1 `
  --worker-timeout 5400 `
  --once
```

Inspect `state.json`, `supervisor.log`, `prompts/`, and `results/`. A useful
acceptance ends in a controller-verified merged PR, an honest blocked/no-work
result, or a preserved actionable failure. It must not create multiple PRs.

## Run for a workday

After the acceptance pass is clean:

```powershell
$drainRun = "output/openspec-drain-$(Get-Date -Format yyyyMMdd-HHmmss)"
Start-Process `
  -FilePath "py" `
  -ArgumentList @(
    "scripts/openspec_drain_supervisor.py",
    "run",
    "--repo", $drainController,
    "--run-dir", $drainRun,
    "--provider", "codex",
    "--hours", "8",
    "--max-slices", "8",
    "--worker-timeout", "5400",
    "--max-failures", "2",
    "--idle-minutes", "30"
  ) `
  -WorkingDirectory $drainController `
  -WindowStyle Hidden
```

Provider and optional model are fixed for a run:

```powershell
--provider claude --model opus
```

Use the model name currently accepted by the installed CLI. If Claude's default
model is rate-limited, pin a reachable model rather than repeatedly restarting
the controller.

## Monitor and stop

In automatic Windows mode, use the watchdog commands shown above or the tray
menu. A direct supervisor stop ends only the current bounded run; the watchdog
will interpret that clean ending as permission to start the next bounded run.
The direct commands below are for intentionally manual supervisor runs.

```powershell
py scripts/openspec_drain_supervisor.py status --run-dir $drainRun
Get-Content "$drainRun\supervisor.log" -Tail 30
py scripts/openspec_drain_supervisor.py stop --run-dir $drainRun
```

Idle waiting checks the stop file every five seconds. An active worker is
allowed to return or reach its finite timeout; no new worker starts afterward.

## Resume and recovery

The exact `drain-<run-id>` STATUS identity persists across replacement workers.
If a worker times out after claiming work, the next fresh worker resumes that
claim before selecting another.

A normal stopped/finished run releases `supervisor.lock`. After a controller
crash:

1. Verify no matching supervisor/peer process is live.
2. Inspect `state.json`, the last prompt/result, STATUS, GitHub PRs, and the
   worker worktree.
3. Resume with the same provider/model and explicit stale-lock recovery:

```powershell
py scripts/openspec_drain_supervisor.py run `
  --repo $drainController `
  --run-dir $drainRun `
  --provider codex `
  --hours 4 `
  --resume `
  --recover-stale-lock `
  --clear-stop
```

Never use `--recover-stale-lock` merely because a live controller appears slow.
Recovery checks the PID stored in the lock through the Windows process API and
refuses to replace it while that controller is alive.

## Terminal results

- `MERGED`: PR is merged and foldback is complete; controller verifies GitHub
  and counts one slice.
- `PARTIAL`: PR is merged but spec sync/archive or STATUS foldback remains; the
  next worker resumes the same target without counting a completed slice. If
  that worker also returns `PARTIAL` for the same target, the controller
  consumes a failure strike and waits before trying again.
- `BLOCKED`: target is preserved in the recent-block list; controller idles.
- `NO_CANDIDATE`: nothing is safely deliverable; controller idles rather than
  inventing work.
- `FAILED`: worker-level failure; consumes the consecutive-failure budget.

CLI-unavailable exit 127 stops immediately. Authentication/rate-limit-shaped
failures receive at most three consecutive free idle retries; later repeats
consume failure strikes. Missing, echoed, multiple, or non-final result markers
are failures. An outer worker timeout terminates the launcher process tree.

When resuming after `failure-budget`, raise `--max-failures` above the persisted
failure count after correcting the underlying problem; otherwise the resumed
controller correctly exits before dispatch.

## End-of-day proof

Record:

- start/end active OpenSpec changes and unchecked tasks from
  `scripts/openspec_flow.py audit`;
- controller-verified merged slice count;
- partial/blocked/no-candidate/failure counts;
- preserved PR/result/worktree links;
- whether any claim or worktree remained after its worker.

Use that evidence to tune slice duration and only then consider concurrency.
