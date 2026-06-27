# DR Drill Runbook

## When to run

- **Quarterly** — standing cadence to confirm backup → restore → probe chain works.
- **After major changes** to `deploy/compose.yml`, `deploy/hetzner-bootstrap.sh`,
  or `deploy/backup-restore.sh`.
- **After any restore event** — drill confirms the restored state is healthy before
  closing the incident.

## How to trigger

GitHub → Actions → `DR drill` → Run workflow.

Inputs:

| Input | Default | Notes |
|---|---|---|
| `drill_droplet_size` | `s-2vcpu-2gb` | Minimum tested size for apt + Docker bootstrap; `s-1vcpu-1gb` OOMs. |
| `backup_source` | (latest on primary) | Override with a specific path, e.g. `2026-04-01` tarball for point-in-time test. |
| `destroy_on_failure` | `false` | Set `true` to auto-destroy on failure; default keeps the Droplet up for inspection. |

## What the workflow does

1. Registers the deploy SSH key with the DO API (idempotent by fingerprint).
2. Creates a `workflow-dr-drill` Droplet (Debian 12, specified size, `nyc3`).
3. Waits for the Droplet to get a public IP + SSH to become ready.
4. Runs `deploy/hetzner-bootstrap.sh` on the drill Droplet (Docker, user, systemd units, log-rotation, swap).
5. Streams the backup tarball from the primary Droplet directly to the drill Droplet.
6. Runs `deploy/backup-restore.sh` on the drill Droplet.
7. Starts `docker compose up -d`, waits 30s.
8. Opens an SSH port-forward to the drill Droplet's loopback port, then probes `http://localhost:8001/mcp` via `scripts/mcp_probe.py status` (no Cloudflare tunnel required).

## Pass / fail criteria

**Pass:** `mcp_probe.py status` exits 0 (MCP initialize + session + `get_status` tool call succeeds).

TinyAssets on pass:
- Appends a timestamped entry to `docs/ops/dr-drill-log.md` + commits.
- Destroys the drill Droplet.

**Fail:** `mcp_probe.py` exits non-zero.

TinyAssets on fail:
- Opens a `dr-failed` GitHub issue with the probe output + Droplet IP.
- Leaves the drill Droplet **running** for inspection (SSH directly with the deploy key).
- Does NOT destroy unless `destroy_on_failure=true`.

## Inspecting a failed drill

```bash
# SSH to the drill Droplet (IP is in the dr-failed issue).
ssh root@<drill-ip>

# Check compose status.
docker compose -f /opt/tinyassets/deploy/compose.yml ps

# Tail daemon logs.
docker compose -f /opt/tinyassets/deploy/compose.yml logs daemon --tail 50

# Probe locally.
curl -s -X POST http://127.0.0.1:8001/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1.0"}}}'
```

When done:
```bash
doctl compute droplet delete <droplet-id> --force
```

## Required secrets

Same set as `deploy-prod.yml`:

| Secret | Purpose |
|---|---|
| `DIGITALOCEAN_TOKEN` | Create + destroy Droplets via DO API |
| `DO_SSH_KEY` | Private key PEM — must be in `authorized_keys` on drill Droplet (cloud-init adds it) |
| `DO_DROPLET_HOST` | Primary Droplet IP — for streaming the backup |
| `DO_SSH_USER` | SSH user on primary (typically `root`) |
