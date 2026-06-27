---
title: Log Aggregation Runbook
date: 2026-04-20
row: K (self-host uptime migration)
---

# Log Aggregation Runbook

TinyAssets uses a two-layer logging strategy on the self-hosted Droplet:

| Layer | Tool | What it does |
|-------|------|--------------|
| Real-time forwarding | Vector sidecar (`deploy/vector.yaml`) | Tails `tinyassets-daemon` + `workflow-tunnel` container stdout via Docker socket; ships to Better Stack when `BETTERSTACK_SOURCE_TOKEN` is set; always echoes to compose stdout (journald) |
| Offsite archiving | `deploy/ship-logs.sh` + systemd timer | Pulls last 24 h of container logs, archives as `.tar.gz`, uploads to `LOG_DEST` (Hetzner Storage Box or DO Spaces), prunes archives older than 30 days |

---

## Setup

### 1. Better Stack (optional, recommended)

1. Create a free account at `logs.betterstack.com`.
2. Create a new **Source** → **HTTP** type.
3. Copy the ingest token.
4. Add to `/etc/tinyassets/env`:

```
BETTERSTACK_SOURCE_TOKEN=<your-token>
```

5. Reload the logs sidecar:

```bash
docker compose -f /opt/tinyassets/deploy/compose.yml restart logs
```

Logs from `tinyassets-daemon` and `workflow-tunnel` will appear in Better Stack within seconds.

### 2. Offsite archive via ship-logs.sh

`ship-logs.sh` uses rclone. Configure the same remote as Row J backups (see `docs/ops/backup-restore-runbook.md`).

Add to `/etc/tinyassets/env`:

```
# rclone URL for log archives — can share the same remote as backups
LOG_DEST=sftp:storagebox/workflow-logs
# or for DO Spaces:
# LOG_DEST=s3:workflow-logs/logs
```

Install the systemd units (ship-logs + disk-watch together):

```bash
cp /opt/tinyassets/deploy/tinyassets-ship-logs.service  /etc/systemd/system/
cp /opt/tinyassets/deploy/tinyassets-ship-logs.timer    /etc/systemd/system/
cp /opt/tinyassets/deploy/tinyassets-disk-watch.service /etc/systemd/system/
cp /opt/tinyassets/deploy/tinyassets-disk-watch.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tinyassets-ship-logs.timer tinyassets-disk-watch.timer
```

Verify the timers are scheduled:

```bash
systemctl list-timers tinyassets-ship-logs.timer tinyassets-disk-watch.timer
```

**Disk-watch** (`scripts/disk_watch.py`) fires daily at 04:30 UTC and opens a
`disk-pressure` GH Issue when `/var/lib/docker` exceeds `DISK_WARN_PCT` (default
80%). Requires `GITHUB_TOKEN` in `/etc/tinyassets/env` with `issues: write` scope.
Optional env vars: `DISK_WATCH_PATH`, `DISK_WARN_PCT`, `GITHUB_REPOSITORY`.

---

## Daily Operations

### Query today's logs (live on Droplet)

```bash
# Last hour — daemon only
docker logs tinyassets-daemon --since 1h

# Last 24 h — both services
docker logs tinyassets-daemon --since 24h
docker logs workflow-tunnel --since 24h

# Tail live
docker logs tinyassets-daemon -f
```

### Query via journald (compose captures Vector's stdout)

```bash
# All workflow containers via compose labels
journalctl -u docker -t tinyassets-daemon --since today

# Or via the compose project (if started via systemd)
journalctl -u docker-compose@workflow --since "1 hour ago"
```

### Query from Better Stack

1. Log in at `logs.betterstack.com`.
2. Filter by source or by metadata field `.service = "workflow"`.
3. Use `.role = "daemon"` or `.role = "cloudflared"` to scope to one container.
4. Date-range picker selects the archive window.

Better Stack free tier retains 3 GB / month — sufficient for a single daemon running at normal load.

---

## Pull a Date Range from Offsite Archives

Archives are named `workflow-logs-YYYY-MM-DDTHH-MM-SS.tar.gz` and stored at `LOG_DEST`.

### List available archives

```bash
rclone lsf --format "tp" "${LOG_DEST}/"
```

### Download and inspect a specific archive

```bash
# Download
rclone copyto "${LOG_DEST}/workflow-logs-2026-04-20T02-00-00.tar.gz" /tmp/

# Extract
mkdir /tmp/log-restore
tar -xzf /tmp/workflow-logs-2026-04-20T02-00-00.tar.gz -C /tmp/log-restore

# Inspect
ls /tmp/log-restore/
grep "ERROR" /tmp/log-restore/tinyassets-daemon.log
```

### Pull a date range (multiple archives)

```bash
# List archives between two dates
rclone lsf --format "tp" "${LOG_DEST}/" | grep "2026-04-1[5-9]"

# Download all of them
rclone copy --include "workflow-logs-2026-04-1*.tar.gz" "${LOG_DEST}/" /tmp/log-range/
```

---

## Manual Offsite Push

To trigger an ad-hoc archive (e.g. before a deploy):

```bash
LOG_DEST="${LOG_DEST}" LOG_SINCE=4h bash /opt/tinyassets/deploy/ship-logs.sh
```

Dry-run to confirm env without touching anything:

```bash
DRY_RUN=1 LOG_DEST="${LOG_DEST}" bash /opt/tinyassets/deploy/ship-logs.sh
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No logs in Better Stack | Token not set or wrong | Check `BETTERSTACK_SOURCE_TOKEN` in `/etc/tinyassets/env`; restart `logs` container |
| Vector container not running | Depends-on daemon unhealthy | Check `docker logs workflow-logs`; confirm daemon healthcheck passes |
| ship-logs.sh exits 1 | `LOG_DEST` missing | Set `LOG_DEST` in `/etc/tinyassets/env` |
| rclone upload fails | Remote misconfigured | Run `rclone lsd "${LOG_DEST}/"` to test connectivity |
| Archives not being pruned | Clock skew or naming mismatch | Check archive names match `workflow-logs-YYYY-MM-DDTHH-MM-SS.tar.gz` pattern |
| `docker logs` shows nothing | Container hasn't started | `docker ps -a` to check container state |

---

## Retention Policy

| Storage | Retention | Where |
|---------|-----------|-------|
| Droplet memory (Vector buffer) | In-memory, ~1 000 events | Drops oldest on overflow |
| Better Stack | 3 GB/month (free tier) | Better Stack cloud |
| Offsite archive | 30 days | `LOG_DEST` (Hetzner/DO Spaces) |
| journald (compose stdout) | Disk-size-limited, typically 1–7 days | Droplet local disk |

To adjust offsite retention, set `LOG_RETAIN_DAYS` in `/etc/tinyassets/env`.
