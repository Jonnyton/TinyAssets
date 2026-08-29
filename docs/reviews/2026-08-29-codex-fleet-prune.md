# Codex review record — deleting the host-run cloud-worker fleet

PRs #2677 (core) and #2678 (ops tail, split for the scope guard's 8-file cap). Change:
`openspec/changes/user-owned-automations` tasks 1.1 (repo half) + 1.2. Dispatch:
`python scripts/peer_agent.py codex --prompt-file <brief>` on Codex's own budget, asked to
REFUTE with `AGREE` / `DISAGREE_EVIDENCE` / `DISAGREE_CONCERN`. Three dispatches; the first was
killed with the Claude Code session crash and returned nothing.

## Round 1 (dispatch 2) — ADAPT, six points

| # | Verdict | Finding | Action |
|---|---|---|---|
| 1 | DISAGREE_EVIDENCE | `deploy/ship-logs.sh` REQUIRED the four deleted worker containers and exited 1 when any was missing; `vector.yaml` classified a `worker` role; P0 triage now writes `.pause` but the assigned-queue consumer never checked it; `DEPLOY.md` / `daemon-liveness-watchdog.md` stale. | All fixed. ship-logs/vector/DEPLOY.md moved to #2678 (scope cap). Consumer honours `.pause` (skips pump + claim, records `paused`), mutation-checked. |
| 2 | AGREE | Relocated helper bodies behaviourally identical; no importer of the old module path. | — |
| 3 | AGREE | `daemon_registry` `"cloud-droplet"` exclusion is compatibility, not an actor. | — |
| 4 | AGREE | `docker compose config --services` → daemon, cloudflared, logs on the repo file and the recovery overlay. | Droplet verified separately: same three, no worker service defined. |
| 5 | DISAGREE_EVIDENCE | Spec sync must land in this PR (AGENTS.md same-lane rule). | Supervisor + healthcheck requirements REMOVED; singleton/idle-cycle MODIFIED; the four reconciliation requirements stay until task 3.3 deletes the operator CLI; the ADDED consumer requirement is not synced ahead of task 3.2. |
| 6 | DISAGREE_EVIDENCE | Deleting all of `tests/test_soul_loop_dispatch.py` was unjustified — most of it tests the surviving user-owned loop. | Restored minus the four `cloud_worker` cases. |

## Round 2 (dispatch 3) — ADAPT, two points

| # | Verdict | Finding | Action |
|---|---|---|---|
| 1 | AGREE | No runtime reference to a retired container name remains in `deploy/` or `.github/`. | — |
| 2 | DISAGREE_EVIDENCE | Pausing skipped heartbeat publication; `deploy/daemon-watchdog.sh:115` restarts the daemon on a stale beat every 2 min and a restart preserves `.pause` — the P0 repair would have become a restart loop. | Fixed: a paused universe still heartbeats (liveness ≠ activity); only pump and claim are skipped. Test asserts the beat and is mutation-checked. |
| 3 | AGREE | `verify-request-hmac-rotation-fleet.sh` has no live caller. | Deleted in #2678. |
| 4 | DISAGREE_EVIDENCE | Spec Purpose still advertised the supervisor/healthcheck/fleet idle-cycle; the delta's MODIFIED block omitted the two surviving idle-cycle scenarios. | Both fixed. |
| 5 | AGREE | Restored test file references nothing deleted. Named the order-dependence cache: `tinyassets.runs.BranchDefinition` is imported module-globally (`runs.py:40`) while `_FakeBranch` is installed. | Out of scope; recorded below. |

## Reported to the founder, not fixed here

- `tests/test_soul_loop_dispatch.py` before `tests/test_assigned_queue_consumer_live_worker.py`
  in one pytest invocation fails the latter (`_FakeBranch` retained through the module-global
  `BranchDefinition` import in `tinyassets/runs.py:40`). Pre-exists on `main`; CI's alphabetical
  order never hits it. A one-line fix is to patch `tinyassets.runs.BranchDefinition` in
  `_patch_common` as well.
- `tests/test_deploy_prod_workflow.py::test_request_hmac_rotation_requires_deployed_corrected_boundary`
  is red on `main` (its deploy step is gone). Untouched.
- `python -m tinyassets.runtime_reconcile stale-fleet` and its four spec requirements survive
  until task 3.3 retires the old-principal rows explicitly.
