# Deploy no longer delivers subscription auth, so rotation and rebuild are both dead

**Filed:** 2026-08-27
**Severity:** P1 — latent on the current droplet, fatal on the path it exists for
**Verified:** 2026-08-27 against `814b4f06`

## The finding

No workflow in `.github/workflows/` references
`TINYASSETS_CODEX_AUTH_JSON_B64` or `TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64`.
Not one:

```
$ grep -rn "CODEX_AUTH_JSON_B64\|CLAUDE_CREDENTIALS_JSON_B64" .github/workflows/
(no output)
```

`deploy-prod.yml` passes exactly four secrets — `DO_DROPLET_HOST`,
`DO_SSH_USER`, `DO_SSH_KEY`, `GITHUB_TOKEN` — and nothing else.

**The product still consumes both.** `deploy/docker-entrypoint.sh:117` decodes
`TINYASSETS_CODEX_AUTH_JSON_B64` into `~/.codex/auth.json` on container start,
and `:153` does the same for `TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64`. The
entrypoint states the consequence itself at `:169`: *"no claude credentials
present … claude-code writer will be unauthenticated"*.

**And the docs still instruct the operator to rely on it.**
`deploy/DEPLOY.md:203` says to *"keep `TINYASSETS_CODEX_AUTH_JSON_B64` rotated
so a fresh-droplet [rebuild works]"*. That instruction is now false. Following
it produces no effect, which is worse than no instruction.

## Where it went

Dropped by PR #2442 (`5aeb64da`), the rewrite that took `deploy-prod.yml` from
2,762 lines to 134. The pre-rewrite workflow delivered the bundle explicitly:

```yaml
# 5aeb64da^:.github/workflows/deploy-prod.yml
HAS_CODEX_AUTH_BUNDLE: ${{ secrets.TINYASSETS_CODEX_AUTH_JSON_B64 != '' }}   # :328
...
printf '%s' "${TINYASSETS_CODEX_AUTH_JSON_B64}" | ssh … \                     # :1252
    "sudo bash /tmp/install-tinyassets-env.sh set TINYASSETS_CODEX_AUTH_JSON_B64"
...
echo "::warning::TINYASSETS_CODEX_AUTH_JSON_B64 is not visible to deploy;      # :1259
      leaving any existing droplet subscription auth untouched."
```

It even warned when the secret was invisible. Now there is no delivery and no
warning.

## Why the obvious "it moved" answers are wrong

Both were checked, because the same review pattern that found this also found a
sibling that genuinely *did* relocate:

- **`apply-daemon-env.yml` is not it.** Its own header: an *"EXPLICIT key→value
  allowlist, not a regex. TINYASSETS_IMAGE and every secret/deploy-critical key
  are NOT settable here — this is a feature-flag surface"*. It also passes only
  the three `DO_*` secrets, and it is `workflow_dispatch`-only.
- **`deploy_fail_safe.sh` is not it.** It uses `install-tinyassets-env.sh` as
  `ENV_HELPER` (`:52`) — the same helper the old workflow used — but deploy
  hands it no secret values to set.
- **Contrast, and the reason this is not uniform rot:**
  `TINYASSETS_GITHUB_PR_CAPABILITIES` **did** relocate. It is delivered by
  `scripts/github-app-token-refresher.py:112` through the same env helper, on a
  systemd timer installed by `install-host-services.yml:364-409`. Its
  deploy-workflow assertion is genuinely stale. The two auth bundles have no
  such path.

## Impact

Latent on the running droplet: the values were written to the persistent host
env file by a pre-#2442 deploy and survive container recreate, which is why
nothing is visibly broken. Two paths are dead anyway, and they are the paths
the variables exist for:

1. **Rotation.** Re-authenticating the Codex or Claude subscription and
   updating the GitHub secret changes nothing in production. The droplet keeps
   the old bundle until it expires, and then the writer is unauthenticated with
   no deploy-time route to fix it.
2. **Fresh-droplet rebuild.** A rebuilt droplet — the zero-hosts-online disaster
   recovery path the Forever Rule promises — comes up with neither bundle. Per
   the entrypoint's own warning, the claude writer is unauthenticated.

**Not verified from this session:** whether the live droplet's
`/etc/tinyassets/env` currently holds either value. That needs the host and was
not run. Confirming it is
`ssh … 'sudo grep -c CODEX_AUTH_JSON_B64 /etc/tinyassets/env'`; a `0` promotes
this from latent to live.

## How it was found

Triaging the 81 failing assertions in `tests/test_deploy_prod_workflow.py`
(see [full-tests-permanently-red](2026-08-27-full-tests-permanently-red.md)).
That file's remaining failures were expected to be uniformly stale — assertions
against a retired design. Four of them assert `TINYASSETS_CODEX_AUTH_JSON_B64`
reaches the droplet, and they are correct. This is the **fourth** real drop
recovered from #2442, after the codex-auth volume step and the
`production-host-mutation` concurrency group (both fixed in #2584) and the
compose sync ([deploy-drops-compose-sync](2026-08-27-deploy-drops-compose-sync.md)).

The lesson is the one already recorded on that file: *a red test suite hides
real findings among stale ones, and the only way to tell them apart is
one at a time.*

## Resolving this

Restore delivery for both bundles in `deploy-prod.yml`, through
`install-tinyassets-env.sh` as before, including the `::warning::` when the
secret is not visible to deploy — the warning is what makes a missing secret
diagnosable instead of silent. Then delete the four assertions' *step-name*
expectations while keeping their *capability* expectations, retargeted at the
current workflow.

Do not resolve by deleting the assertions. They are the only thing that noticed.
