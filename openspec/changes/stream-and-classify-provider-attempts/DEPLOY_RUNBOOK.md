# Durable deploy runbook — Slice 1 (and the Phase-2 serving fixes)

Prepared 2026-08-19 from a read-only prod inventory (droplet `workflow-droplet`).
This is the founder's deploy decision; steps below are staged, not executed.

## Live prod state (as inventoried)
- Running image: `ghcr.io/jonnyton/tinyassets-daemon@sha256:89f3127949a8…` = tag
  `c5d419442fee` ("harden(engine): apply Codex re-review fixes"), deployed
  2026-08-19T03:40 via a MANUAL fail-safe swap (`deploy-prod.yml` is disabled).
- `release-state.json` git_sha: `c5d419442fee`.
- Prod is on the **durable-agent-push lineage**, NOT `main`.

## Divergence analysis — main is a clean content-FORWARD of prod
`git diff origin/main..c5d419442fee` touches only `provider_assignment.py`,
`provider_serving_binding.py`, `universe_server.py`, `providers/router.py`, and
tests — all cases where **main is AHEAD** (it carries #2438/#2439 served-budget
hardening + the held-by-default claude-serving gate that prod lacks). The engine
files (`engine_mcp_http.py`, `engine_mcp_server.py`) are **identical** → main
already contains prod's engine hardening. **Deploying a main-based image does NOT
regress prod's engine work; it only adds the budget hardening + Slice 1.**
(The 4 "commits not on main" are pre-squash originals; #2434 squash-merged their
tree, so by CONTENT main ⊇ prod.)

## HARD PRE-DEPLOY GATE (or claude serving breaks)
`TINYASSETS_ALLOW_CLAUDE_SERVING` is currently **absent** from
`/etc/tinyassets/env`. Prod serves claude today only because image
`c5d419442fee` predates the held-by-default gate. Any main-based image HOLDS
claude serving unless this is set. **Before swapping the image:**
```
# on workflow-droplet, append to /etc/tinyassets/env:
TINYASSETS_ALLOW_CLAUDE_SERVING=1
```
(Also confirm `TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES=u-tiny` stays set — present.)

## Deploy steps (durable — baked image, survives recreate)
1. Land Slice 1 to `main` (own PR, Codex-approved, CI green). Slice 1 branches off
   fb2574fa so the deployed image is `main + Slice 1` — a superset of prod.
2. Build the image off the merged main sha:
   `gh workflow run build-image.yml --ref main` (workflow_dispatch builds without
   auto-deploy). Capture the resulting `ghcr.io/...@sha256:<digest>`.
3. Set the env gate (above) on the droplet.
4. Swap the running container to the new digest (compose up -d with the pinned
   digest under project `tinyassets`), health-gate, and update
   `/data/release-state.json` git_sha to the new main sha (a manual swap does NOT
   auto-update it — `deploy-prod.yml`/`release-reconcile.yml` would).
5. Record rollback target = the current `c5d419442fee` digest before swapping.

## Post-deploy verification (Hard Rule 11 + the actual fix)
- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` green;
  `--assert-handles` green (handle set unchanged).
- Confirm `get_status` release_state.git_sha == the new main sha (merged ≠ deployed).
- **The real proof:** a substantive multi-message Slack back-and-forth completes
  without the "at model's capacity" notice (the bug this slice fixes). Watch
  `docker logs tinyassets-daemon` for `provider_idle_timeout`/`interactive_deadline`
  classes replacing the old `claude-code timed out → cooldown 120s → exhausted`.
- Confirm claude serving is live (not held): `provider_auth.writers.claude-code = ok`
  AND a real served reply lands.

## Note on the durability root cause (for the founder)
Prod keeps diverging from main because it receives branch-build + hot-patch
deploys that don't merge back cleanly. The durable fix is to always deploy a
**merged-main** image and keep `release-state.json` truthful, so `main` == what's
running. This slice's deploy is the chance to re-converge prod onto main.
