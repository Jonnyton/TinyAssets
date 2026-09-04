# Windows lifecycle installer is cancelled without a verdict or log

**Filed:** 2026-09-04 00:04 PDT  
**Verified:** 2026-09-04, GitHub Actions run `33843457460`, attempts 1 and 2  
**Severity:** P2

## Source (verbatim)

Attempt 1, exact job `100931525845`:

> `conclusion":"cancelled"`  
> `Install, probe, repair, and uninstall exact CI artifact` — `status":"in_progress"`

Attempt 2, exact bounded rerun job `100936661082`:

> `started_at":"2026-09-04T06:44:04Z"`  
> `completed_at":"2026-09-04T06:59:04Z"`  
> `conclusion":"cancelled"`  
> `Install, probe, repair, and uninstall exact CI artifact` — `status":"in_progress"`

GitHub returned no retained job log for the cancelled attempt:

> `log not found: 100936661082`

## Finding

The Voice provider-binding PR's unsigned Windows artifact built successfully,
downloaded successfully, and entered the lifecycle supervisor twice. The first
attempt was cancelled after the PR merged. One bounded rerun of the exact job
and exact head rebuilt all three platform artifacts successfully, then was also
cancelled after fifteen minutes while the lifecycle step was still in progress.
Neither attempt emitted a terminal supervisor verdict or retained a downloadable
log, so neither proves pass or product failure.

This is the same observable failure shape recorded in
`docs/audits/2026-08-02-windows-lifecycle-supervisor-escape.md`: the workflow's
configured supervisor and job deadlines did not yield an inspectable terminal
receipt. That earlier incident was repaired and subsequently completed in 46
seconds, so the 2026-09-04 recurrence needs diagnosis rather than repeated
reruns.

## Scope

This does not invalidate the deployed server/app Voice proof: the exact merge
image deployed healthy and passed the authenticated public MCP canary, and the
running production Voice gates are independently default-off. It does leave the
desktop unsigned-install lifecycle without fresh exact-head acceptance evidence.

## Next action

Reproduce the lifecycle supervisor on an isolated Windows runner with durable
per-phase checkpoints that survive cancellation, determine which child or phase
outlives the 300-second supervisor budget, and repair the workflow so its own
deadline emits a terminal verdict before GitHub can cancel the job. Do not start
another blind rerun without adding that evidence path.
