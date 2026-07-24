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

Permissions check:

```bash
ls -la /etc/tinyassets/env
# -rw-r----- 1 root tinyassets ... env
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
- On the very first deploy onto a pre-existing live droplet, copies
  the rotated `auth.json` out of the running `tinyassets-worker`
  container into `/data/.codex` so the post-restart container preserves
  the live refresh chain. It checks the new `/data/.codex/auth.json`
  path first and then the legacy `/app/.codex/auth.json` path for the
  one-time migration.
- After that, every subsequent deploy is a complete no-op for this
  section — the volume + `auth.json` are already in place and the
  entrypoint preserves the file on restart.

The auth file is shared across the `tinyassets-daemon` and
`tinyassets-worker` containers (both call `codex exec`: the daemon's
in-process executor handles `run_branch` MCP calls; the worker's
`fantasy_daemon` subprocess handles queued BranchTasks). Concurrent
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

## Host uptime services

Bootstrap converges the complete host-uptime set through
`deploy/install-host-uptime-services.sh`:

- `tinyassets-watchdog.timer`
- `daemon-watchdog.timer`
- `tinyassets-backup.timer`
- `tinyassets-prune.timer`
- `tinyassets-disk-watch.timer`

The installer validates its complete source manifest and scoped sudoers
candidate before activation, stores runtime files under
`/opt/tinyassets-host-uptime/releases/<content-hash>/`, atomically switches the
`current` symlink, and enables, starts, and verifies every timer on every run.
It pauses timers and waits boundedly for active oneshot services before
changing installed files. Re-running bootstrap is therefore also the repair
path for byte-current but disabled or inactive timers.

Verify the converged set:

```bash
sudo systemctl is-enabled tinyassets-watchdog.timer daemon-watchdog.timer \
  tinyassets-backup.timer tinyassets-prune.timer tinyassets-disk-watch.timer
sudo systemctl is-active tinyassets-watchdog.timer daemon-watchdog.timer \
  tinyassets-backup.timer tinyassets-prune.timer tinyassets-disk-watch.timer
sudo systemctl list-timers 'tinyassets-*' 'daemon-watchdog.timer'
readlink -f /opt/tinyassets-host-uptime/current
```

The `Install Host Services` workflow uses the same installer. Automatic runs
checkout the successful triggering deploy's full source SHA; manual runs pin
the dispatch's `github.sha`. The restart workflow's install option delegates
to the same manifest. Both workflows checksum a unique private remote bundle
before invoking the installer.

## Row L — Daemon watchdog (installed by bootstrap)

The shared installer installs two complementary watchdogs alongside the
daemon unit. They catch failures systemd's `Restart=always` cannot see:
an alive but unresponsive `/mcp` process and a stale daemon/container
heartbeat.

- **Timer:** `tinyassets-watchdog.timer` fires every 30s starting 60s after boot.
- **Local MCP watchdog:** `/opt/tinyassets-host-uptime/current/scripts/watchdog.py` probes `http://127.0.0.1:8001/mcp` via the installed canary. State persists at `/var/lib/tinyassets-watchdog/state.json` across ticks.
- **Daemon watchdog:** `/opt/tinyassets-host-uptime/current/deploy/daemon-watchdog.sh` checks the systemd unit, compose containers, and freshest worker-supervisor heartbeat.
- **Trigger:** 3 consecutive reds → `sudo systemctl restart tinyassets-daemon.service`.
- **Rate limit:** min 10 min between restarts — blocks hot-loop on persistent-failure states.
- **Logs:** `sudo journalctl -u tinyassets-watchdog -f`.
- **Sudoers:** scoped rule at `/etc/sudoers.d/tinyassets-watchdog` — `tinyassets` user has NOPASSWD ONLY for the one restart command; no other sudo access.

Check next fire: `sudo systemctl list-timers tinyassets-watchdog.timer`.

## Row J — State backup (installed by bootstrap)

The shared installer installs a nightly backup of the `tinyassets-data`
named Docker volume to the configured remote destination. Bootstrap enables the
timer unconditionally; if `BACKUP_DEST` is blank, `backup.sh`
exits 1 with a clear message (so ops sees the wiring but can defer
remote provisioning).

- **Timer:** `tinyassets-backup.timer` fires nightly at 03:00 UTC.
- **Script:** `/opt/tinyassets-host-uptime/current/deploy/backup.sh` creates strict brain and best-effort full-volume `.tar.gz` archives, then uploads them with `rclone`.
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

### Compose layout (reconciled 2026-06-26 — the old drift trap is fixed)

systemd runs `ExecStart=docker compose -f `**`/opt/tinyassets/compose.yml`**` up`.
That path is now a **symlink → `deploy/compose.yml`** (the tracked file), so the
old "root copy hand-maintained + drifts from `deploy/`" trap is gone — landing a
`deploy/compose.yml` change on the droplet updates what systemd runs. The
`/opt/tinyassets` checkout was reconciled to clean `origin/main` (was 1608 behind +
dirty; 2026-06-10 STATUS concern, **now resolved**). So:

- A `git pull` in `/opt/tinyassets` is now **safe** — the checkout is clean, no
  local edits to clobber. (The old "never git pull" warning is obsolete.)
- A config commit still does **not** auto-deploy — only image builds trigger Row M.
  Landing a compose/env change is the manual step below.
- Droplet-only values (image digest pin, secrets, tunnel token) live in
  `/etc/tinyassets/env`, never in the repo. `environment:` in `deploy/compose.yml`
  overrides `env_file` for the same key.

### Applying a config/env change to the live daemon

```bash
ssh tinyassets-droplet                       # or: python scripts/droplet.py ssh

# A — a compose change already committed (e.g. a daemon env flag in
#     deploy/compose.yml): pull it onto the now-clean checkout; the symlink means
#     /opt/tinyassets/compose.yml reflects it immediately.
cd /opt/tinyassets && git pull --ff-only origin main

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
`TINYASSETS_AUTO_SHIP_{RUBRIC,TRAJECTORY}_MODE=enforce` in `deploy/compose.yml`,
now live + durable via the symlink (verified across a daemon restart).

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
tails `daemon` + `cloudflared` container stdout via the Docker socket
and forwards events. Two paths:

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
