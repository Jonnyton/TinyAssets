# Windows lifecycle installer is cancelled without a verdict or log

**Filed:** 2026-09-04 00:04 PDT  
**Verified:** 2026-09-04, GitHub Actions runs `33843457460`, `33916000603`,
and `33920975686`
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

The same failure recurred on PR #2936, run `33916000603`, job
`101164590946`. The artifact download completed at `20:29:17Z`; the lifecycle
step remained `in_progress` until the run was explicitly cancelled at
`20:44:03Z`, and GitHub again returned `log not found`. All other PR gates were
green. This is the smallest evidence GitHub retained; it identifies the
lifecycle step but cannot distinguish one of its child phases.

PR #2936's first guarded head, `e3447755`, subsequently completed the exact
Windows lifecycle job `101171997094` in 39 seconds and emitted
`process_tree.closed`. That normal-output pass proves the Job Object closes the
observed escape, but it does not clear the sustained-output disk-exhaustion
defect described below; a fresh bounded-capture head still needs the exact gate.

The failure then recurred on Voice PR #2944, run `33920975686`, exact job
`101180235516`. The job started at `21:30:07Z`, remained in
`Install, probe, repair, and uninstall exact CI artifact`, and was cancelled
at `21:45:07Z`. GitHub's annotation was `The job has exceeded the maximum
execution time of 10m0s`. The exact merged Voice image independently deployed
healthy and passed the authenticated public canary and protected revision
receipt, but live microphone acceptance remains held at the founder boundary.

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

The as-built cause of the missing verdict is now narrower than the logless
child phase: `--total-timeout-seconds 300` wraps only
`process.wait(timeout=...)`. Process creation, Job Object calls, tree cleanup,
drain shutdown, capture replay, temporary-file finalization, and interpreter
teardown are outside that deadline. The flag therefore never implemented the
spec's claimed whole-supervisor bound. With no independent watchdog, a stall in
any of those paths can survive until GitHub cancels the job and discards its
only diagnostic stream. The cancelled log cannot identify which one stalled,
so naming a specific child phase would be invented evidence.

## Scope

This does not invalidate the deployed server/app health proof: the exact merge
image deployed healthy and passed the authenticated public MCP canary and
protected revision receipt. Production serves the corrected Voice transport
configuration, but live Voice acceptance remains held before microphone capture
until this exact Windows proof returns a terminal verdict.

## Repair in progress

The existing bounded pipe capture and kill-on-close Job Object remain. The
narrow correction arms `faulthandler`'s native watchdog around the complete
supervisor before preflight, with a 420-second deadline between the 300-second
child wait and 600-second GitHub job timeout. If ordinary control flow stalls,
the watchdog writes every thread stack directly to workflow stderr and exits
non-zero. A Windows regression exercises the hard deadline independently of
the child-wait deadline. Keep this concern open until a fresh exact-head
lifecycle job returns a terminal verdict; then delete it rather than annotating
it as resolved.
