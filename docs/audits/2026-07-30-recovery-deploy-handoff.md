# Recovery-To-Normal Deploy Handoff — 2026-07-30

## Outcome

The public MCP surface is recovered on the previously configured immutable
image. The handoff and partial-target recovery repairs are landed, but current
`main` still fails startup against production-shaped state. Normal deployment
is paused until a bounded pre-rollback diagnostic artifact is landed; the next
single controlled deploy will use it to identify the startup regression.

Update at `2026-07-30T21:01Z`: repaired normal deploy `30581439569`
successfully handed off the recovered generation and installed the target, but
health convergence failed with only stopped `tinyassets-daemon` remaining.
Cleanup fenced that `restart=no` strict subset. Recovery `30582599465` then
failed closed because recovery admitted only empty or exact-five volume
inventories. A fresh public canary returned HTTP 502.

Update at `2026-07-31T05:21Z`: isolated recovery workflow run `30605922404`
restored the public MCP surface after normal deploy `30605692331` failed
current-main startup and its ordinary rollback. Fresh-volume Docker build smoke
run `30606140782` passed on `ba87b1dd`, narrowing the fault to
production-shaped state or environment. The failed candidate's logs were lost
to rollback, so the next repair preserves bounded private startup evidence
before any rollback mutation.

## Production Evidence

- Diagnostic normal deploy run `30578541098` completed its stop-writer
  preflight and target installation but failed health convergence.
- Host evidence showed the exact five stopped containers retained
  `com.docker.compose.project=tinyassets-recovery-691142eb4348935e`.
- `tinyassets-daemon.service` starts the canonical default Compose project
  `tinyassets`. Because the service was inactive, restart did not execute a
  canonical-project teardown before start.
- Docker then refused creation of `/tinyassets-daemon` because the stopped
  recovery-project container still owned that fixed name.
