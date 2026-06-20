# Workflow daemon deploy runbook (provider-neutral Debian 12 VM)

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
- Cloudflare Zero Trust tunnel `workflow-daemon-prod` already created
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
7. **Hostname:** `workflow-daemon-prod-01`.
8. **Cloud-config** (advanced options, optional): none needed; bootstrap handles provisioning.

Wait for status → green. Copy the public IPv4.

**Hetzner equivalent** (if using fallback provider): Hetzner Cloud Console → Servers → Add Server → Location Falkenstein/Nuremberg → Image Debian 12 → Shared vCPU CX22 → same SSH key + firewall posture. Name `workflow-daemon-prod-01`.

## Step 2 — Bootstrap the box (~3 min)

SSH in:

```bash
ssh root@<public-ipv4>
```

Run the bootstrap script. Two paths:

**Path A (recommended — single command):**

```bash
curl -fsSL https://raw.githubusercontent.com/Jonnyton/Workflow/main/deploy/hetzner-bootstrap.sh \
    -o /tmp/bootstrap.sh
sudo bash /tmp/bootstrap.sh
```

**Path B (local clone — if you want to review first):**

```bash
git clone https://github.com/Jonnyton/Workflow.git /tmp/workflow-src
sudo bash /tmp/workflow-src/deploy/hetzner-bootstrap.sh
```

The script is idempotent. Re-running is safe; it skips steps whose
end-state is already reached. Expected output ends with:

```
[bootstrap] bootstrap complete.

Next steps (host action required):
  1. Fill in secrets: sudo nano /etc/workflow/env
  ...
```

## Step 3 — Fill `/etc/workflow/env` (~5 min)

Open in your editor of choice:

```bash
sudo nano /etc/workflow/env
```

Fill in these fields (template at `/opt/workflow/deploy/workflow-env.template`
documents each):

| Variable | Source |
|---|---|
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare dashboard → Zero Trust → Networks → Tunnels → (tunnel) → Connectors → Install → "Token" field. |
| `SUPABASE_DB_URL` | Supabase dashboard → Project Settings → Database → Connection string → **Pooled** (port 6543). |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → Project Settings → API → service_role key (keep secret; never ship to clients). |
| `GITHUB_OAUTH_CLIENT_ID` | GitHub → Settings → Developer settings → OAuth Apps → Workflow → Client ID. |
| `GITHUB_OAUTH_CLIENT_SECRET` | Same page → "Generate a new client secret" → copy once. |
| `WORKFLOW_IMAGE` | Required immutable GHCR digest ref. `deploy-prod.yml` resolves the short-SHA tag from `.github/workflows/build-image.yml` to `ghcr.io/jonnyton/workflow-daemon@sha256:<digest>` before writing `/etc/workflow/env`. |

Save + exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

Permissions check:

```bash
ls -la /etc/workflow/env
# -rw-r----- 1 root workflow ... env
```

If ownership/mode differs, re-run the bootstrap — it resets to
`root:workflow 640`.

## Step 3b — Codex auth persistent volume

Codex CLI uses single-use OAuth refresh tokens that rotate in-place
during normal operation. The compose stack persists Codex's auth state
across container restarts at `CODEX_HOME=/data/.codex` on the shared
`workflow-data` Docker volume (see `deploy/compose.yml`).
Without this, every restart throws away rotated tokens and the next
refresh attempt fails with `refresh_token_reused`. Design source:
<https://developers.openai.com/codex/auth/ci-cd-auth>.

**The deploy workflow prepares the auth directory + migration automatically.**
`.github/workflows/deploy-prod.yml` has a `Prepare codex auth
persistent volume` step that runs on every deploy. It is idempotent:

- Creates `workflow-data` when missing, resolves its local mountpoint,
  and creates `.codex` inside it; repairs ownership (`uid 1001:1001`)
  and mode (`700`) unconditionally every deploy so a failed earlier
  attempt gets healed back to a state uid 1001 can write.
- On the very first deploy onto a pre-existing live droplet, copies
  the rotated `auth.json` out of the running `workflow-worker`
  container into `/data/.codex` so the post-restart container preserves
  the live refresh chain. It checks the new `/data/.codex/auth.json`
  path first and then the legacy `/app/.codex/auth.json` path for the
  one-time migration.
- After that, every subsequent deploy is a complete no-op for this
  section — the volume + `auth.json` are already in place and the
  entrypoint preserves the file on restart.

