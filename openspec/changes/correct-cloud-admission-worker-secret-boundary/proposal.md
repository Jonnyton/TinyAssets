## Why

PR #2178 merged and automatically deployed a production compose shape that gives the daemon's request/admission HMAC minting key to every legacy cloud worker. Those workers supervise an in-process graph executor whose approved source nodes have full Python builtins, so a node can bypass the substring denylist and read the server key. The deploy installed the key, synced the unsafe compose file, and started the worker fleet; the key therefore must be treated as exposed and rotated after the boundary is corrected.

## What Changes

- Make the request/admission HMAC file daemon-only; legacy graph workers receive no minting key.
- Add a deployment regression that exercises the worker environment boundary and proves the key is absent, including after compose inheritance/merge.
- Add an explicit manual-only rotation path and rotate the exposed production key during the corrective cutover.
- Make protected-stdin secret installation remove its plaintext temporary file on normal exit, error, and termination signals.
- Include every production worker in the offsite log archive and correct stale service/archive identities in the operator runbook.
- Keep custom-agent execution dark and prohibit production redeploy until exact-head security review passes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: Require least-privilege production secret scope, interruption-safe protected-stdin custody, and complete worker log retention for the deployed daemon/worker fleet.

## Impact

- Production compose and deploy-secret custody: `deploy/compose.yml`, `deploy/install-tinyassets-env.sh`, `.github/workflows/deploy-prod.yml`.
- Operational evidence and retention: `deploy/ship-logs.sh`, `docs/ops/log-aggregation-runbook.md`.
- Focused deploy, installer, and logging regressions.
- No MCP handle, storage shape, agent definition, invocation record, provider route, or live activation behavior changes.
