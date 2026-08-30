# TinyAssets daemon deploy runbook (provider-neutral Debian 12 VM)

Self-host migration Row D per
`docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md`.

**Current target (2026-04-20):** DigitalOcean **Basic Droplet** ($6/mo, 1 vCPU / 1 GB RAM / 25 GB SSD tier or larger), **Debian 12** image, region NYC / SFO / AMS / FRA.

**Pivot note:** Hetzner Cloud CX22 was the original pick (per exec plan §2) and remains the documented fallback. Mid-cutover 2026-04-20 the Hetzner US individual-signup form blocked account creation; switched to DigitalOcean (GitHub-OAuth-based signup, works cleanly). Same Debian 12 image + same `hetzner-bootstrap.sh` script run unchanged. Script file name kept for git history; the script is generic-Debian-12.

**Works on:** DigitalOcean Basic Droplet / Hetzner Cloud CX22 / Linode 1 GB / Vultr Cloud Compute / any Debian 12 VM with public IPv4. Steps below use DO terminology; Hetzner/Linode/Vultr equivalents noted where meaningful.

**Outcome:** `https://tinyassets.io/mcp` stays green even when the host
machine is powered off. 48-hour-offline acceptance gate lives at Row F;
this runbook gets you to the single-host green state.

---

## Prerequisites

