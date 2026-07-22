# Release reconcile cron reliability audit

- **Audit date:** 2026-07-22 UTC
- **Repository:** `Jonnyton/TinyAssets`
- **Base:** `origin/main` at `220a1fc8`
- **Initial finding:** Claude Code, recorded in `.agents/activity.log`
- **Independent review:** Codex (`codex-gpt5-desktop`)
- **Verdict:** Do not move release reconciliation into `uptime-canary.yml` and
  delete the standalone schedule. Keep the independent cron for now and add one
  out-of-GitHub dead-man monitor as the next reliability layer.

## Executive judgment

At the 2026-07-22 01:45 UTC checkpoint, the release reconciler had **not**
eventually fired on its schedule. Its only run was the successful manual
`workflow_dispatch` at 01:24:15 UTC. GitHub reported the workflow itself as
`active`, so this was not a disabled-workflow or invalid-YAML failure.

The missing ticks are consistent with GitHub's documented best-effort scheduler:
scheduled events can be delayed under load and queued jobs can be dropped. The
repository's existing schedules demonstrate that this is not merely a new-file
activation delay. In the 24 hours ending 01:41 UTC, `uptime-canary.yml` produced
14 scheduled runs from 288 nominal five-minute slots (4.9%); gaps ranged from
54.1 to 156.9 minutes, with an 83.6-minute median. The two existing 15-minute
workflows inspected, DNS canary and community-loop watch, were also arriving
roughly hourly.

That evidence makes `uptime-canary.yml` a proven *registered* schedule, but not
a proven five-minute clock. Moving the reconcile job there would provide no
delivery SLA, would place two critical controls in the same workflow/concurrency
group, and would delete one of the few available scheduler attempts. It also
would make the release check's outcome less visible while the uptime workflow is
already concluding red for unrelated probe failures.

One scope correction matters: `build-image.yml` still starts the ordinary
release chain on a release-relevant `push` to `main`, and manual dispatch remains
available. The reconciler is the sole *automatic fallback* when a merge made
with `GITHUB_TOKEN` suppresses the downstream push-triggered workflow. That is
the silent-failure class this audit evaluates; the narrower wording does not
reduce its severity.

## 1. Did the cron eventually fire?

No, not by the audit checkpoint.

Timeline from the live API and `origin/main` history:

