---
title: Log Aggregation Runbook
date: 2026-04-20
row: K (self-host uptime migration)
---

# Log Aggregation Runbook

TinyAssets uses a three-layer logging strategy on the self-hosted Droplet:

| Layer | Tool | What it does |
|-------|------|--------------|
| Collection | Vector sidecar (`deploy/vector.yaml`) | Receives daemon, tunnel, and slack-agent stdout from Docker's async Fluent driver on host-loopback port 24224; has no Docker socket; re-emits everything on its own stdout |
| Durable, on-box | the host journal | The `logs` container uses the `journald` driver (`deploy/compose.yml`), so Vector's re-emitted stream is journal data and **survives container recreates**. Retention: `deploy/journald-tinyassets.conf`, installed by the host-uptime installer |
| Off-box | logs tier of the nightly backup (`scripts/backup_log_tier.py`) | A redacted 3-day window of the journal, shipped as `tinyassets-logs-*.tar.gz` beside the state tiers — same destination, same credential |
| Real-time (optional) | Better Stack | Vector also ships live when `BETTERSTACK_SOURCE_TOKEN` is set |

**Why the journal is the durable layer (2026-09-26).** It used to be the `logs`
container's own json-file, which lives under
`/var/lib/docker/containers/<id>/` and is deleted with the container. Every
deploy recreates the daemon, and `deploy/deploy_fail_safe.sh` force-recreates
`tinyassets-logs` whenever a Vector input changes. On 2026-09-26 a live latency
investigation needed the per-attempt `latency_ms` lines from turns six minutes
earlier and they no longer existed anywhere
(filed and resolved 2026-09-26; the concern file is deleted, per the
`docs/concerns/` convention that resolving one deletes it -- recover it with
`git log --diff-filter=D -- docs/concerns/2026-09-26-daemon-logs-not-shipped.md`).

**`tinyassets-ship-logs` is retired** (2026-09-26). It required `LOG_DEST` — a
destination plus a credential nobody had set — and logged
`ERROR: LOG_DEST is required` hourly for months. Setting it would not have
helped: it collected with `docker logs`, which Docker refuses on a container
using the fluentd driver. The installer removes the units from the host
(`RETIRED_UNITS` in `deploy/install-host-uptime-services.sh`).

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

Logs from the daemon, tunnel, and workers will appear in Better Stack within seconds.

### 2. Journal retention (no host action — the installer owns it)

`deploy/journald-tinyassets.conf` is installed to
`/etc/systemd/journald.conf.d/tinyassets.conf` by
`deploy/install-host-uptime-services.sh`, which runs after every successful
production deploy and restarts `systemd-journald` only when the bytes changed.
`Storage=persistent`, `SystemMaxUse=1G`, `MaxRetentionSec=14day`,
`SystemKeepFree=2G`, rate limiting off.

Confirm it is live:

```bash
journalctl --disk-usage
systemctl show systemd-journald --property=FragmentPath >/dev/null && \
  cat /etc/systemd/journald.conf.d/tinyassets.conf
```

### 3. Off-box log archive (no extra credential)

The nightly `tinyassets-backup.timer` builds a third tier beside the brain and
full tiers: `scripts/backup_log_tier.py` queries the journal, pipes every line
through `scripts/redact_log_bundle.py`, and tars the result as
`tinyassets-logs-<TS>.tar.gz`. It goes to `BACKUP_DEST` and to the same private
`Jonnyton/tinyassets-backups` release repo as the state tiers.

It is deliberately best-effort — a journal problem must never starve the brain
tier — so every failure is a `WARN` in `/var/log/tinyassets-backup.log` and the
backup's own exit code is unchanged. Override the window with
`BACKUP_LOG_SINCE` (default `3 days ago`).

Install the disk-watch units:

```bash
cp /opt/tinyassets/deploy/tinyassets-disk-watch.service /etc/systemd/system/
cp /opt/tinyassets/deploy/tinyassets-disk-watch.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tinyassets-disk-watch.timer
```

