# Recovery-To-Normal Deploy Handoff — 2026-07-30

## Outcome

The public MCP surface is recovered on the previously configured immutable
image. Normal deployment remains paused until the reviewed handoff repair is
landed and deployed.

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

## Release And Rollback

Land only after independent exact-head fail-closed/security review. Build an
immutable image, then run one normal deploy from the currently finalized
recovery generation. Acceptance requires canonical exact-five proof, restored
fence state, and a fresh public MCP canary. On failure, use only the existing
provenance-bound unsafe recovery workflow with the prior admitted stop-writer
image; do not delete containers directly or bypass the fence.