The auth file is shared across the `workflow-daemon` and
`workflow-worker` containers (both call `codex exec`: the daemon's
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
   seeds `auth.json` from `WORKFLOW_CODEX_AUTH_JSON_B64` (GitHub
   Actions secret or `/etc/workflow/env`) on first boot. Host action:
   keep `WORKFLOW_CODEX_AUTH_JSON_B64` rotated so a fresh-droplet
   bootstrap has a known-good seed available.
2. **Persistent volume wiped (disaster recovery).** Same as case 1:
   the entrypoint reseeds from the env-var on the next boot. Host
   action: same — keep the GitHub Actions secret or `/etc/workflow/env`
   value fresh.

In normal steady-state operation (volume intact, container restarts
for image bumps), Codex's in-place refresh chain survives indefinitely
with no host intervention.

Claude Code subscription auth mirrors this persistence pattern directly.
`deploy/compose.yml` sets `CLAUDE_CONFIG_DIR=/data/.claude`, and the
entrypoint creates that directory on the shared `workflow-data` volume.
The matching keepalive workflow runs a trivial `claude -p` call with the
same `CLAUDE_CONFIG_DIR` so the subscription session is exercised after
deploys and during idle weeks. Host login command for a fresh volume:

```bash
sudo docker exec -it -e CLAUDE_CONFIG_DIR=/data/.claude workflow-daemon claude auth login --claudeai
```

## Step 4 — Start the daemon (~30 sec)

```bash
sudo systemctl start workflow-daemon
sudo systemctl status workflow-daemon
```

Expect: **active (running)**. If the container image hasn't been pulled
yet, compose pulls it inline — first start takes ~30s longer than
subsequent restarts.

Tail logs:

```bash
sudo journalctl -u workflow-daemon -f
```

Look for:
- `daemon-1 | Starting Workflow Server on 0.0.0.0:8001 (transport=streamable-http)` — daemon bound.
- `cloudflared | Registered tunnel connection connIndex=0` — tunnel up.

## Step 5 — Verify canary green (~10 sec)

From the Hetzner box (container-internal):

```bash
docker exec workflow-daemon \
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
sudo systemctl stop workflow-daemon
# Investigate via journalctl; see Diagnosis section below.
# To fully revert:
sudo systemctl disable workflow-daemon
sudo rm /etc/systemd/system/workflow-daemon.service
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

- **`CLOUDFLARE_TUNNEL_TOKEN` not set or wrong.** `docker logs workflow-tunnel` shows `Unauthorized` or hangs at "Tried to connect to tunnel". Fix: re-copy the token from the Cloudflare dashboard; tokens don't expire but do get regenerated on tunnel rotation.
- **Healthcheck never passes.** `docker inspect workflow-daemon | jq '.[].State.Health'` shows consecutive failures. The healthcheck runs `mcp_public_canary.py` against `http://127.0.0.1:8001/mcp`; if daemon didn't bind, check `docker logs workflow-daemon`.
- **Short-SHA image pin not pullable.** Image tag doesn't exist in GHCR. Pick a known-good short-SHA tag from GHCR, resolve it to a digest ref, write `WORKFLOW_IMAGE=ghcr.io/jonnyton/workflow-daemon@sha256:<digest>` in `/etc/workflow/env`, then `systemctl restart workflow-daemon`.
- **`/etc/workflow/env` permissions wrong.** Compose reads env file via docker; mode must allow the `workflow` user to read. `chown root:workflow /etc/workflow/env && chmod 640 /etc/workflow/env`.
- **Docker pull fails (GHCR auth).** If the image is private, the box needs a pull credential. This runbook assumes the GHCR image is public; if not, add `docker login ghcr.io` to the bootstrap + supply a PAT with `read:packages`.

---

## What this deploy does NOT include (future rows)

## Row L — Daemon watchdog (installed by bootstrap)

`hetzner-bootstrap.sh` installs a watchdog alongside the daemon unit.
Catches the failure systemd's `Restart=always` CAN'T see: daemon
process alive, `/mcp` unresponsive (hung transaction, wedged thread,
OOM-adjacent).

- **Timer:** `workflow-watchdog.timer` fires every 2 min starting 60s after boot.
- **Script:** `scripts/watchdog.py` probes `http://127.0.0.1:8001/mcp` via the canary. State persists at `/var/lib/workflow-watchdog/state.json` across ticks.
- **Trigger:** 3 consecutive reds → `sudo systemctl restart workflow-daemon.service`.
- **Rate limit:** min 10 min between restarts — blocks hot-loop on persistent-failure states.
- **Logs:** `sudo journalctl -u workflow-watchdog -f`.
- **Sudoers:** scoped rule at `/etc/sudoers.d/workflow-watchdog` — `workflow` user has NOPASSWD ONLY for the one restart command; no other sudo access.

Check next fire: `sudo systemctl list-timers workflow-watchdog.timer`.

## Row J — State backup (installed by bootstrap)

`hetzner-bootstrap.sh` installs a nightly backup of the `workflow-data`
named Docker volume to Hetzner Storage Box. Bootstrap enables the
timer unconditionally; if Storage Box creds are blank, `backup.sh`
exits 1 with a clear message (so ops sees the wiring but can defer
the Storage Box provisioning).

- **Timer:** `workflow-backup.timer` fires nightly at 03:00 UTC.
- **Script:** `deploy/backup.sh` tars the volume → `zstd` → `rclone` to `storagebox:workflow-backups/workflow-data-<ts>.tar.zst`.
- **Retention:** 7 daily + 4 weekly (override via `BACKUP_RETAIN_*` env vars).
- **Host action needed:** provision a Hetzner Storage Box (BX11 recommended, ~€1/mo), create a dedicated subuser scoped to `/workflow-backups/`, fill `STORAGEBOX_HOST` / `STORAGEBOX_USER` / `STORAGEBOX_PASS` in `/etc/workflow/env`, `sudo systemctl restart workflow-backup.timer`.

Storage Box provisioning (host does this when ready):
1. Hetzner Cloud console → Storage Boxes → Add → BX11 (100 GB, ~€1/mo).
2. Create subuser scoped to `/workflow-backups/`. Copy the SFTP host + subuser credentials.
3. `sudo nano /etc/workflow/env` → fill in the 3 STORAGEBOX_* vars.
4. Manually trigger first backup to verify: `sudo systemctl start workflow-backup.service && sudo journalctl -u workflow-backup -n 50`.
5. On success, 03:00 UTC nightly cadence takes over.

**Restore runbook:** `deploy/RESTORE.md` covers full-volume restore
from a specific tarball. Estimated 5-15 min depending on archive size.

## Row M — CI deploy pipeline (GitHub Actions)

`.github/workflows/deploy-prod.yml` auto-deploys the freshly-published
image on every successful `build-image.yml` run on `main`. SSH to the
DigitalOcean Droplet, pin the new tag in `/etc/workflow/env`, `docker pull`,
`systemctl restart`, run post-deploy canary, auto-rollback on red.

**GitHub secrets required** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DO_DROPLET_HOST` | Droplet public IP (e.g. `161.35.237.133`) or DNS name. |
| `DO_SSH_USER` | SSH user on the Droplet — typically `root` or a dedicated `deploy` user. |
| `DO_SSH_KEY` | Private key PEM (ed25519 recommended). Paste whole contents including BEGIN/END lines. |

Generate the key pair:
```bash
ssh-keygen -t ed25519 -C "gh-actions-deploy" -f ~/.ssh/workflow_deploy -N ""
cat ~/.ssh/workflow_deploy.pub  # add to /root/.ssh/authorized_keys on the Droplet
cat ~/.ssh/workflow_deploy      # paste into DO_SSH_KEY secret
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
deploy ALL=(root) NOPASSWD:/usr/bin/sed -i * /etc/workflow/env
deploy ALL=(root) NOPASSWD:/usr/bin/docker pull *
deploy ALL=(root) NOPASSWD:/usr/bin/systemctl restart workflow-daemon
deploy ALL=(root) NOPASSWD:/usr/bin/grep * /etc/workflow/env
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
- On canary red, auto-rollback to the previous `WORKFLOW_IMAGE` value, re-verify canary, and open a `deploy-failed` GitHub issue with the run URL. Distinct from `p0-outage` (Row H) — deploy-failed = we caused it; p0-outage = daemon died spontaneously.

## Row K — Log aggregation (sidecar in compose)

The `logs` service in `deploy/compose.yml` runs a Vector sidecar that
tails `daemon` + `cloudflared` container stdout via the Docker socket
and forwards events. Two paths:

- **Default (no config):** Vector writes to its own stdout, which
  `docker compose` + journald capture. Equivalent to not running the
  sidecar, but the wiring exists for one-env-flip enable.
- **With Better Stack:** set `BETTERSTACK_SOURCE_TOKEN` in
  `/etc/workflow/env`, `sudo systemctl restart workflow-daemon`.
  Vector starts shipping to `https://in.logs.betterstack.com` with
  `workflow` service + `daemon`/`cloudflared` role metadata on each
  event. Free tier = 3 GB/mo retention.

**Host action (optional — enable Better Stack):**
1. Sign up at betterstack.com (free tier). Create a "Logs" source.
2. Copy the source token.
3. `sudo nano /etc/workflow/env` → fill `BETTERSTACK_SOURCE_TOKEN=...`.
4. `sudo systemctl restart workflow-daemon` (restarts the whole compose stack including the logs sidecar).
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

- **Log source of truth:** `journalctl -u workflow-daemon -f` on the Hetzner box.
- **Canary alarm:** `.github/workflows/uptime-canary.yml` auto-opens a GitHub issue labeled `p0-outage` on 2 consecutive reds. Host gets GitHub email notification.
- **Tunnel dashboard:** `https://dash.cloudflare.com/<acct>/one/networks/connectors` — shows tunnel + connector health.

If canary goes red + persists >10 min AND host isn't responding, the
succession runbook (`SUCCESSION.md` §6.1) applies: admin-pool member
can SSH in + restart or rollback per this runbook.
