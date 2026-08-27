# OpenSpec all-day drain supervisor

> **RETIRED (2026-08-26).** `openspec_drain_supervisor.py`, its watchdog, tray,
> and autostart installer were deleted in the harness reset — autonomous
> background workers are out of scope under the two-provider decision. Every
> command below refers to something that no longer exists. Kept as the record of
> how the drain worked, not as a runbook. Recover from git at `e4180697`.


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
claimable rows, policy-qualified stale claims, exact-current-main OpenSpec flow,
current blocker evidence, and safe cross-cutting recovery in that order. After
a `NO_CANDIDATE` marker, the controller independently recomputes owned,
claimable, stale, and refinable pressure; any nonzero count rejects the result
and consumes a bounded failure strike. Two ignored rejections therefore become
visibly down instead of silently treating a non-empty backlog as exhausted.

Immediately before dispatch, the controller fetches origin and injects at most
five ordered candidate hints classified from one exact `origin/main` snapshot:
STATUS through `claim_check.py --status-ref origin/main --json`, and, when no
ordinary row is eligible, OpenSpec flow through `openspec_flow.py audit --ref
origin/main --json`. It does not move the live detached checkout or mix stale
working-tree artifacts into that snapshot. Invalid ref/archive evidence fails
closed.

Owned, claimable, and stale hints retain deterministic mechanical admission.
A `REFINERY` hint is coordination-only: the worker may land one exact reviewed
pending/blocked STATUS row for the named existing change, but cannot implement,
sync, or archive it. A PARTIAL promotion is normally admitted by the next fresh
worker. Exact STATUS row lifecycle edits are implicit and do not globally lock
the file; all product/artifact Files atoms retain ordinary collision checks.

Codex drain workers are launched at `medium` reasoning effort even when the
host's interactive Codex default is `high`. The drain's narrow preselected
slice, tests, independent review, CI, and finite budgets provide the quality
boundary while keeping admission latency proportional to the task.

Admission itself is deterministic and does not consume a coding-worker turn.
The controller takes the first canonical hint, runs the bounded claim feed,
fetches current main, creates a purpose-named branch/worktree, writes
`_PURPOSE.md`, commits the exact STATUS claim, persists that admission, and only
then launches the worker with the prepared worktree as cwd. Replacement workers
reuse it. Branch/worktree names include the persisted attempt number, so a
later slice can revisit one still-open target without colliding with its
preserved earlier lane. A pre-existing exact-attempt branch/path fails visibly;
it is never overwritten.
Admission timeouts/errors consume the normal failure budget. `BLOCKED` preserves
the worktree for recovery but releases active admission and skips that target
on the next bounded snapshot. `PARTIAL` retains the lane and requires a
current-main restack before foldback publication.

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

Yellow health with `result_waiting: true` means the current attempt has written
a settled, valid terminal artifact that the controller has not consumed yet.
This is a handoff stall, not active green progress. The watchdog preserves the
run identity so a restart can recover that artifact.

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

For a controller crash after a worker writes its result, resume checks the
exact current attempt before enforcing the failure budget or dispatching a
replacement. A valid result must match the preserved admission and passes
ordinary GitHub merge verification. Invalid, ambiguous, or foreign-target
artifacts fail closed. Successful recovery records the consumed attempt, then
dispatches the next worker; a recovered `PARTIAL` therefore resumes foldback.

If the immediately preceding attempt is recorded as `INVALID_RESULT`, resume
re-parses that exact result artifact before checking the failure budget. When
an upgraded parser now accepts the marker and it matches the preserved
admission, the controller removes only the parser's failure strike and applies
the ordinary result transition. An artifact that remains invalid or reports a
different admitted target leaves the failure budget unchanged.
Pre-change result records may lack an attempt number. The controller may infer
the current counter only from a persisted terminal `failure-budget` state,
where no later attempt can have started; all non-terminal legacy states fail
closed instead of guessing.

## Terminal results

- A mechanically admitted prompt names its exact canonical result target. The
  marker uses that slug, not the human STATUS label. The parser defensively
  canonicalizes a literal human label through the same bounded slug rule.
- `MERGED`: PR is merged and foldback is complete; controller verifies GitHub
  and counts one slice.
- `PARTIAL`: PR is merged but spec sync/archive or STATUS foldback remains; the
  next worker resumes the same target without counting a completed slice. If
  that worker also returns `PARTIAL` for the same target, the controller
  consumes a failure strike and waits before trying again.
- `BLOCKED`: a durable task, host, dependency, review, or policy gate prevents
  progress; the target is preserved in the recent-block list. The controller
  immediately considers a different eligible owned, claimable, or stale candidate
  and idles when none remains. Refinery targets take the ordinary idle backoff.
- `NO_CANDIDATE`: owned, claimable, stale, and refinable pressure are all zero;
  the controller idles rather than inventing work.
- `FAILED`: worker or delivery-infrastructure failure; consumes the
  consecutive-failure budget while preserving the admitted worktree for a
  fresh worker to resume. Verified work that cannot be staged, committed,
  pushed, or published as a PR is `FAILED`, not `BLOCKED`.

Workers publish from their assigned worktree with shell `git` and `gh`.
Write-capable Codex workers receive the linked worktree's resolved Git common
directory as an additional writable root and use `danger-full-access`, because
Codex protects Git metadata under workspace-write even when that root is added.
This mode is allowed only in the prepared, claimed worktree; claim, review, CI,
and finite budgets are the safety boundary. Read-only peers stay read-only. On
Windows, the peer launcher uses `CREATE_NO_WINDOW`, including when the CLI
resolves to a `.CMD` shim.

CLI-unavailable exit 127 stops immediately. Authentication/rate-limit-shaped
failures receive at most three consecutive free idle retries; later repeats
consume failure strikes. Missing, echoed, multiple, or non-final result markers
are failures. While the launcher is live, the controller accepts the same valid
terminal artifact on two one-second observations, terminates the lingering
launcher tree, and applies ordinary admission/result validation. An outer
worker timeout terminates the launcher tree only when no such stable artifact
is available.

When resuming after an unrecoverable `failure-budget`, raise `--max-failures`
above the persisted failure count only after correcting and inspecting the
underlying problem; otherwise the resumed controller correctly exits before
dispatch.

## End-of-day proof

Record:

- start/end active OpenSpec changes and unchecked tasks from
  `scripts/openspec_flow.py audit`;
- controller-verified merged slice count;
- partial/blocked/no-candidate/failure counts;
- preserved PR/result/worktree links;
- whether any claim or worktree remained after its worker.

Use that evidence to tune slice duration and only then consider concurrency.
