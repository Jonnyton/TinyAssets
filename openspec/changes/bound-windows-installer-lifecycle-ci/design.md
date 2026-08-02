## Context

PR #2078 wrapped each installer, health-probe, repair, and uninstall process in `Process.WaitForExit(180000)` and added a 15-minute GitHub job timeout. Most runs now finish in under 70 seconds, but runs 30722063982, 30722054273, and 30723889111 remained inside the lifecycle step until GitHub cancelled them about twenty minutes after job start. GitHub documents that job cancellation can retain a stuck step for a further five-minute forced-termination window. The cancelled jobs retained no downloadable log blob, so the job timeout proves eventual runner reclamation but does not provide a precise or diagnostic lifecycle gate.

The current timeout handler performs process-tree discovery and synchronous tree termination inside the same PowerShell process that executes the lifecycle. Any hang in lifecycle code or cleanup therefore prevents that process from reporting failure. The release gate needs an independent authority that can terminate and report the whole child lifecycle.

## Goals / Non-Goals

**Goals:**

- Bound the complete lifecycle independently of every operation inside it.
- Finish caught hangs before GitHub begins job cancellation.
- Retain phase output and the supervisor's timeout evidence on caught failures.
- Exercise the supervisor with a real hung child on Windows.
- Preserve the existing exact-artifact install, probe, repair, uninstall, singleton-autostart, and content-preservation checks.

**Non-Goals:**

- Diagnose which product process caused historical hangs when GitHub retained no logs.
- Publish or sign desktop artifacts.
- Replace the clean-machine or signed-artifact acceptance matrix.
- Add production runtime process supervision.

## Decisions

### 1. Supervise the lifecycle from a separate PowerShell process

The workflow invokes a new supervisor. The supervisor launches `windows_lifecycle.ps1` as a child `pwsh` process, redirects its stdout and stderr to unique runner-temp files, and waits for one total deadline. Because the deadline owner is outside the lifecycle process, an inner wait, diagnostic query, or cleanup operation cannot disable the outer bound.

Alternative considered: lower only `timeout-minutes`. Rejected because GitHub adds a documented five-minute forced-cancellation window and the affected jobs retained no logs.

### 2. Separate the total deadline from the GitHub fallback

The supervisor defaults to a five-minute total deadline. The GitHub job retains a ten-minute timeout. A caught lifecycle hang therefore has five minutes to report and terminate before the platform fallback begins, while the normal 38-70 second path remains unaffected.

Alternative considered: retain four independent 180-second phases as the only bound. Rejected because the recurring failure proves an in-process bound is not an independent failure boundary.

### 3. Capture output outside the child process

The child writes stdout and stderr to unique files beneath `RUNNER_TEMP` (or the operating-system temp directory locally). The supervisor replays both streams before returning success or throwing. Redirecting away from the runner pipe also prevents an escaped descendant from retaining the workflow step's output handle.

Alternative considered: inherit the workflow console directly. Rejected because an escaped descendant can keep inherited handles open and the historical forced cancellations produced no retained log blob.

### 4. Keep cleanup bounded and subordinate to the verdict

On total timeout the supervisor starts hidden `taskkill.exe /T /F` for the exact lifecycle child PID, waits at most ten seconds for the killer, and then reports timeout regardless of cleanup outcome. The GitHub runner remains defense-in-depth cleanup authority. The inner phase timeout stops only its exact root process and throws; the outer supervisor remains able to terminate the complete child tree if inner cleanup stalls.

Alternative considered: continue synchronous `.Kill($true)` inside the lifecycle. Rejected because tree cleanup occurs in the same failure domain as the code being bounded.

## Risks / Trade-offs

- **A descendant survives both bounded cleanup attempts** -> redirected output prevents it from holding the step open; the runner's process cleanup and job timeout remain defense in depth.
- **The five-minute total deadline is too short on a loaded runner** -> normal evidence is under 70 seconds; the deadline is configurable and a timeout reports captured phase evidence instead of silently extending.
- **Redirected output is delayed until child completion** -> CI loses live phase streaming but gains retained caught-failure evidence; phase names and PIDs remain explicit in the replay.
- **A forced timeout cannot identify the historical phase** -> the next caught recurrence records phase-start evidence, turning the non-reproducible incident into actionable data.

## Migration Plan

1. Land the supervisor, lifecycle instrumentation, regression tests, and workflow invocation in one PR.
2. Observe the exact-head Windows lifecycle job complete successfully or fail under the supervisor before the ten-minute job fallback.
3. Retain the job timeout as defense in depth.
4. Roll back by reverting the PR; the prior behavior remains safe from publication but can occupy a runner for twenty minutes.

## Open Questions

None for this bounded recovery. The next captured timeout, if any, decides whether a product-level installer/probe repair is required.