- The workflow failed closed and returned production to `unsafe_fenced`.
- Provenance-bound recovery run
  [30578968815](https://github.com/Jonnyton/TinyAssets/actions/runs/30578968815)
  succeeded at `2026-07-30T20:26:23Z`, including the canonical MCP canary,
  exact-seven surface assertion, and fence finalization.
- Fresh local public-canary verification on 2026-07-30 (Windows host):
  `py scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
  --assert-name TinyAssets --assert-handles` exited `0`.
- Normal deployment
  [30605692331](https://github.com/Jonnyton/TinyAssets/actions/runs/30605692331)
  installed immutable current-main digest
  `38441153394980b49774d1a2469599173e01850b2ee51c958f64eaffc00f953b`
  at revision `098fdd963e73069a98c15c312231dbc84688a75b`, but the daemon did
  not become healthy within 90 seconds. Ordinary rollback then failed and the
  workflow fenced the remaining partial fleet.
- Provenance-bound recovery
  [30605922404](https://github.com/Jonnyton/TinyAssets/actions/runs/30605922404)
  succeeded and restored the previously admitted immutable image.
- Fresh-volume Docker smoke
  [30606140782](https://github.com/Jonnyton/TinyAssets/actions/runs/30606140782)
  passed for current `main` revision `ba87b1dd`, including the local MCP
  canary. This contradicts a universal image/import failure and points to
  production-shaped startup inputs.
- Fresh local public-canary verification at `2026-07-31T05:21Z` (Windows
  host): `python scripts/mcp_public_canary.py --url
  https://tinyassets.io/mcp --assert-name TinyAssets --assert-handles
  --verbose` exited `0`.

## Root Cause

Emergency recovery correctly creates a restart-fenced generation under a
unique Compose project and preserves its exact IDs in durable state.
Finalization restores service boot posture but intentionally does not recreate
those containers under the canonical project. The next normal preflight stops
the recovered generation and overwrites canonical fence state with the new
run's exact old IDs. Before this repair it discarded the prior recovery
project/ID provenance, and `prepare_deploy` only unmasked the service. The
stopped recovery containers therefore survived into canonical Compose start.

## Repair

`preflight` now recognizes recovery provenance only from a prior `restored`
state. Before any host mutation it requires:

- the recorded recovery run to derive the exact recorded project name;
- the recorded IDs to cover exactly the daemon plus four workers;
- current inspected IDs to equal those durable IDs; and
- every current Compose project label to equal that exact recorded project.

It carries the bounded handoff into the new run's write-ahead state.
`prepare_deploy`, after its existing queue, receipt, and stopped-old-ID checks,
requires the same exact five IDs, labels, stopped states, and `restart=no`
policies. It writes removal intent, runs `docker rm` on only those exact IDs
without `-v`, proves the production-volume container inventory empty, records
completion, and only then unmasks the canonical service. After durable intent,
a strict remaining subset is replayable only when every survivor retains its
recorded identity and safety posture, every missing recorded ID is proved
absent, and there are no extra writers. Before intent, partial absence fails.
Substituted, running, restart-enabled, and foreign-project survivors fail.

Ordinary canonical predecessors have no recovery handoff record and keep the
existing systemd lifecycle.

The follow-up recovery repair recognizes only a strict subset of expected
canonical target names whose exact image/revision equals the durable target,
whose Compose project is exactly `tinyassets`, and whose containers are
stopped with `restart=no`. Every missing expected name must be absent across
all container states. It writes observed IDs before `docker rm`, removes
without `-v`, and replays only the remaining recorded subset after an
interruption. Extra, foreign, running, restart-enabled, substituted, and
same-name off-volume states fail before removal.

## Verification

TDD red evidence on 2026-07-30:

```text
5 failed, 2 passed, 90 deselected
```

The failures covered the reproduced no-removal behavior, discarded recovery
provenance, partial/foreign drift, and absent removal-intent replay state.

Green evidence on 2026-07-30 (Windows host):

```text
py -m pytest -q tests/test_retire_cheat_loop_deploy_fence.py
100 passed in 2.71s

py -m ruff check scripts/retire_cheat_loop_deploy_fence.py tests/test_retire_cheat_loop_deploy_fence.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict
Change 'repair-recovery-deploy-handoff' is valid
```

The suite includes a full unsafe-recovery → finalization → next normal
preflight → exact removal path, ordinary canonical preservation, mismatch
before first mutation, partial/foreign/running/restart-policy refusal, and
crash-after-removal replay, including injected strict-subset removal followed
by successful exact-survivor replay.

Independent review of head `01724e33` returned ADAPT: multi-ID `docker rm` is
not transactional, so strict-subset success had no replay path, and the change
needed an explicit sync/archive closeout task. Both findings are addressed in
head `65a12e1c`. Independent exact-head re-review returned APPROVE after fresh
evidence of 100 focused tests, clean Ruff and diff checks, and strict OpenSpec
validation.

Follow-up P0 verification on 2026-07-30 (Windows host):

```text
py -m pytest tests/test_retire_cheat_loop_deploy_fence.py -q
112 passed in 3.81s

py -m ruff check scripts/retire_cheat_loop_deploy_fence.py tests/test_retire_cheat_loop_deploy_fence.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict
Change 'repair-recovery-deploy-handoff' is valid
```

Two independent reviews of head `8486ca53` returned ADAPT because an
empty-inventory replay did not rebind the write-ahead record's
image/revision/project and did not prove every expected container name
globally absent. An existing plan could also encounter a full or substituted
volume fleet and fall through to a different remover. The follow-up binds plan
metadata before inventory branching, requires the observed volume names to
remain a subset of the write-ahead names, and proves all expected names absent
both on empty replay and after exact-ID removal. Five additional regression
cases cover off-volume name substitution, a full replacement fleet, and each
plan-metadata substitution. Exact-head independent re-review is pending.

Twelve new tests cover production-shaped partial-target recovery, write-ahead
replay after interrupted subset removal, and refusal of foreign-project,
running, restart-enabled, foreign-image, and same-name off-volume states.

Failed-candidate diagnostic verification at `2026-07-31T05:21Z` (Windows
host):

```text
python -m pytest tests/test_deploy_prod_workflow.py \
  tests/test_build_image_workflow.py tests/test_release_reconcile_workflow.py -q
127 passed in 22.55s

python -m ruff check tests/test_deploy_prod_workflow.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict
Change 'repair-recovery-deploy-handoff' is valid
```

The diagnostic artifact is emitted before rollback, contains Compose status,
daemon runtime state, and a 128 KiB-bounded tail of the last 200 daemon log
lines, excludes environment inspection, and expires after seven days.

## Release And Rollback

Land only after independent exact-head fail-closed/security review. Build an
immutable image, then run one normal deploy from the currently finalized
recovery generation. Acceptance requires canonical exact-five proof, restored
fence state, and a fresh public MCP canary. On failure, use only the existing
provenance-bound unsafe recovery workflow with the prior admitted stop-writer
image; do not delete containers directly or bypass the fence.
