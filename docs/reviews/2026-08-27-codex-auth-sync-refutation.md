Reviewed the exact `814b4f06` tree and `5aeb64da^`.

1. **AGREE**

No workflow delivers either bundle to production.

- `deploy-prod.yml` exposes only the droplet coordinates globally and `GITHUB_TOKEN` for image resolution: `.github/workflows/deploy-prod.yml:68-70`, `:85-87`. The SSH key appears only at `:151-154`.
- Deployment stages the env helper but passes only `IMAGE_REF`: `.github/workflows/deploy-prod.yml:288-299`. The fail-safe’s sole setter writes `TINYASSETS_IMAGE`: `deploy/deploy_fail_safe.sh:116`.
- `apply-daemon-env.yml` explicitly refuses keys outside its feature-flag allowlist: `.github/workflows/apply-daemon-env.yml:80-90`.
- P0 rollback writes only `TINYASSETS_IMAGE`: `.github/workflows/p0-outage-triage.yml:261`.
- Host-service installation writes only `BACKUP_DEST`: `.github/workflows/install-host-services.yml:315-329`.
- The auth keepalives merely exercise existing files: `.github/workflows/codex-auth-keepalive.yml:43-48`, `.github/workflows/claude-auth-keepalive.yml:42-47`.
- Before #2442, delivery was explicit at `5aeb64da^:.github/workflows/deploy-prod.yml:1250-1259` and `:1282-1288`. The rewrite removed it. It also removed the preferred global Claude token path at `:1277-1281`.

Minor precision: `install-tinyassets-env.sh` is not literally the only code capable of writing the env file. Bootstrap copies an empty template at `deploy/hetzner-bootstrap.sh:212-217`, and the isolated DR drill directly rewrites only `TINYASSETS_IMAGE` at `.github/workflows/dr-drill.yml:671-695`. Neither delivers auth.

2. **DISAGREE_EVIDENCE**

The entrypoint consumes both variables, but they are vestigial for the production user-serving credential path—not unreachable code everywhere.

- Literal consumption is confirmed at `deploy/docker-entrypoint.sh:117-132` and `:153-171`.
- User subscription material now enters an owner-scoped per-universe vault: `tinyassets/api/llm_deposit.py:1-7`, `:178-192`.
- Codex materialization reads and rotates the vault bundle independently of the global seed: `tinyassets/credential_vault.py:1827-1853`.
- Universe-scoped subprocesses start from an isolated environment and overlay only that universe’s vault credential: `tinyassets/providers/base.py:568-578`, `:626-654`.
- The as-built requirement says a universe must never borrow ambient host credentials or platform compute: `openspec/specs/provider-routing/spec.md:22-33`.
- Production deployment starts only `daemon`, `cloudflared`, and `logs`: `deploy/deploy_fail_safe.sh:152`; `deploy/tinyassets-daemon.service:79`. The legacy Compose worker definitions that advertise shared global auth at `deploy/compose.yml:182-225` are not started by the deployed command.

The remaining global-auth dependency is stale pre-vault logic: the worker checks process-global auth first at `tinyassets/cloud_worker.py:1801-1830`, even though its own documentation says universe children do not consult it at `:571-578`, and only afterward checks the universe credential at `:1832-1856`. `get_status` likewise reads global `CODEX_HOME` at `tinyassets/api/status.py:1054-1077`.

Restoring global delivery would mask those stale gates and conflict with the requester-owned-compute contract. Host-local, no-universe calls deliberately retain ambient authority at `tinyassets/providers/base.py:568-578`, so generic self-host support may need a separate explicit credential-mount path.

3. **DISAGREE_EVIDENCE**

Persistence is real, but the claimed rotation and rebuild impact is overstated.

- The helper defaults to persistent `/etc/tinyassets/env`: `deploy/install-tinyassets-env.sh:68`.
- Its setter preserves unrelated lines and atomically replaces/appends the selected key: `deploy/install-tinyassets-env.sh:443-464`.
- Compose reloads that host file when recreating a container and mounts the durable volume: `deploy/compose.yml:106-112`. Therefore pre-#2442 values survive ordinary container recreation.
- However, updating either JSON bundle was never live rotation: the entrypoint intentionally preserves an existing Codex file at `deploy/docker-entrypoint.sh:101-104`, `:129-130`, and an existing Claude file at `:153-165`. The GitHub secret was only a missing-file/recovery seed.
- Official full backups archive the entire data volume, including `.codex`, `.claude`, and per-universe vault material: `deploy/backup.sh:161-169`. Restore reinstates the archive into the new volume at `deploy/backup-restore.sh:253-255`. A DR rebuild can therefore recover materialized credentials without either env bundle.
- A genuinely bare bootstrap gets only empty template values: `deploy/hetzner-bootstrap.sh:212-217`; `deploy/tinyassets-env.template:121`, `:138`.

The accurate impact is a dead legacy recovery-seed path plus misleading documentation—not loss of the active per-universe rotation path.

4. **DISAGREE_EVIDENCE**

The GitHub App token generator exists, but it has not functionally relocated live runtime delivery.

- The timer runs every 45 minutes: `deploy/github-app-token-refresher.timer:5-11`.
- The script mints a token and writes `TINYASSETS_GITHUB_PR_CAPABILITIES` into the host env: `scripts/github-app-token-refresher.py:97-112`.
- The helper only atomically updates the file; it performs no restart or reload: `deploy/install-tinyassets-env.sh:462-464`.
- The running daemon received its environment only when Compose created it: `deploy/tinyassets-daemon.service:79`. Consequently, refreshes do not reach the existing process.
- The service also refuses to run unless a manually provisioned `/etc/tinyassets/github-app-token-refresher.env` already exists: `deploy/github-app-token-refresher.service:6-14`; installation only installs/enables the units at `.github/workflows/install-host-services.yml:404-417`.
- Runtime lookup reads the process environment, not the host env file: `tinyassets/auth/provider.py:101-129`.

**ADAPT — do not restore the two global auth secrets to `deploy-prod.yml`. Remove their production entrypoint/template/runbook contract; change worker quarantine and `get_status` to evaluate the selected universe’s vault credential; remove or separately document host-local global auth; and add a fresh-host test proving deposited per-universe Codex/Claude credentials work with no ambient bundle. Separately fix the GitHub App refresher to provide live reload—prefer a dynamically read credential file/vault, or explicitly recreate the daemon under the host-mutation lock—and provision its bootstrap credentials.**