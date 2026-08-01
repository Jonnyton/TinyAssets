## Why

Normal deploy run `30676899240` failed closed before host mutation because
preflight rejected a preliminary `/proc` writer-process candidate without the
fresh Docker-ownership reconciliation already used by fleet observation. A
container process created between the first Docker PID snapshot and the process
scan can therefore be misclassified as a stray host writer and indefinitely
block safe immutable releases.

## What Changes

- Reconcile every preliminary preflight process candidate against a fresh
  Docker PID snapshot for the exact inspected container identities.
- Continue to reject any candidate that still exists and is not owned by those
  exact containers; no command-line, environment value, or process detail is
  published on refusal.
- Prove both the container-process race and a genuine host-writer refusal with
  focused tests before another production deploy.
- Record one successful normal-fence deployment with exact fleet, canary,
  cleanup, and terminal-receipt evidence before resuming rendered OAuth
  acceptance.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: Preflight process-risk admission uses a fresh
  exact-container ownership reconciliation before classifying a candidate as a
  stray writer, while genuine unowned writers remain fail-closed.

## Impact

- Runtime fence: `scripts/retire_cheat_loop_deploy_fence.py`
- Verification: `tests/test_retire_cheat_loop_deploy_fence.py`
- Production release: one new immutable image and normal `deploy-prod` run
- Public MCP and OAuth token-acceptance behavior are unchanged.
