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

1. Validates the selected primary backup's safe archive shape and records its
   archive + representative-member SHA-256 values.
2. Reads only the primary host's final `TINYASSETS_IMAGE` assignment, removes
   at most one matching pair of surrounding quotes, and requires the canonical
   immutable `ghcr.io/jonnyton/tinyassets-daemon@sha256:<digest>` form. It does
   not copy the primary environment or any secrets.
3. Resolves the newest public, available Debian x64 image serving `nyc3` across
   a bounded DigitalOcean distribution-catalog traversal. This first request
   verifies the token's required `image:read` scope before any mutation.
4. Registers the deploy SSH key with the DO API (idempotent by fingerprint).
5. Creates a `tinyassets-dr-drill` Droplet with the resolved Debian image and
   requested size.
6. Waits for the Droplet to get a public IP + SSH to become ready.
7. Runs `deploy/hetzner-bootstrap.sh` on the drill Droplet (Docker, user,
   systemd units, log rotation, swap).
8. Streams the exact validated backup from primary to drill, then requires the
   destination SHA-256 to match before restore.
9. Runs `deploy/backup-restore.sh` with the exact transferred `BACKUP_FILE` and
   verifies the representative member at Docker's inspected volume mountpoint.
10. Supplies the validated runtime image ephemerally, starts only the daemon
   compose service with the fresh template environment, waits 30s, opens an
   SSH port-forward to loopback, and probes `http://localhost:8001/mcp` via
   `scripts/mcp_probe.py status` (no Cloudflare tunnel required).

## Pass / fail criteria

**Pass:** `mcp_probe.py status` exits 0 (MCP initialize + session + `get_status` tool call succeeds).

TinyAssets on pass:
- Confirms destruction of the drill Droplet.
- Appends and commits a timestamped `docs/ops/dr-drill-log.md` entry containing
  the Debian base image and daemon runtime image as distinct fields, plus
  archive/restored-state checksum evidence.

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
TINYASSETS_IMAGE='<runtime-image-from-run-evidence>' \
  docker compose --env-file /etc/tinyassets/env \
  -f /opt/tinyassets/deploy/compose.yml ps

# Tail daemon logs.
TINYASSETS_IMAGE='<runtime-image-from-run-evidence>' \
  docker compose --env-file /etc/tinyassets/env \
  -f /opt/tinyassets/deploy/compose.yml logs daemon --tail 50

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
| `DIGITALOCEAN_TOKEN` | Must include `image:read` plus SSH-key read/create and Droplet create/read/delete permissions. Missing catalog scope fails red before any mutation. |
| `DO_SSH_KEY` | Private key PEM — must be in `authorized_keys` on drill Droplet (cloud-init adds it) |
| `DO_DROPLET_HOST` | Primary Droplet IP — for streaming the backup |
| `DO_SSH_USER` | SSH user on primary (typically `root`) |
