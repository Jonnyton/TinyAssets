# The deploy no longer ships `deploy/compose.yml` to the droplet

**Filed:** 2026-08-27
**Severity:** P1 — every compose-level change is silently inert in production

## The finding

`.github/workflows/deploy-prod.yml` used to carry a **`Sync runtime deploy
files`** step that `scp`'d `deploy/compose.yml`, `deploy/vector.yaml`,
`deploy/vector-betterstack.yaml`, `deploy/vector-entrypoint.sh` and the systemd
unit to the droplet and installed them at `/opt/tinyassets/`.

PR #2442 (`5aeb64da`) rewrote the workflow from 2,762 lines to 134 and dropped
it. The current workflow `scp`s four files:

| Line | Shipped |
|---|---|
| 169 | `deploy/tinyassets-daemon.service` |
| 277 | the fail-safe deploy script |
| 334 | `release-state.json` |
| 277 | `deploy/install-tinyassets-env.sh` |

`deploy/compose.yml` is not among them, and neither are the vector configs.

## Why it matters

**Editing `deploy/compose.yml` in this repo has no effect on production.** The
droplet keeps whatever copy it had when the sync step was last alive. This is
the already-recorded symptom "a compose.yml env flag is INERT after a normal
deploy" — the effect was known; this is the cause.

Everything compose owns is affected: service definitions, `CODEX_HOME`,
`TINYASSETS_DATA_DIR`, every feature flag set as a compose env, and the vector
log pipeline.

## How it was found

Triaging the 88 failures in `tests/test_deploy_prod_workflow.py`, which assert
the pre-#2442 workflow. Most are stale — renamed steps (`Rollback on failure`
-> `Roll back if the public canary is red`, `Capture previous image tag` ->
`Capture current image`) or a superseded receipt schema (`terminal_receipt_result`
-> release_state_version 2 with `outcome`/`terminal_at`). Two were not stale:

1. `Prepare codex auth persistent volume` — a genuine drop, **restored** in this
   same change. It also repairs `/data/.auth.db` ownership, without which
   "every public MCP initialize request fails in OptionalOAuthProvider with
   sqlite3 unable to open database file".
2. This one.

## Why it is not fixed here

Restoring the sync is not a straight revert. The droplet's live
`/opt/tinyassets/compose.yml` has been the sole source of truth since
`5aeb64da` landed on 2026-08-20, while the repo copy drifted unvalidated. Installing the repo copy over it on the
next deploy would converge production onto an unverified file — and this repo
has already taken a 502 from exactly that class of mistake (a partial `-f`
under an existing `-p` destroying omitted services).

**What resolving this needs, in order:**

1. Read the live `/opt/tinyassets/compose.yml` off the droplet (host action —
   no SSH key in the agent environment).
2. Diff it against `deploy/compose.yml` in this repo. Every difference is
   either drift to discard or live configuration the repo never captured.
3. Reconcile the repo copy to be a superset of what production needs.
4. Only then restore the `Sync runtime deploy files` step.

Step 1 is the blocker and is a host action. Until it is done, treat
`deploy/compose.yml` as documentation, not as deployed configuration.

## Also dropped by #2442, deliberately left alone

`Scrub stale cloud env overrides` deleted a fixed list of legacy `WORKFLOW_*`
and `TINYASSETS_*` env vars from the droplet's shared env and asserted
`TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY` absent. It is destructive on the
droplet and its absence has no observed symptom, so it is recorded here rather
than restored.
