# Deployed monitoring classification, not full uptime acceptance

Read-only verification on 2026-09-19 around 06:20 UTC used `gh run list
--workflow uptime-canary.yml --limit 12 --json
databaseId,event,status,conclusion,createdAt,headSha,url`, then `gh run view
35426174606 --json event,headSha,createdAt,conclusion,jobs,url` and that run's
`--log`. No account, private workflow, incident or production configuration
was changed.

PR [3880](https://github.com/Jonnyton/TinyAssets/pull/3880) merged at 06:06:43 UTC
as `59cf8843f05be9ecc76d7bb093803481dab6e844`. Exact-head Fable approval and
hosted CI receipts are retained in the PR comments. Local Windows and Linux
monitor cohorts each passed 344 tests with zero skips; required hosted tests
and actionlint passed before merge.

## Automatic deploy-completion observation

[Run 35426174606](https://github.com/Jonnyton/TinyAssets/actions/runs/35426174606)
started at 06:16:49 UTC from `7b406025b8aea8cfbdcb12bd18e92d14d0bb7428`.
Its event is **workflow_run**, not schedule or manual dispatch.

- Handshake, real tool, current executor activity and reserved wiki readback
  returned exit 0. Executor activity reported no active work and a fresh
  coordinator heartbeat; this is not useful-work proof.
- Revert returned exit 5 with the explicit pair `revert_observation=unknown`
  and `revert_reason=legacy_evidence_unavailable`.
- Layer-1 combination reported unknown. `Layer-1 measured red v1` was skipped.
- Layer-2 reported unknown with
  `authorized_rendered_session_unavailable`, without invoking a browser or LLM.
- The alarm sink reported unknown and returned before issue/label queries or
  mutations and paging. Comment/page steps were skipped. Workflow success
  means the classifier ran correctly, not that uptime acceptance is green.

The earlier post-merge run
[35425806368](https://github.com/Jonnyton/TinyAssets/actions/runs/35425806368)
at 06:08:32 UTC is also a deploy-completion `workflow_run`.

## Still open

The latest observed natural `schedule` event was
[35424683040](https://github.com/Jonnyton/TinyAssets/actions/runs/35424683040)
at 05:42:42 UTC, before this merge. No post-merge natural cron proof was
available at this read. The change remains active until that acceptance and
specification sync are complete; do not substitute a manual dispatch.

Authoritative private-free current-engine execution-quality observation and
authorized rendered-user acceptance remain unavailable. Unknown cannot clear
existing incidents, and historical incidents need separate owner disposition.
No failures were induced and no incident closure was attempted.

## Community consumer running from merged source, 08:24 UTC

PR3882 exact head `c1dae68332c677050b45999c1e584d78c00ba47b` has Fable55159
approval (PR comment5740284456, paired with runtime review5740160347).
Required Tests35430169457 completed SUCCESS08:24:10UTC; required job38m46s,
slow job1m27s. It merged as `c9b8ee7e655776eb7f981966d7a83034ed89e315`.

Automatic **push**, not schedule, run
[35431904185](https://github.com/Jonnyton/TinyAssets/actions/runs/35431904185)
checked out that exact source and ran the hosted consumer. Root verified with
`gh run view 35431904185 --log`, parsed its emitted status JSON, and checked
the resulting issue comment at08:30UTC. This proves the Actions-side consumer
is running; it is not a claim that the daemon image contains c9b8ee7e.

- Observation canary: **unknown**, exact run35429679337 attempt1, age50.264min,
  reason required Layer-1 receipt unavailable or ambiguous. Its workflow
  conclusion success was not substituted for measured green.
- Observation incidents: **red**, existing open P0 incident2824. This stage
  legitimately kept overall red/exit2; the watch job's failure is not evidence
  of classifier regression or a newly measured endpoint outage.
- Tier-3 clone smoke: yellow, newer successful clone run35343734963 with older
  unresolved issues. Production/site deploy stages: green from their run metadata.
- The ordinary red sink appended
  [comment5740466974](https://github.com/Jonnyton/TinyAssets/issues/3646#issuecomment-5740466974)
  at08:24:40UTC, containing this run. It did not claim recovery. No operator
  incident mutation, induced failure or forced green was used for acceptance.
- Because overall was red, this live run did NOT exercise the unknown/yellow
  early-return sink. Executed JavaScript fixture tests remain supporting
  evidence for that branch, not substituted live proof.

At08:27UTC, `gh run list --workflow uptime-canary.yml --event schedule --limit 1
--json databaseId,headSha,event,status,conclusion,createdAt` still returned only
the05:42:42UTC pre-fix run35424683040. A fresh natural schedule, positive measured
green/recovery, private-free execution-quality observation and authorized
rendered acceptance remain open. Main specification sync does not archive this
change or close capability9. No redundant daemon deployment was initiated for
this Actions-only change.