| UTC | Evidence |
|---|---|
| 01:06:22 | `release-reconcile.yml` landed in `1437b30a` (#1499). |
| 01:06:24 | GitHub workflow record created; API state is `active`. |
| 01:15 | First `*/15` slot passed with no scheduled run. |
| 01:19:17 | Correctness amendment `32241353` landed (#1500). |
| 01:24:15 | [Manual run 29882999785](https://github.com/Jonnyton/TinyAssets/actions/runs/29882999785) started and succeeded. |
| 01:30 | Second post-creation slot passed with no scheduled run. |
| 01:45 | Third post-creation slot passed with no scheduled run visible at the checkpoint. |

Commands used:

```text
gh run list --workflow release-reconcile.yml --limit 20 \
  --json databaseId,event,status,conclusion,createdAt,startedAt,headSha,url
gh api repos/Jonnyton/TinyAssets/actions/workflows/release-reconcile.yml \
  --jq '{id,name,path,state,created_at,updated_at}'
```

The first command returned one entry, with `event=workflow_dispatch`, and no
`event=schedule` entries. The API returned workflow id `317824618`, state
`active`, and creation time `2026-07-21T18:06:24-07:00`.

This is a freshness-stamped observation, not a claim that the workflow can never
run. A later run would change the answer to "eventually, after a long delay" but
would not restore a 15-minute guarantee.

## 2. GitHub's actual schedule behavior

GitHub documents these properties:

- A scheduled workflow is eligible only when its workflow file exists on the
  default branch, and scheduled runs use the latest commit on that branch.
- Five minutes is the shortest *configured interval*. The documentation does
  not state an execution SLA or a special activation grace period for a newly
  added schedule.
- Scheduled events can be delayed during high Actions load. GitHub calls out the
  start of each hour as a high-load time and explicitly says sufficiently loaded
  queues may drop jobs.
- Public-repository schedules can be automatically disabled after 60 days with
  no repository activity. That condition does not apply here, and the workflow
  API reported `active`.

Primary sources: [Events that trigger workflows — `schedule`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[Troubleshooting scheduled workflows](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#scheduled-workflows-running-at-unexpected-times),
and [Disabling and enabling workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows).

For a newly added workflow, the documented boundary is therefore simple: once
the file is on the default branch it is eligible at a matching cron time. GitHub
does not document a propagation window after creation. The live API showed this
workflow registered and active within two seconds of the landing commit, but the
next matching ticks still produced no run. The defensible interpretation is not
"new schedules take N minutes"; it is "schedule delivery is best effort, with no
documented first-run guarantee."

### Repository evidence under load

The existing canary is useful empirical evidence because it predates this
incident by months:

```text
gh run list --workflow uptime-canary.yml --event schedule --limit 100 \
  --json createdAt,event
```

Filtering those timestamps to the preceding 24 hours yielded:

| Measure | Observed |
|---|---:|
| Configured interval | 5 minutes |
| Nominal slots | 288 |
| Scheduled runs delivered | 14 |
| Delivery ratio | 4.9% |
| Minimum inter-run gap | 54.1 minutes |
| Median inter-run gap | 83.6 minutes |
| Maximum inter-run gap | 156.9 minutes |

This does not prove why GitHub dropped or delayed each tick, but it does refute
the assumption that an old, active `*/5` schedule is presently executing every
five minutes in this repository.

## 3. Detecting that the reconciler stopped running

A workflow can look backward on its next run and report a stale prior heartbeat,
but it cannot alert while no run is being created. Putting a "last tick" check
inside the same GitHub schedule detects recovery after silence, not silence
itself.

The real pattern is one independent dead-man boundary:

1. An external managed scheduler or heartbeat monitor, outside GitHub Actions,
   checks the Actions API (or expects a heartbeat) at a fixed cadence.
2. It pages when the newest successful `event=schedule` reconcile run exceeds a
   defined age. A 30-minute threshold matches the stated 15-minute objective and
   two-miss tolerance; with today's observed gaps it would page, correctly,
   because the objective is already not being met.
3. Optionally, after paging, it can dispatch the reconcile workflow. That turns
   the independent monitor into a recovery trigger as well as a detector and
   requires a narrowly scoped GitHub credential.

Stop the regress at that boundary: GitHub supplies the primary loop; one
operationally independent managed service supplies the dead-man timer and alert
delivery. Do not add a third service solely to watch the second. Instead, test
the dead-man alarm route periodically, use the provider's own status/SLA, and
accept simultaneous failure of both providers as the explicit residual risk.

## 4. Should uptime-canary carry the reconcile check?

Not as a replacement for the standalone schedule.

Reasons:

1. **It is not meeting its configured cadence.** Fourteen of 288 nominal ticks
   is liveness evidence, but not a clock suitable for a 15-minute release
   objective.
2. **The failure domain is unchanged.** Both triggers depend on GitHub's
   scheduler. Consolidation removes a registration and an independent queued
   attempt; it does not create an independent witness.
3. **The current workflow has unrelated triggers and workflow-level
   concurrency.** `uptime-canary.yml` also runs on `workflow_dispatch` and
   successful `Deploy prod` completions. Its single `uptime-canary` concurrency
   group permits only one running and one pending workflow run; a newer pending
   run can replace an older pending run. A release-critical job would inherit
   that coupling unless the concurrency design were changed.
4. **The outcome would be harder to see.** The canary is currently red for probe
   failures. A successful reconcile job inside a failed workflow is less obvious
   than a separate `Release reconcile` run and does not satisfy "cannot fail
   silently."

Accordingly, this audit makes no workflow change and does not delete
`.github/workflows/release-reconcile.yml`.

## Recommended next slice

Treat the current cron as a best-effort recovery attempt, not the alarm. Add one
external dead-man monitor with a 30-minute stale-run threshold, an independent
page route, and a periodic alarm-path drill. Keep the standalone schedule until
that monitor has produced clean evidence; only then reconsider consolidation
based on measured delivery and failure-domain value.

This next slice changes operational architecture and credentials, so it is not
silently implemented by this audit. It requires a narrow OpenSpec change and an
explicit provider/credential choice. The live `STATUS.md` concern remains the
pickup surface.

## Verification gaps

- GitHub publishes no first-run activation SLA, so the cause cannot be narrowed
  to "new schedule propagation" from documentation alone.
- GitHub's public status did not identify a repository-specific scheduler cause;
  the run history establishes symptoms, not GitHub's internal root cause.
- No independent dead-man endpoint or credential was in scope, so absence
  detection remains unimplemented.