Verify the timers are scheduled:

```bash
systemctl list-timers tinyassets-backup.timer tinyassets-disk-watch.timer
```

**Disk-watch** (`scripts/disk_watch.py`) fires hourly at minute27 (also shortly
after boot) and opens a `disk-pressure` GH Issue when the verified image-store
filesystem reaches `DISK_WARN_PCT` (default
80%). Requires `GITHUB_TOKEN` in `/etc/tinyassets/env` with `issues: write` scope.
Optional env vars: `DISK_WATCH_PATH`, `DISK_WARN_PCT`, `GITHUB_REPOSITORY`.

Both automatic cleanup services use bounded daemon-image retention, not system,
builder, journal, volume or container cleanup. The compatibility command
`python3 scripts/disk_autoprune.py` defaults to dry-run; both `--apply` and exact
`TINYASSETS_DAEMON_IMAGE_RETENTION_APPLY=1` are required for exact non-force removals
after all protection/recovery checks. Timer installation alone cannot enable it.
Run the helper directly for acceptance: the chained service also runs ordinary
transcript rotation, which this flag does not affect. Containerd image
storage needs an operator-verified `TINYASSETS_IMAGE_RETENTION_STORAGE_PATH`.
See the [retention rollout checklist](../../openspec/changes/archive/2026-09-19-daemon-image-retention/operator-acceptance.md)
before installing or activating the updated cleanup units. Unknown mapping or
protected-image evidence is a refusal, not permission for broad prune.

---

## Daily Operations

### Query today's logs (live on Droplet)

```bash
# Vector's local forwarded stream (daemon, tunnel, and workers)
docker logs tinyassets-logs --since 1h
docker logs tinyassets-logs -f
```

### Query via journald — this is the one that survives a deploy

```bash
# Every forwarded line from every container, across past container recreates.
journalctl CONTAINER_NAME=tinyassets-logs --since "1 hour ago"

# Microsecond timestamps — needed for per-attempt latency evidence.
journalctl CONTAINER_NAME=tinyassets-logs --output=short-iso-precise \
  --since "2026-09-26 18:10" --until "2026-09-26 18:20"

# One originating container: the JSON payload carries Vector's `tag`/`role`.
journalctl CONTAINER_NAME=tinyassets-logs -o cat | grep '"role":"daemon"'

# The systemd unit that runs compose — the supervisor's own output, NOT the
# containers' (`docker compose up -d` detaches).
journalctl -u tinyassets-daemon --since "1 hour ago"
```

`docker logs tinyassets-logs` also still works, because journald is a readable
driver — but it is scoped to the current container, so prefer `journalctl` when
the question spans a deploy.

### Query from Better Stack

1. Log in at `logs.betterstack.com`.
2. Filter by source or by metadata field `.service = "tinyassets"`.
3. Use `.role = "daemon"` or `.role = "cloudflared"` to scope to one container.
4. Date-range picker selects the archive window.

Better Stack free tier retains 3 GB / month — sufficient for a single daemon running at normal load.

---

## Pull a Date Range from Offsite Archives

Bundles are named `tinyassets-logs-<TS>.tar.gz` and each holds one `.log` per
journal source plus `manifest.tsv` (source, file, line count, status). A `status`
of `empty` or `error:` is how a source that stopped producing stays visible.

### From the GitHub release repo (no rclone remote needed)

```bash
gh release list --repo Jonnyton/tinyassets-backups | grep tinyassets-logs-
gh release download tinyassets-logs-2026-09-26T03-00-00Z \
  --repo Jonnyton/tinyassets-backups --dir /tmp
mkdir -p /tmp/log-restore && tar -xzf /tmp/tinyassets-logs-*.tar.gz -C /tmp/log-restore
cat /tmp/log-restore/manifest.tsv
grep -i error /tmp/log-restore/container-tinyassets-logs.log
```

### From the rclone destination

