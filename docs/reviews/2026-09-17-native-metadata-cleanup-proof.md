# Native metadata launcher cleanup

Item3 of the owner-approved capability queue, existing select-agent-models lane.
Scope: generic native JSON-RPC subprocess lifecycle. No new public API, model
pins, grants, credentials, preference writes or private workflow edits.

## Diagnosis, September17 2026

Live e0921fb2 owned model options:32.422s, native30.087s failure/HTTP2.18s.
Phase-only supporting diagnostic: initialize0.662s, model/list1.093s, cleanup
failure30.266s. Isolated process-group cleanup experiment:8models in1.132s.
These are service diagnostics, not a deployed fix or user acceptance.

Official source fetched September17:
[Codex App Server](https://learn.chatgpt.com/docs/app-server), protocol,
initialization and model/list sections. Existing wire registration matches it;
no provider model catalogue fallback is needed.

## Independent shape review

Claude Fable via peer_agent.py, read-only,600-second budget, terminal exit0 in
437s. Artifact output/native-metadata-shape-review.md. VERDICT: ADAPT. Reviewer
independently reproduced launcher-only kill hanging and process-group kill
completing immediately on WSL; also demonstrated inherited flock ownership.

Applied: transport-owned session isolation, close stdin, group cleanup, bounded
reap/pipe closure, propagation of cancellation, real inherited-pipe/lock tests.
Clarifications requiring exact-head review:

- Native metadata receives a per-invocation owned credential snapshot through
  base.py, not host /data/.codex. Review's claim of a shared host-wide lock in
  this path is not established. No broad process kill is authorized by it.
- Cleanup must also target a group whose launcher has already exited; merely
  checking returncode misses that tested case. Target the original group ID,
  never getpgid on a reaped PID. The registered executor is trusted not to escape
  its session. Deliberately escaped descendants and theoretical group-ID reuse
  are not claimed solved by this patch.
- Immediate termination retains the prior shutdown policy, but covers children.
  Its auth/config writes are ephemeral; the source custody record is untouched.

## Verification before exact-head review

Linux/Python3.11, disposable container of deployed image956abf6b: no network,
no host volumes or credentials, read-only root, dropped capabilities,768MiB/1CPU/
128PID ceilings. Working-tree tracked source + focused tests and public pytest
wheels copied to tmpfs; pytest8.4.2/packaging25.0. Command:
`python output/run-native-linux-check.py`.

- Red against base transport:5 new launcher cases failed,34 existing passed.
- First green transport:39 passed,2.76s; includes launcher exited, success,
  malformed response, cancellation, timeout, and lock release.
- Windows first cohort:75passed/5POSIX skips,13.18s. Windows is not the oracle.
- Final expanded Linux checks:41passed,2.73s. Windows:75passed/7POSIX skips,
  11.24s. Ruff, mirror build/import probe, diff check and OpenSpec validation pass.
- Exact-head review receipt follows outside this commit.

Local `scripts/linux_oracle.py` could not start: Docker Desktop crashed on its
dockerInference socket September17~21:12UTC. The disposable Linux check above
uses the working tree and real POSIX semantics without modifying production.
Hosted required checks remain mandatory. No gate or quarantine edits.

## Release and rollback

Not yet deployed or accepted. After exact-head approval and required checks:
build immutable image, deploy, protected deployed-SHA and public canary, then
ordinary app picker discovery/selection and actual response. Preserve saved
Automatic unless the user explicitly changes it; test override is tab-local.
Rollback: revert this patch via reviewed release if metadata discovery or
process cleanup regresses. No storage migration or user-data rollback needed.
Full item3 remains open for Codex answer identity and default/fallback acceptance.