- DigitalOcean account (or Hetzner Cloud / Linode / Vultr) with billing.
- SSH keypair registered in the provider's SSH-keys surface.
- Domain `tinyassets.io` managed by Cloudflare (already true post-P0).
- Cloudflare Zero Trust tunnel `tinyassets-daemon-prod` already created
  (or a new tunnel you'll create at step 3). Token in hand.
- Supabase project provisioned (for Track A schema + auth).
- GitHub OAuth app registered with callback
  `https://tinyassets.io/authorize/github/callback`.

## Step 1 — Provision the Droplet (~5 min)

Via DigitalOcean Control Panel (or `doctl` CLI):

1. **Droplets → Create Droplet**.
2. **Region:** NYC / SFO / AMS / FRA — pick the one lowest-latency to your Cloudflare edge (typically your user base region).
3. **Image:** Marketplace or Distributions → **Debian 12**.
4. **Size:** Basic → Regular SSD → **$6/mo tier** (1 vCPU, 1 GB RAM, 25 GB SSD) minimum. Upgrade to $12/mo (2 GB RAM) if you expect paid-market concurrency on day one.
5. **Authentication:** SSH Key → select your registered key. Do NOT enable password auth.
6. **Firewall:** attach or create:
   - Inbound: SSH (22) from your admin IP only, ICMP open.
   - **Do NOT** open 8001 — the daemon binds loopback-only.
   - Outbound: all.
7. **Hostname:** `tinyassets-daemon-prod-01`.
8. **Cloud-config** (advanced options, optional): none needed; bootstrap handles provisioning.

Wait for status → green. Copy the public IPv4.

**Hetzner equivalent** (if using fallback provider): Hetzner Cloud Console → Servers → Add Server → Location Falkenstein/Nuremberg → Image Debian 12 → Shared vCPU CX22 → same SSH key + firewall posture. Name `tinyassets-daemon-prod-01`.

## Step 2 — Bootstrap the box (~3 min)

SSH in:

```bash
ssh root@<public-ipv4>
```

Run the bootstrap script. Two paths:

**Path A (recommended — single command):**

```bash
curl -fsSL https://raw.githubusercontent.com/Jonnyton/TinyAssets/main/deploy/hetzner-bootstrap.sh \
    -o /tmp/bootstrap.sh
sudo bash /tmp/bootstrap.sh
```

**Path B (local clone — if you want to review first):**

```bash
git clone https://github.com/Jonnyton/TinyAssets.git /tmp/tinyassets-src
sudo bash /tmp/tinyassets-src/deploy/hetzner-bootstrap.sh
```

The script is idempotent. Re-running is safe; it skips steps whose
end-state is already reached. Expected output ends with:

```
[bootstrap] bootstrap complete.

Next steps (host action required):
  1. Fill in secrets: sudo nano /etc/tinyassets/env
  2. Generate the daemon-only agent interchange key (Step 3 below)
  ...
```

## Step 3 — Fill `/etc/tinyassets/env` (~5 min)

Open in your editor of choice:

```bash
sudo nano /etc/tinyassets/env
```

Fill in these fields (template at `/opt/tinyassets/deploy/tinyassets-env.template`
documents each):

| Variable | Source |
|---|---|
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare dashboard → Zero Trust → Networks → Tunnels → (tunnel) → Connectors → Install → "Token" field. |
| `SUPABASE_DB_URL` | Supabase dashboard → Project Settings → Database → Connection string → **Pooled** (port 6543). |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → Project Settings → API → service_role key (keep secret; never ship to clients). |
| `GITHUB_OAUTH_CLIENT_ID` | GitHub → Settings → Developer settings → OAuth Apps → TinyAssets → Client ID. |
| `GITHUB_OAUTH_CLIENT_SECRET` | Same page → "Generate a new client secret" → copy once. |
| `TINYASSETS_IMAGE` | Required immutable GHCR digest ref. `deploy-prod.yml` resolves the short-SHA tag from `.github/workflows/build-image.yml` to `ghcr.io/jonnyton/tinyassets-daemon@sha256:<digest>` before writing `/etc/tinyassets/env`. |
| `BACKUP_DEST` | Optional until offsite backup is provisioned; a root-configured rclone destination such as `storagebox:tinyassets-backups`. |

Save + exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

Generate the daemon-only request-admission key without printing it. The
dedicated file is exposed only to the daemon, not to workers, Cloudflare, or
logging sidecars, and the atomic installer preserves its ownership and mode:

```bash
openssl rand -base64 48 | tr -d "\n" | sudo env TINYASSETS_ENV_FILE=/etc/tinyassets/request-idempotency.env TINYASSETS_LEGACY_ENV_FILE=/etc/tinyassets/no-request-idempotency-legacy bash /opt/tinyassets/deploy/install-tinyassets-env.sh set-once TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY
```

For automated production deploys, store a separately generated value under the
GitHub Actions repository secret `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY`.
The deploy validates it before touching the host and installs it before
recreating the daemon/workers. Ordinary deploys use `set-once` and fail closed
if GitHub and the host differ because persisted idempotency hashes and admission
witnesses depend on the current key. If the key crosses an execution boundary,
first ship the reviewed daemon-only boundary correction, replace the repository
secret, then manually dispatch that same correction image with
`rotate_request_idempotency_hmac=true`. Incident rotation intentionally
invalidates witnesses signed by the exposed key. The rotation workflow requires
the resolved target to match the exact immutable image already running on the
daemon and four workers, proves the worker identities lack minting authority in
host-controlled Docker configuration metadata before the stop-writer fence,
then reads state by those immutable IDs and repeats the name-to-ID check before
it transmits the replacement. Verify the restarted worker environments and
canonical MCP health before resuming activation.

Generate a unique daemon-only agent interchange key without printing it to the
terminal. This writes canonical single-line base64 for 48 random bytes:

```bash
sudo sh -c 'umask 027; key=$(openssl rand -base64 48 | tr -d "\n"); printf "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY=%s\n" "$key" > /etc/tinyassets/agent-interchange.env; chown root:tinyassets /etc/tinyassets/agent-interchange.env; chmod 640 /etc/tinyassets/agent-interchange.env'
```

The separate file is injected only into the daemon container. Replace the key
and restart to rotate it. Deleting a repository secret merely blocks automated
deploys; normal revocation rotates and deploys, while emergency revocation
stops the daemon before removing this protected file.

Permissions check:

```bash
ls -la /etc/tinyassets/env /etc/tinyassets/agent-interchange.env /etc/tinyassets/request-idempotency.env
# -rw-r----- 1 root tinyassets ... env
# -rw-r----- 1 root tinyassets ... agent-interchange.env
# -rw-r----- 1 root tinyassets ... request-idempotency.env
```

If ownership/mode differs, re-run the bootstrap — it resets to
`root:tinyassets 640`.

## Step 3b — Codex auth persistent volume

Codex CLI uses single-use OAuth refresh tokens that rotate in-place
during normal operation. The compose stack persists Codex's auth state
across container restarts at `CODEX_HOME=/data/.codex` on the shared
`tinyassets-data` Docker volume (see `deploy/compose.yml`).
Without this, every restart throws away rotated tokens and the next
refresh attempt fails with `refresh_token_reused`. Design source:
<https://developers.openai.com/codex/auth/ci-cd-auth>.

**The deploy workflow prepares the auth directory + migration automatically.**
`.github/workflows/deploy-prod.yml` has a `Prepare codex auth
persistent volume` step that runs on every deploy. It is idempotent:

- Creates `tinyassets-data` when missing, resolves its local mountpoint,
  and creates `.codex` inside it; repairs ownership (`uid 1001:1001`)
  and mode (`700`) unconditionally every deploy so a failed earlier
  attempt gets healed back to a state uid 1001 can write.
- The one-time migration that copied a rotated `auth.json` out of the
  running worker container was deleted with the host-run worker fleet
  (2026-08-29). A pre-existing droplet already holds
  `/data/.codex/auth.json` on the volume; a fresh droplet seeds it from
  `TINYASSETS_CODEX_AUTH_JSON_B64` (case 1 below).
- Every deploy is otherwise a complete no-op for this section — the
  volume + `auth.json` are already in place and the entrypoint
  preserves the file on restart.

The auth file is used by the `tinyassets-daemon` container alone: its
in-process executor handles `run_branch` MCP calls and its
assigned-queue consumer runs due automations, and both call
`codex exec`. Concurrent
refresh attempts are serialized by `/usr/local/bin/codex` (which is
`deploy/codex-flock-wrapper.sh`, installed by the Dockerfile in place
of the bare codex symlink) — it takes an exclusive `flock -x` on
`$CODEX_HOME/.lock` before every invocation. This mitigates the
`refresh_token_reused` race that Codex's official CI/CD auth guide
warns about for shared-auth scenarios (Codex Issue #10332).

**Host action is only needed in two rare cases:**

1. **Brand-new droplet, no live container to migrate from.** The
   workflow step creates the empty `/data/.codex`; the new container then
   seeds `auth.json` from `TINYASSETS_CODEX_AUTH_JSON_B64` (GitHub
   Actions secret or `/etc/tinyassets/env`) on first boot. Host action:
   keep `TINYASSETS_CODEX_AUTH_JSON_B64` rotated so a fresh-droplet
   bootstrap has a known-good seed available.
2. **Persistent volume wiped (disaster recovery).** Same as case 1:
   the entrypoint reseeds from the env-var on the next boot. Host
   action: same — keep the GitHub Actions secret or `/etc/tinyassets/env`
   value fresh.

In normal steady-state operation (volume intact, container restarts
for image bumps), Codex's in-place refresh chain survives indefinitely
with no host intervention.

Claude Code subscription auth mirrors this persistence pattern directly.
`deploy/compose.yml` sets `CLAUDE_CONFIG_DIR=/data/.claude`, and the
entrypoint creates that directory on the shared `tinyassets-data` volume.
The matching keepalive workflow runs a trivial `claude -p` call with the
same `CLAUDE_CONFIG_DIR` so the subscription session is exercised after
deploys and during idle weeks. Host login command for a fresh volume:

```bash
sudo docker exec -it -e CLAUDE_CONFIG_DIR=/data/.claude tinyassets-daemon claude auth login --claudeai
```

## Step 4 — Start the daemon (~30 sec)

```bash
sudo systemctl start tinyassets-daemon
sudo systemctl status tinyassets-daemon
```

Expect: **active (running)**. If the container image hasn't been pulled
yet, compose pulls it inline — first start takes ~30s longer than
subsequent restarts.

Tail logs:

```bash
sudo journalctl -u tinyassets-daemon -f
```

Look for:
- `daemon-1 | Starting TinyAssets Server on 0.0.0.0:8001 (transport=streamable-http)` — daemon bound.
- `cloudflared | Registered tunnel connection connIndex=0` — tunnel up.

## Step 5 — Verify canary green (~10 sec)

From the Hetzner box (container-internal):

```bash
docker exec tinyassets-daemon \
    python scripts/mcp_public_canary.py \
        --url http://127.0.0.1:8001/mcp --verbose
```

Expect `[canary] OK` + exit 0.

From your laptop (public-canonical):

```bash
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --verbose
```

Expect `[canary] OK`. **This is the pass gate.** Once green, the
Hetzner box is serving the canonical URL; your home tunnel can stay
off permanently.

If the canary returns red, see the **Diagnosis** section below.

## Step 6 — Power off the host tunnel (optional, only after you've watched green for 10+ min)

If you've been running the old cloudflared on your home box, it's now
redundant (dual-origin race). Stop it:

```bash
# On home box (Windows tray):
#  → Tray → "Stop cloudflared" menuitem
# OR manually:
taskkill /F /IM cloudflared.exe
```

Leave it off. The Hetzner tunnel is now the sole origin for
`mcp.tinyassets.io`.

---

## Rollback

If step 4 or 5 fails:

```bash
sudo systemctl stop tinyassets-daemon
# Investigate via journalctl; see Diagnosis section below.
# To fully revert:
sudo systemctl disable tinyassets-daemon
sudo rm /etc/systemd/system/tinyassets-daemon.service
sudo systemctl daemon-reload
# Destroy the box:
#   Hetzner console → Server → Delete.
```

The canonical URL stays green on your home tunnel throughout rollback
— nothing changes on the Cloudflare side until you flip DNS or disable
the home tunnel. The Hetzner deploy is fully additive until you power
off the home tunnel at Step 6.

---

## Diagnosis (when things go red)

**Single-URL architecture (2026-04-20).** Per Hard Rule #10, the canonical
public endpoint is `https://tinyassets.io/mcp` only. `mcp.tinyassets.io`
is an Access-gated internal tunnel origin that returns 401/403 to
unauthenticated probes — the former dual-URL color-asymmetry diagnosis
is retired. Layer diagnosis now uses Cloudflare Worker logs +
cloudflared tunnel logs. See
`docs/ops/dns-tunnel-single-entry-cutover.md` § Observability after
cutover for the post-cutover playbook.

## Common failure modes

- **`CLOUDFLARE_TUNNEL_TOKEN` not set or wrong.** `docker logs tinyassets-tunnel` shows `Unauthorized` or hangs at "Tried to connect to tunnel". Fix: re-copy the token from the Cloudflare dashboard; tokens don't expire but do get regenerated on tunnel rotation.
- **Healthcheck never passes.** `docker inspect tinyassets-daemon | jq '.[].State.Health'` shows consecutive failures. The healthcheck runs `mcp_public_canary.py` against `http://127.0.0.1:8001/mcp`; if daemon didn't bind, check `docker logs tinyassets-daemon`.
- **Short-SHA image pin not pullable.** Image tag doesn't exist in GHCR. Pick a known-good short-SHA tag from GHCR, resolve it to a digest ref, write `TINYASSETS_IMAGE=ghcr.io/jonnyton/tinyassets-daemon@sha256:<digest>` in `/etc/tinyassets/env`, then `systemctl restart tinyassets-daemon`.
- **`/etc/tinyassets/env` permissions wrong.** Compose reads env file via docker; mode must allow the `tinyassets` user to read. `chown root:tinyassets /etc/tinyassets/env && chmod 640 /etc/tinyassets/env`.
- **Docker pull fails (GHCR auth).** If the image is private, the box needs a pull credential. This runbook assumes the GHCR image is public; if not, add `docker login ghcr.io` to the bootstrap + supply a PAT with `read:packages`.

---

## What this deploy does NOT include (future rows)

## Row L — Daemon watchdog (installed by bootstrap)

`hetzner-bootstrap.sh` installs a watchdog alongside the daemon unit.
Catches the failure systemd's `Restart=always` CAN'T see: daemon
process alive, `/mcp` unresponsive (hung transaction, wedged thread,
OOM-adjacent).

- **Timer:** `tinyassets-watchdog.timer` fires every 2 min starting 60s after boot.
- **Script:** `scripts/watchdog.py` probes `http://127.0.0.1:8001/mcp` via the canary. State persists at `/var/lib/tinyassets-watchdog/state.json` across ticks.
- **Trigger:** 3 consecutive reds → `sudo systemctl restart tinyassets-daemon.service`.
- **Rate limit:** min 10 min between restarts — blocks hot-loop on persistent-failure states.
- **Logs:** `sudo journalctl -u tinyassets-watchdog -f`.
- **Sudoers:** scoped rule at `/etc/sudoers.d/tinyassets-watchdog` — `workflow` user has NOPASSWD ONLY for the one restart command; no other sudo access.

Check next fire: `sudo systemctl list-timers tinyassets-watchdog.timer`.

## Row J — State backup (installed by bootstrap)

`hetzner-bootstrap.sh` installs a nightly backup of the `tinyassets-data`
named Docker volume to the configured remote destination. Bootstrap enables the
timer unconditionally; if `BACKUP_DEST` is blank, `backup.sh`
exits 1 with a clear message (so ops sees the wiring but can defer
remote provisioning).

- **Timer:** `tinyassets-backup.timer` fires nightly at 03:00 UTC.
- **Script:** `deploy/backup.sh` creates strict brain and best-effort full-volume `.tar.gz` archives, then uploads them with `rclone`.
- **Retention:** 7 daily + 4 weekly + 6 monthly (override via `BACKUP_RETAIN_*` env vars).
- **Host action needed:** configure an rclone remote as root, set its destination in `/etc/tinyassets/env` as `BACKUP_DEST=<remote>:<path>`, then manually run the backup service once.

Storage Box provisioning (host does this when ready):
1. Hetzner Cloud console → Storage Boxes → Add → BX11 (100 GB, ~€1/mo).
2. Create subuser scoped to `/tinyassets-backups/`. Copy the SFTP host + subuser credentials.
3. Run `sudo rclone config` and create a remote named `storagebox` with those credentials.
4. Set `BACKUP_DEST=storagebox:tinyassets-backups` in `/etc/tinyassets/env`.
5. Manually trigger first backup to verify: `sudo systemctl start tinyassets-backup.service && sudo journalctl -u tinyassets-backup -n 50`.
6. On success, 03:00 UTC nightly cadence takes over.

**Restore runbook:** `deploy/RESTORE.md` covers full-volume restore
from a specific tarball. Estimated 5-15 min depending on archive size.

## Operator access to the live droplet + config/env changes

Day-2 ops on the **already-running** prod droplet — distinct from Step 1
(new-box provisioning) and Row M (CI *image* deploy). This section exists
because a session burned time here on 2026-06-25 mistaking a key-name problem
for "no access".

### SSH access — the deploy key is non-default-named

The operator deploy key is **`~/.ssh/tinyassets_deploy_ed25519`** (pubkey comment
`tinyassets-deploy@…`). It is NOT one of ssh's default names (`id_rsa` /
`id_ed25519`) and there is usually no `~/.ssh/config` entry, so a bare
`ssh root@161.35.237.133` never offers it and fails with
**`Permission denied (publickey)`**. That is NOT "no access" — ssh just didn't
try the right key. Connect explicitly:

```bash
chmod 600 ~/.ssh/tinyassets_deploy_ed25519   # ssh refuses a world-readable key
ssh -i ~/.ssh/tinyassets_deploy_ed25519 -o IdentitiesOnly=yes root@161.35.237.133
```

Add a `~/.ssh/config` entry once so `ssh tinyassets-droplet` Just Works:

```
Host tinyassets-droplet
    HostName 161.35.237.133
    User root
    IdentityFile ~/.ssh/tinyassets_deploy_ed25519
    IdentitiesOnly yes
```

Easiest — the repo wraps this in a **read-only** helper that auto-selects the
key, fixes perms, and never mutates the daemon:

```bash
python scripts/droplet.py status   # container names + daemon health
python scripts/droplet.py env      # auto-ship + writer/provider env in the daemon
python scripts/droplet.py canary   # loopback MCP probe from inside the daemon
python scripts/droplet.py ssh -- <cmd>   # one-off remote command
```

### Two deploy paths — image vs config/env

| Change | How it reaches the live daemon |
|---|---|
| **New image** (code merged to `main`) | Automatic: `build-image.yml` → `deploy-prod.yml` (Row M) pins the tag, pulls, restarts, canaries, auto-rolls-back. |
| **Config / env flag** (eval-gate flip, feature flag) | **Manual** — a config commit does NOT trigger a deploy. Apply on the droplet (below). |

### Compose layout (re-verified on the droplet 2026-08-29)

systemd runs `ExecStart=docker compose -f `**`/opt/tinyassets/compose.yml`**` up`.

**The symlink this section used to describe is gone.** `/opt/tinyassets/compose.yml`
is a REGULAR file (`root:root 0644`, `stat`'d 2026-08-29), not a symlink to
`deploy/compose.yml`. Whatever replaced it, the consequence is that editing the
`/opt/tinyassets` checkout no longer changes what systemd runs — every deploy
installs `compose.yml` over that path from the repo (below).

- Droplet-only values (image digest pin, secrets, tunnel token) live in
  `/etc/tinyassets/env`, never in the repo. `environment:` in `deploy/compose.yml`
  overrides `env_file` for the same key.
- A config-only commit still does **not** auto-deploy — only image builds trigger
  Row M. But an image deploy now DOES carry the compose/vector/unit change with
  it: see the next section. Between 2026-08-18 and 2026-08-27 it did not
  (PR #2442 dropped the sync), and every `deploy/compose.yml` edit was inert in
  production for nine days.

### Runtime bundle transaction

`deploy/{compose.yml,vector.yaml,vector-betterstack.yaml,vector-entrypoint.sh,tinyassets-daemon.service}`
are the **runtime bundle**. `deploy-prod.yml`'s "Sync runtime deploy files" step
only *stages* them, into a per-run
`/tmp/tinyassets-bundle-<run id>-<attempt>/` passed to the script as
`BUNDLE_DIR`; `deploy/deploy_fail_safe.sh` owns the transaction, so config and
image succeed or fail together:

0. **claim** — under the host-mutation lock, the stage is copied into a private
   `mktemp -d` the run owns, and every stage below reads *that* copy. The stage
   is populated before the lock exists, so validating one set of bytes and
   installing another was a real window.
1. **validate** — `docker compose config` on the claimed copy with
   `/etc/tinyassets/env` and the candidate image, asserting the production
   invariants: the default service set is exactly `daemon`/`cloudflared`/`logs`
   (profiles are honoured, so `slack-agent` is absent by construction), the three
   container names, `restart: unless-stopped` on all three, digest-pinned
   `cloudflare/cloudflared:`/`timberio/vector:` sidecar images, the daemon's
   `env_file` containing `/etc/tinyassets/env`, its `tinyassets-data:/data`
   volume, its healthcheck, `TINYASSETS_DATA_DIR: /data`, a positive
   `daemon.mem_limit`, that the compose **source text** interpolates
   `${TINYASSETS_IMAGE}` in the daemon image line, and the `logs` service
   mounting exactly the three vector files read-only. Any miss →
   `deploy_result=bundle_invalid`, exit 1, **production untouched**.

   > **Read the real rendering before adding or moving a check here.** Compose
   > v5 (the droplet runs 5.1.3) does not hand back what the compose file says:
   > it resolves every `env_file` into `environment` and drops the key, and
   > `mem_limit: 4g` comes back as the *string* `'4294967296'`. The first
   > production run of this transaction refused a correct bundle for exactly
   > that reason (`"daemon.env_file is []"`, 2026-08-30 00:34Z, run
   > 33283629722) while the mocked suite was green, because the fake and the
   > validator shared one wrong belief. `env_file` is now read from a second
   > `--no-interpolate` render. `tests/test_deploy_bundle_validator.py` pins the
   > validator against a *capture* of the real output and needs no docker, so it
   > runs everywhere — extend that capture, not just the fake, when Compose is
   > upgraded or these assertions change.
2. **snapshot** — the *live* `/opt/tinyassets/compose.yml`,
   `/opt/tinyassets/deploy/{compose.yml,vector.yaml,vector-betterstack.yaml,vector-entrypoint.sh}`
   and `/etc/systemd/system/tinyassets-daemon.service` are copied into
   `/var/lib/tinyassets-deploy/bundle-snapshots/<UTC stamp>-XXXXXX/`, alongside a
   `manifest` recording each file's `uid gid mode`. A restore reinstates *those*,
   not the forward install's contract — otherwise rolling back would rewrite
   `root:root` `compose.yml` as `tinyassets:tinyassets`, which is a rollback that
   changes something. The last 5 snapshots are kept, and **never** the one
   `bundle-previous` names.
3. **install** — `tinyassets:tinyassets` `0644` (`0755` for the entrypoint script),
   the unit `root:root 0644`, then `systemctl daemon-reload`. Only after this
   succeeds does `/var/lib/tinyassets-deploy/bundle-previous` advance — written
   atomically (temp file + `mv -fT`) — to name the snapshot the install replaced.
   Failing to advance it is fatal, because every later rollback would then read
   the *previous* deploy's snapshot.
4. **converge** — the usual `up -d daemon cloudflared logs`, plus
   `up -d --force-recreate logs` when any vector input changed.
   `vector-entrypoint.sh` copies the mounted files into `/run/vector-config` only
   at container start, so an unchanged image would otherwise keep serving the old
   config. A non-zero `docker compose up` is a failure even if the daemon looks
   healthy afterwards, and `accept()` re-checks `tinyassets-logs` **last**, after
   daemon health and the tunnel — it can be seen `running` and then die while the
   health probe is still waiting.
5. **rollback restores config first, then the image.** Both paths — the script's
   internal rollback on an unhealthy candidate, and
   `deploy_fail_safe.sh --restore-bundle <previous image>`, which the workflow's
   "Roll back if the public canary is red" step calls — reinstall the snapshot,
   `daemon-reload`, then converge the previous image (force-recreating `logs` if
   the restore moved a vector input). Converging the previous IMAGE against the
   new CONFIG would roll back half a change.

**Nothing reports success over a mixed tree.** A restore that does not complete
leaves `/var/lib/tinyassets-deploy/bundle-dirty` — which *names the snapshot that
must go back*, written atomically like the pointer — and reports
`deploy_result=rollback_failed` (exit 3). While that marker exists a normal
deploy refuses with `bundle_dirty`, because snapshotting a half-installed tree
would make the mixed state the next rollback target. `--restore-bundle` runs
regardless and clears it.

Two corners of that worth knowing before you meet them at 3am:

- **A marker that will not clear is terminal.** If the deploy otherwise
  succeeded but the marker survives, the result is
  `deploy_result=marker_clear_failed` (exit 3) — `deployed_image=` is still
  printed, because the image *did* change and you need to know which one is
  live. Production is fine; the *next* deploy is blocked until you remove the
  file by hand.
- **An empty marker is not "no marker".** It means a run was interrupted without
  recording its snapshot. `--restore-bundle` refuses rather than falling back to
  `bundle-previous`: that pointer names the last *good* state, not the
  interrupted one, so restoring it would report success over a tree nobody has
  accounted for. Look in `bundle-snapshots/`, decide which one is right, and
  write its path into `bundle-dirty` yourself.

An **absent** stage directory is not an error: the script logs
`bundle: absent, image-only deploy` and skips these stages, so a manual
`sudo bash /tmp/deploy_fail_safe.sh <ref>` still works. A **partial** stage
directory is refused — half a bundle is what caused the 2026-08 502. An
image-only deploy that fails never touches the bundle: a surviving pointer
belongs to an earlier deploy and names a state this run did not create.

Manual restore, if you ever need it without a deploy:

```bash
cat /var/lib/tinyassets-deploy/bundle-dirty       # set only if a run was interrupted
cat /var/lib/tinyassets-deploy/bundle-previous    # otherwise, the last good snapshot
sudo bash /tmp/deploy_fail_safe.sh --restore-bundle "$(grep -E '^TINYASSETS_IMAGE=' /etc/tinyassets/env | cut -d= -f2-)"
```

### Applying a config/env change to the live daemon

```bash
ssh tinyassets-droplet                       # or: python scripts/droplet.py ssh

# A — a compose change already committed (e.g. a daemon env flag in
#     deploy/compose.yml): there is NO symlink any more (see "Compose layout"),
#     so a checkout pull does not change what systemd runs. Either let the next
#     image deploy install it as part of the runtime bundle, or install it by
#     hand at BOTH paths:
cd /opt/tinyassets && git pull --ff-only origin main
sudo install -m 0644 -o tinyassets -g tinyassets \
  /opt/tinyassets/deploy/compose.yml /opt/tinyassets/compose.yml

# B — a host-only env value (image pin, secret, quick flag): edit the env file.
printf '\nTINYASSETS_SOME_FLAG=value\n' >> /etc/tinyassets/env

# Recreate ONLY the daemon so it re-reads config (brief MCP-surface blip):
systemctl restart tinyassets-daemon
docker exec tinyassets-daemon printenv | grep TINYASSETS_SOME_FLAG   # confirm it took
```

Then confirm the public surface is green (Hard Rule #11):
`python scripts/droplet.py canary` (loopback) **and**
`python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp`.
Rollback: revert the edit + `systemctl restart tinyassets-daemon`.

Worked example — the 2026-06-25 auto-ship enforce flip set
`TINYASSETS_AUTO_SHIP_{RUBRIC,TRAJECTORY}_MODE=enforce` in `deploy/compose.yml`.
It was durable then via the symlink; today the same flip becomes live when the
next image deploy installs the runtime bundle.

## Row M — CI deploy pipeline (GitHub Actions)

`.github/workflows/deploy-prod.yml` auto-deploys the freshly-published
image on every successful `build-image.yml` run on `main`. SSH to the
DigitalOcean Droplet, pin the new tag in `/etc/tinyassets/env`, `docker pull`,
`systemctl restart`, run post-deploy canary, auto-rollback on red.

**GitHub secrets required** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DO_DROPLET_HOST` | Droplet public IP (e.g. `161.35.237.133`) or DNS name. |
| `DO_SSH_USER` | SSH user on the Droplet — typically `root` or a dedicated `deploy` user. |
| `DO_SSH_KEY` | Private key PEM (ed25519 recommended). Paste whole contents including BEGIN/END lines. |

Generate the key pair:
```bash
ssh-keygen -t ed25519 -C "gh-actions-deploy" -f ~/.ssh/tinyassets_deploy -N ""
cat ~/.ssh/tinyassets_deploy.pub  # add to /root/.ssh/authorized_keys on the Droplet
cat ~/.ssh/tinyassets_deploy      # paste into DO_SSH_KEY secret
```

Recommended: use a dedicated `deploy` user (not `root`) with limited
sudo — passwordless for the 2 commands the pipeline runs:

```bash
# On the Droplet, as root:
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/  # or paste deploy pubkey directly
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh

# Scoped sudoers for deploy:
cat > /etc/sudoers.d/deploy-pipeline <<EOF
deploy ALL=(root) NOPASSWD:/usr/bin/sed -i * /etc/tinyassets/env
deploy ALL=(root) NOPASSWD:/usr/bin/docker pull *
deploy ALL=(root) NOPASSWD:/usr/bin/systemctl restart tinyassets-daemon
deploy ALL=(root) NOPASSWD:/usr/bin/grep * /etc/tinyassets/env
EOF
chmod 0440 /etc/sudoers.d/deploy-pipeline
visudo -c
```

Then `DO_SSH_USER=deploy` in the GH secret.

**Behavior:**
- Trigger: successful `build-image.yml` run on `main`, OR `workflow_dispatch` with optional `image_tag` input.
- Deploy pins the new image tag + restarts the daemon.
- Waits up to 90s for cold-start; polls canary every 5s.
- On canary green, deploy succeeds.
- On canary red, auto-rollback to the previous `TINYASSETS_IMAGE` value, re-verify canary, and open a `deploy-failed` GitHub issue with the run URL. Distinct from `p0-outage` (Row H) — deploy-failed = we caused it; p0-outage = daemon died spontaneously.

## Row K — Log aggregation (sidecar in compose)

The `logs` service in `deploy/compose.yml` runs a Vector sidecar that
receives `daemon`, `cloudflared`, and worker stdout through Docker's
asynchronous Fluent logging driver on host-loopback port 24224 and forwards
events. Vector receives no Docker socket or container-control capability. Two paths:

- **Default (no config):** Vector writes to its own stdout, which
  `docker compose` + journald capture. Equivalent to not running the
  sidecar, but the wiring exists for one-env-flip enable.
- **With Better Stack:** set `BETTERSTACK_SOURCE_TOKEN` in
  `/etc/tinyassets/env`, `sudo systemctl restart tinyassets-daemon`.
  Vector starts shipping to `https://in.logs.betterstack.com` with
  `tinyassets` service + `daemon`/`cloudflared` role metadata on each
  event. Free tier = 3 GB/mo retention.

**Host action (optional — enable Better Stack):**
1. Sign up at betterstack.com (free tier). Create a "Logs" source.
2. Copy the source token.
3. `sudo nano /etc/tinyassets/env` → fill `BETTERSTACK_SOURCE_TOKEN=...`.
4. `sudo systemctl restart tinyassets-daemon` (restarts the whole compose stack including the logs sidecar).
5. Verify in Better Stack dashboard — events should appear within ~30s.

If the box dies, Better Stack retains the most recent logs for
debugging the death itself. Without this, `journalctl` is box-local +
lost on destroy.

## What this deploy does NOT include (future rows)

Each of these ships independently on top of this compose + systemd
foundation. Row D is the anchor.

---

## Cost

- CX22: €5.83/mo → ~$6.50/mo at current exchange.
- Hetzner Storage Box (Row J, not yet wired): ~€1/mo for 100 GB.
- Cloudflare (all Workers traffic on free tier at current volume): $0.
- Supabase Pro (existing, not deploy-gated): $25/mo.

Total incremental cost of self-host migration: **~$7/mo** (storage box
adds $1 when Row J lands).

## Support + escalation

- **Log source of truth:** `journalctl -u tinyassets-daemon -f` on the Hetzner box.
- **Canary alarm:** `.github/workflows/uptime-canary.yml` auto-opens a GitHub issue labeled `p0-outage` on 2 consecutive reds. Host gets GitHub email notification.
- **Tunnel dashboard:** `https://dash.cloudflare.com/<acct>/one/networks/connectors` — shows tunnel + connector health.

If canary goes red + persists >10 min AND host isn't responding, the
succession runbook (`SUCCESSION.md` §6.1) applies: admin-pool member
can SSH in + restart or rollback per this runbook.