```bash
rclone lsf "${BACKUP_DEST}/" | grep '^tinyassets-logs-'
rclone copyto "${BACKUP_DEST}/tinyassets-logs-2026-09-26T03-00-00Z.tar.gz" /tmp/
```

Every line in a bundle has passed `scripts/redact_log_bundle.py`. Treat a bundle
as sensitive anyway — it is operational detail about real users' turns, just not
credential material.

---

## Manual Off-box Push

To build an ad-hoc bundle (e.g. before a deploy, to keep the evidence a deploy
would otherwise age out):

```bash
python3 /opt/tinyassets-host-uptime/current/scripts/backup_log_tier.py \
  --out /tmp/tinyassets-logs-manual.tar.gz --since '6 hours ago'
```

Exit 3 means "no journal to read" — a skipped tier, not a failure. Then ship it
with the same credential the nightly backup uses:

```bash
GH_TOKEN="${GH_TOKEN}" python3 \
  /opt/tinyassets-host-uptime/current/scripts/backup_ship_gh.py \
  /tmp/tinyassets-logs-manual.tar.gz
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No logs in Better Stack | Token not set or wrong | Check `BETTERSTACK_SOURCE_TOKEN` in `/etc/tinyassets/env`; restart `logs` container |
| Vector container not running | Depends-on daemon unhealthy | Check `docker logs tinyassets-logs`; confirm daemon healthcheck passes. While it is down the fluentd driver buffers in memory and then **drops** — the journal gets nothing, so fix this first |
| `journalctl CONTAINER_NAME=tinyassets-logs` is empty | The `logs` container is not on the journald driver (compose drift) | `docker inspect -f '{{.HostConfig.LogConfig.Type}}' tinyassets-logs` must print `journald`; if not, the deployed compose.yml is behind `deploy/compose.yml` |
| Journal history shorter than 14 days | Drop-in missing, or `SystemMaxUse` hit | `cat /etc/systemd/journald.conf.d/tinyassets.conf`; `journalctl --disk-usage`. Absent drop-in means the installer has not run since the change landed |
| Journal empties on reboot | `Storage` is not persistent | `/var/log/journal` must exist; the drop-in sets `Storage=persistent` and journald creates it on restart |
| `WARN: no readable journal — logs tier skipped` | `journalctl` unavailable to the backup unit | It runs as root from `tinyassets-backup.service`; check the unit's `journalctl --version` |
| Logs tier says `no log source produced any lines` | The collection path is broken, not quiet | Work back up the chain: journald driver → Vector up → fluentd listener on 127.0.0.1:24224 |
| Bundles not being pruned | Name outside the tier pattern | Names must match `tinyassets-logs-<digit>...tar.gz`; both pruners ignore names they do not recognise, by design |
| `docker logs` shows nothing | Container hasn't started | `docker ps -a` to check container state |

---

## Retention Policy

| Storage | Retention | Where |
|---------|-----------|-------|
| Docker fluentd driver buffer | In-memory; **drops** while Vector is down (`docs/concerns/2026-09-26-fluentd-driver-drops-while-vector-is-down.md`) | Not durable, never evidence |
| **host journal** | **1 G / 14 days, persistent** (`deploy/journald-tinyassets.conf`) | Droplet local disk, survives container recreates |
| Off-box log bundles | per-tier daily/weekly/monthly at `BACKUP_DEST`; 45-release pool in the GitHub repo | `deploy/backup.sh` tier 3 |
| Better Stack | 3 GB/month (free tier) | Better Stack cloud |

Journal retention is `deploy/journald-tinyassets.conf` — change it there, not on
the box, or the next install reverts it. Bundle retention follows the other
backup tiers: `BACKUP_RETAIN_DAILY/WEEKLY/MONTHLY` at the rclone destination and
`BACKUP_GH_RETAIN` for releases. The GitHub pool is shared across all three
tiers, so its default is 45 (15 nights x 3 tiers), not 30.
