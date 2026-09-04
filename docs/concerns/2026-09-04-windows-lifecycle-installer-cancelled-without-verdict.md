# Windows lifecycle installer is cancelled without a verdict or log

**Filed:** 2026-09-04 00:04 PDT  
**Verified:** 2026-09-04, GitHub Actions runs `33843457460` and `33916000603`
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

## Repair in progress

The direct-file capture bounded replay but not storage: sustained child output
could fill the runner disk before either timeout returned a verdict. The repair
drains private pipes while storing at most the configured cap, assigns the
lifecycle tree to a kill-on-close Job Object, closes that object before any
bounded drain wait, and requires an escaped descendant to be gone before the
supervisor returns. Keep this concern open until a fresh exact-head lifecycle
job returns a terminal verdict; then delete it rather than annotating it as
resolved.
