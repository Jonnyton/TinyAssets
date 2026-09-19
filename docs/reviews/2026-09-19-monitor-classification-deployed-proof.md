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
