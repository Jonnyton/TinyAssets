# Community watch typed-observation follow-through

September 19, 2026 UTC. Internal monitoring-consumer repair, not a scheduler,
new status endpoint, tenant authority or incident cleanup. Existing Actions
metadata supplies the result; no logs or new content artifacts are parsed.

## Reproduced behavior and minimum repair

`community_loop_watch.workflow_stage` accepted fresh whole-workflow success as
green. Uptime run [35426174606](https://github.com/Jonnyton/TinyAssets/actions/runs/35426174606)
is a concrete counterexample: workflow_run/classifier success with unavailable
Layer-1 evidence. The existing follow-up sink also recovered on any non-red
overall result, including yellow. This source behavior was tested, not inferred
from a current issue's existence; no live issue was queried for mutation or closed.

The producer adds a positive measured-green step beside its existing measured
red step. This is the minimum extra receipt because skipped red cannot tell
unknown from green. The consumer binds exact production repository/path/branch,
head/run/attempt, job completion/freshness, uniqueness and final run re-read.
Missing or conflicting evidence is unknown; explicit legacy red stays usable.
Other existing red stages retain priority. Literal red/green alone reach the
sink's existing actions; unknown/yellow return before label, issue or dispatch
calls. Generic deploy stages and permissions remain unchanged.

The existing 90-minute stale-monitor alarm remains a missing-monitor signal,
explicitly distinguished from a measured endpoint failure. The separate Uptime
prior-red receipt limit remains 30 minutes, unchanged. Full rendered and useful
execution-quality coverage remains unavailable. No cadence promise is added.

## Executed checks

Red first, Windows Python 3.14, before runtime/workflow edits:

```text
python -m pytest -q tests/test_community_loop_typed_observation.py --tb=no
```

**27 failed, 2 passed.** The real alarm JavaScript red/green controls passed;
unknown/yellow/empty recovery and receipt-boundary cases failed. Further
malformed-field, source, legacy-red and read-failure cases were added afterward.

Final focused Windows and canonical Linux selection each report **136 passed,
one known failure, zero skips**:

```text
python -m pytest -q tests/test_community_loop_typed_observation.py tests/test_community_loop_watch.py tests/test_community_loop_watch_workflow.py tests/test_uptime_canary_workflow.py tests/test_uptime_observations.py tests/test_uptime_canary_concurrency.py tests/test_revert_loop_canary.py --tb=short
```

Linux command uses the existing native WSL Docker engine and working-tree oracle:

```powershell
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Users/Jonathan/.codex/worktrees/monitor-classification-closeout/TinyAssets && GIT_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git/worktrees/TinyAssets51 GIT_COMMON_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git GIT_WORK_TREE=/mnt/c/Users/Jonathan/.codex/worktrees/monitor-classification-closeout/TinyAssets python3 scripts/linux_oracle.py -- -q tests/test_community_loop_typed_observation.py tests/test_community_loop_watch.py tests/test_community_loop_watch_workflow.py tests/test_uptime_canary_workflow.py tests/test_uptime_observations.py tests/test_uptime_canary_concurrency.py tests/test_revert_loop_canary.py'
```

Linux Python3.11.16/git2.47.3/bwrap0.12.0; oracle exited1 for the known assertion,
not a fully green suite. `test_alarm_sink_dispatches_only_stale_uptime_canary_workflow`
expects obsolete `createTinyAssetsDispatch`, and was already quarantined at
`.github/known-failing-tests.txt:41`. Its original assertion also fails in the
pinned baseline checkout1bd4b4f4; that workflow/test are byte-identical between
that baseline and branch base7b406025. No ledger change or weakened assertion.

Ruff, whitespace and strict OpenSpec checks pass. Local actionlint is absent;
hosted actionlint is still required, not claimed passed. A read-only API-shaped
check of run35426174606 at approximately07:00UTC with the new reader returned
unknown, without incident actions or provider invocation. That is supporting
consumer proof, not deployed follow-through or natural cron acceptance.

Independent exact-head review, hosted CI, deployment and a new automatic
consumer result remain pending. The natural-cron cadence concern and broader
execution-quality/rendered acceptance remain open after this bounded repair.
