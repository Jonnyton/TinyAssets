# The global subscription-auth seed is a dead path the docs still promise

**Filed:** 2026-08-27
**Severity:** P2 — no live user impact; a false runbook and stale code gates
**Verified:** 2026-08-27 against `814b4f06`
**Cross-family review:** Codex, `docs/reviews/2026-08-27-codex-auth-sync-refutation.md`
— **ADAPT**, and it inverted the fix. See *What review changed*.

## The finding

No workflow in `.github/workflows/` references
`TINYASSETS_CODEX_AUTH_JSON_B64` or `TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64`:

```
$ grep -rn "CODEX_AUTH_JSON_B64\|CLAUDE_CREDENTIALS_JSON_B64" .github/workflows/
(no output)
```

`deploy-prod.yml` exposes only the droplet coordinates (`:68-70`), `GITHUB_TOKEN`
for image resolution (`:85-87`) and the SSH key (`:151-154`). It stages the env
helper but passes only `IMAGE_REF` (`:288-299`), and the fail-safe's sole setter
writes `TINYASSETS_IMAGE` (`deploy/deploy_fail_safe.sh:116`). Before #2442,
delivery was explicit at `5aeb64da^:.github/workflows/deploy-prod.yml:1250-1259`
and `:1282-1288`; the rewrite removed it, along with the preferred global Claude
token path at `:1277-1281`.

Both are still consumed by `deploy/docker-entrypoint.sh:117-132` and `:153-171`,
`deploy/tinyassets-env.template:121,138` still lists them, and
`deploy/DEPLOY.md:203` still tells the operator to keep the codex secret rotated.

## What review changed

**I filed this as a P1 deploy regression and proposed restoring delivery. That
was wrong on three of four points**, and the correct fix is the opposite one.

**1. The variables are vestigial for the user-serving path.** User subscription
material enters an owner-scoped per-universe vault (`tinyassets/api/llm_deposit.py:178-192`);
Codex materialization reads and rotates that bundle independently of the global
seed (`credential_vault.py:1827-1853`); universe-scoped subprocesses start from
an isolated environment and overlay only that universe's credential
(`providers/base.py:568-578`, `:626-654`). The as-built requirement is explicit
that a universe must never borrow ambient host credentials
(`openspec/specs/provider-routing/spec.md:22-33`). The Compose worker
definitions that advertise shared global auth (`deploy/compose.yml:182-225`) are
not started — the deploy runs `daemon cloudflared logs` only.

**Restoring the secrets would mask a stale gate rather than fix anything.**
`cloud_worker.py:1801-1830` checks process-global auth *first*, contradicting its
own documentation at `:571-578`, and only then checks the universe credential
(`:1832-1856`). `get_status` reads global `CODEX_HOME` the same way
(`api/status.py:1054-1077`). Feeding those a bundle hides the bug.

**2. Rotation through this variable was never live.** The entrypoint
deliberately preserves an existing credential file — `docker-entrypoint.sh:101-104`,
`:129-130` for Codex and `:153-165` for Claude. The GitHub secret was only ever a
**missing-file/recovery seed**, so "rotation is inert" was wrong: it was never
the rotation path.

**3. Disaster recovery does not depend on it either.** Full backups archive the
whole data volume including `.codex`, `.claude` and per-universe vault material
(`deploy/backup.sh:161-169`), and restore reinstates it (`backup-restore.sh:253-255`).
Only a genuinely bare bootstrap gets empty template values
(`deploy/hetzner-bootstrap.sh:212-217`).

**So the accurate finding is a dead legacy seed path plus documentation that
promises it works.** That is still worth fixing — a runbook instructing an
operator to do something inert is worse than silence — but it is not a deploy
regression, and the fix is removal, not restoration.

## Resolving this

Per the review's ADAPT verdict, and explicitly **not** by re-adding the secrets:

1. Remove the production entrypoint / template / runbook contract for both
   variables (`docker-entrypoint.sh:117-132,153-171`,
   `tinyassets-env.template:121,138`, `DEPLOY.md:203`,
   `docs/reference/environment-variables.md`).
2. Change the worker quarantine gate and `get_status` to evaluate the selected
   universe's vault credential instead of process-global auth
   (`cloud_worker.py:1801-1830`, `api/status.py:1054-1077`).
3. Remove or separately document host-local global auth — host-local, no-universe
   calls deliberately retain ambient authority (`providers/base.py:568-578`), so
   generic self-host support may need its own explicit credential-mount path.
4. Add a fresh-host test proving deposited per-universe Codex/Claude credentials
   work with **no** ambient bundle present.

Steps 2 and 4 are the ones with real value; step 1 is what stops the docs lying.

## Related, found by the same review

`TINYASSETS_GITHUB_PR_CAPABILITIES` — which I had recorded as a clean
relocation — **is relocated but broken**. Filed as
[github-app-token-refresh-never-reaches-the-daemon](2026-08-27-github-app-token-refresh-never-reaches-daemon.md).

## How it was found

Triaging the 81 failing assertions in `tests/test_deploy_prod_workflow.py`
individually rather than assuming uniform staleness — see
[full-tests-permanently-red](2026-08-27-full-tests-permanently-red.md).
