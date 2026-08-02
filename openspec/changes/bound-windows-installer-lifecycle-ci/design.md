## Context

PR #2078 wrapped each installer, health-probe, repair, and uninstall process in `Process.WaitForExit(180000)` and added a 15-minute GitHub job timeout. Most runs now finish in under 70 seconds, but runs 30722063982, 30722054273, 30723889111, 30724201497, and 30724652715 remained inside the lifecycle step until GitHub cancelled them about twenty minutes after job start. GitHub documents that job cancellation can retain a stuck step for a further five-minute forced-termination window. The cancelled jobs retained no downloadable log blob, so the job timeout proves eventual runner reclamation but does not provide a precise or diagnostic lifecycle gate.

The current timeout handler performs process-tree discovery and synchronous tree termination inside the same PowerShell process that executes the lifecycle. Any hang in lifecycle code or cleanup therefore prevents that process from reporting failure. The release gate needs an independent authority that can terminate and report the whole child lifecycle.

The first repair attempted to make another PowerShell script that authority. Exact PR #2110 run 30725711495 reproduced the real hang and remained in the step beyond the supervisor's five-minute deadline until the ten-minute GitHub job cancellation began. That proves the PowerShell `Start-Process` / cleanup chain still shared an unbounded Windows process-control failure mode. Because the runner did not expose a live log or stack, the exact stuck call is unknown; the recovery therefore replaces that chain rather than adding another timeout inside it.

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

### 1. Supervise the PowerShell lifecycle from a stdlib Python parent

The workflow pins Python through `actions/setup-python` and invokes a stdlib-only supervisor. The supervisor launches `windows_lifecycle.ps1` as a child `pwsh` process, redirects stdout and stderr to anonymous temporary binary files, and calls `Popen.wait(timeout=...)` for the total deadline. PowerShell is now only the tested lifecycle child; process wait, timeout classification, byte-capped replay, and fallback cleanup are owned by the Python parent.

Alternative considered: retain the PowerShell supervisor and wrap more of its calls. Rejected because exact PR evidence shows the supposed parent failure domain also escaped, while the unavailable live stack cannot prove which PowerShell process-control call needs another wrapper.

### 2. Separate the total deadline from the GitHub fallback

The supervisor defaults to a five-minute total deadline. The GitHub job retains a ten-minute timeout. A caught lifecycle hang therefore has five minutes to report and terminate before the platform fallback begins, while the normal 38-70 second path remains unaffected.

Alternative considered: retain four independent 180-second phases as the only bound. Rejected because the recurring failure proves an in-process bound is not an independent failure boundary.

### 3. Capture output outside the child process

The child writes stdout and stderr to anonymous `TemporaryFile` handles. The supervisor snapshots and replays at most 256 KiB from each stream before returning success or failure, and emits the observed byte count when evidence is truncated. Redirecting away from the runner pipe prevents an escaped descendant from retaining the workflow step's output handle; the byte-capped snapshot prevents a noisy or surviving writer from extending replay past the total-deadline margin.

Alternative considered: inherit the workflow console directly. Rejected because an escaped descendant can keep inherited handles open and the historical forced cancellations produced no retained log blob.

### 4. Keep cleanup bounded and subordinate to the verdict

On total timeout the Python supervisor invokes hidden `taskkill.exe /T /F` for the exact lifecycle child PID through `subprocess.run(..., timeout=10)`, then applies an exact-root `Popen.kill()` fallback and another bounded `wait`. It reports timeout regardless of cleanup outcome. The GitHub runner remains defense-in-depth cleanup authority. The inner phase timeout stops only its exact root process and throws.

Alternative considered: continue synchronous `.Kill($true)` inside the lifecycle. Rejected because tree cleanup occurs in the same failure domain as the code being bounded.

## Risks / Trade-offs

- **A descendant survives both bounded cleanup attempts** -> anonymous file handles prevent it from holding the workflow pipe open; Python reports without waiting for descendants, while runner cleanup and the job timeout remain defense in depth.
- **The five-minute total deadline is too short on a loaded runner** -> normal evidence is under 70 seconds; the deadline is configurable and a timeout reports captured phase evidence instead of silently extending.
- **Redirected output is delayed until child completion** -> CI loses live phase streaming but gains retained caught-failure evidence; phase names and PIDs remain explicit in the replay, and each stream is byte-capped with truthful truncation evidence.
- **A forced timeout cannot identify the historical phase** -> the next caught recurrence records phase-start evidence, turning the non-reproducible incident into actionable data.

## Migration Plan

1. Replace the failed PowerShell supervisor with the stdlib Python parent, update the noisy-child regression, and pin Python in the lifecycle job.
2. Observe the exact-head Windows lifecycle job complete successfully or fail under the supervisor before the ten-minute job fallback.
3. Retain the job timeout as defense in depth.
4. Roll back by reverting the PR; the prior behavior remains safe from publication but can occupy a runner for twenty minutes.

## Open Questions

None for this bounded recovery. The next captured timeout, if any, decides whether a product-level installer/probe repair is required.
