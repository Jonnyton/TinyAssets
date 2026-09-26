#!/usr/bin/env bash
# backup.sh — nightly snapshot of the tinyassets-data named volume.
#
# Self-host migration Row J per
# docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md.
#
# Two tiers per run (2026-06-10 redesign — see
# docs/ops/backup-restore-runbook.md "Two-tier design"):
#
#   1. BRAIN tier (strict): wiki/, daemon_wikis/, top-level ledgers and
#      SQLite DBs, staged to a quiesced temp dir with SQLite files copied
#      through python3's sqlite3 backup API for transactional consistency.
#      Small (MBs). This archive MUST succeed — it carries the
#      irreplaceable knowledge state.
#   2. FULL tier (best-effort): whole-volume tar including multi-GB
#      rebuildable LanceDB indexes, taken live. GNU tar exit 1 ("file
#      changed as we read it") is EXPECTED on a hot volume and tolerated;
#      exit >= 2 is fatal. Before 2026-06-10 this exit-1 case failed the
#      whole unit nightly and silently starved the offsite history.
#   3. LOGS tier (best-effort, added 2026-09-26): a redacted window of the
#      host journal (scripts/backup_log_tier.py). Evidence rather than state
#      — before this, container output existed only inside a container and
#      every deploy that recreated one erased it
#      (found 2026-09-26; docs/ops/log-aggregation-runbook.md). Never fatal: a
#      journal problem must not starve the brain tier.
#
# Retention: 7 daily + 4 weekly + 6 monthly per tier, pruned at the end
# of each run (scripts/backup_prune.py).
#
# Triggered by tinyassets-backup.service (systemd oneshot) from
# tinyassets-backup.timer (nightly 03:00 UTC).
#
# Required env (from /etc/tinyassets/env, sourced by the systemd unit):
#   BACKUP_DEST   rclone destination URL, e.g.:
#                   s3://my-do-spaces-bucket/tinyassets-backups
#                   sftp://u123456.your-storagebox.de/tinyassets-backups
#                 Any rclone remote URL works; rclone must already be
#                 configured for the scheme (see docs/ops/backup-restore-runbook.md).
#
# Optional env:
#   BACKUP_VOLUME          Docker volume name (default: tinyassets-data)
#   BACKUP_RETAIN_DAILY    keep last N daily archives (default: 7)
#   BACKUP_RETAIN_WEEKLY   keep first archive per week, last N weeks (default: 4)
#   BACKUP_RETAIN_MONTHLY  keep first archive per month, last N months (default: 6)
#   DRY_RUN                set to "1" — print plan, no tar/upload/prune
#   BACKUP_LOG             append log to this file (default: /var/log/tinyassets-backup.log)
#   BACKUP_LOG_SINCE       journal window for the logs tier (default: "3 days ago")
#   GH_TOKEN               GitHub token for offsite upload to BACKUP_GH_REPO.
#                          When set, both tarballs are also shipped as GH
#                          release assets.
#   BACKUP_GH_REPO         GitHub repo for offsite releases (default: Jonnyton/tinyassets-backups).
#   BACKUP_GH_RETAIN       GH releases to keep (default: 30).
#
# Exit codes:
#   0  upload + prune succeeded (or DRY_RUN=1 — no mutations).
#   1  BACKUP_DEST not set.
#   2  tar/staging failed (source volume missing, brain stage failed, or
#      full tar exited >= 2).
#   3  rclone upload failed (either tier).
#   4  retention prune failed (non-fatal; uploads themselves succeeded).

set -euo pipefail

BACKUP_VOLUME="${BACKUP_VOLUME:-tinyassets-data}"
BACKUP_RETAIN_DAILY="${BACKUP_RETAIN_DAILY:-7}"
BACKUP_RETAIN_WEEKLY="${BACKUP_RETAIN_WEEKLY:-4}"
BACKUP_RETAIN_MONTHLY="${BACKUP_RETAIN_MONTHLY:-6}"
DRY_RUN="${DRY_RUN:-0}"
BACKUP_LOG="${BACKUP_LOG:-/var/log/tinyassets-backup.log}"

# Docker-internal volume mountpoint. Fall back to `docker volume inspect`
# when Docker uses a non-default storage root.
VOLUME_DIR="/var/lib/docker/volumes/${BACKUP_VOLUME}/_data"

log() {
    # Declared and assigned separately: `local x="$(cmd)"` masks the
    # command's return value in `local`'s own exit status (SC2155).
    local msg
    msg="[backup $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    echo "${msg}"
    echo "${msg}" >> "${BACKUP_LOG}" 2>/dev/null || true
}

# ----- 1. validate env --------------------------------------------------

if [[ "${DRY_RUN}" != "1" ]]; then
    if [[ -z "${BACKUP_DEST:-}" ]]; then
        log "ERROR: BACKUP_DEST is not set"
        log "Set it in /etc/tinyassets/env, e.g.: BACKUP_DEST=s3://my-bucket/tinyassets-backups"
        exit 1
    fi
fi

if [[ "${DRY_RUN}" == "1" ]]; then
    log "DRY_RUN=1 — skipping volume locate, tar, upload, and prune. No mutations."
    log "  BACKUP_DEST=${BACKUP_DEST:-<unset>}"
    log "  BACKUP_VOLUME=${BACKUP_VOLUME}"
    log "  retention: daily=${BACKUP_RETAIN_DAILY} weekly=${BACKUP_RETAIN_WEEKLY} monthly=${BACKUP_RETAIN_MONTHLY}"
    exit 0
fi

# ----- 2. locate volume -------------------------------------------------

if [[ ! -d "${VOLUME_DIR}" ]]; then
    VOLUME_DIR="$(docker volume inspect --format '{{ .Mountpoint }}' "${BACKUP_VOLUME}" 2>/dev/null || echo '')"
    if [[ -z "${VOLUME_DIR}" || ! -d "${VOLUME_DIR}" ]]; then
        log "ERROR: volume ${BACKUP_VOLUME} not found on disk"
        exit 2
    fi
fi

log "source: ${VOLUME_DIR}"
log "dest:   ${BACKUP_DEST}"

TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"

# ----- 3. brain tier — consistent archive of the irreplaceable subset ---

BRAIN_NAME="tinyassets-brain-${TS}.tar.gz"
BRAIN_PATH="/tmp/${BRAIN_NAME}"
BRAIN_STAGE="$(mktemp -d /tmp/tinyassets-brain-stage.XXXXXX)"
trap 'rm -rf "${BRAIN_STAGE}"' EXIT

log "staging brain tier (wiki, daemon_wikis, ledgers, SQLite DBs)..."
for d in wiki daemon_wikis; do
    if [[ -d "${VOLUME_DIR}/${d}" ]]; then
        if ! cp -a "${VOLUME_DIR}/${d}" "${BRAIN_STAGE}/"; then
            log "ERROR: brain stage copy failed: ${d}"
            exit 2
        fi
    fi
done
for f in "${VOLUME_DIR}"/*.json; do
    [[ -f "${f}" ]] && cp -a "${f}" "${BRAIN_STAGE}/"
done
for db in "${VOLUME_DIR}"/*.db; do
    [[ -f "${db}" ]] || continue
    if ! python3 - "${db}" "${BRAIN_STAGE}/$(basename "${db}")" <<'PY'
import sqlite3
import sys

src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
PY
    then
        log "ERROR: consistent sqlite copy failed: $(basename "${db}")"
        exit 2
    fi
done

log "creating brain archive ${BRAIN_PATH}..."
if ! tar -czf "${BRAIN_PATH}" -C "${BRAIN_STAGE}" .; then
    log "ERROR: brain tar failed"
    rm -f "${BRAIN_PATH}"
    exit 2
fi
log "  brain archive size: $(stat -c %s "${BRAIN_PATH}" 2>/dev/null || echo '?') bytes"

log "uploading brain tier to ${BACKUP_DEST}/${BRAIN_NAME}..."
if ! rclone copyto --contimeout 60s --timeout 900s \
        "${BRAIN_PATH}" "${BACKUP_DEST}/${BRAIN_NAME}"; then
    log "ERROR: brain rclone upload failed"
    rm -f "${BRAIN_PATH}"
    exit 3
fi
log "  brain upload OK"

# ----- 4. full tier — whole volume, live (tar exit 1 tolerated) ---------

TAR_NAME="tinyassets-data-${TS}.tar.gz"
TAR_PATH="/tmp/${TAR_NAME}"

log "creating archive ${TAR_PATH}..."
set +e
tar -czf "${TAR_PATH}" --warning=no-file-changed \
    -C "$(dirname "${VOLUME_DIR}")" "$(basename "${VOLUME_DIR}")"
tar_rc=$?
set -e
if [[ "${tar_rc}" -ge 2 ]]; then
    log "ERROR: tar failed (rc=${tar_rc})"
    rm -f "${TAR_PATH}" "${BRAIN_PATH}"
    exit 2
elif [[ "${tar_rc}" -eq 1 ]]; then
    log "  tar rc=1 (files changed during live read) — expected on a hot volume; archive kept (brain tier carries the strict-consistency guarantee)"
fi
TAR_SIZE="$(stat -c %s "${TAR_PATH}" 2>/dev/null || echo '?')"
log "  archive size: ${TAR_SIZE} bytes"

log "uploading to ${BACKUP_DEST}/${TAR_NAME}..."
if ! rclone copyto --contimeout 60s --timeout 900s \
        "${TAR_PATH}" "${BACKUP_DEST}/${TAR_NAME}"; then
    log "ERROR: rclone upload failed"
    rm -f "${TAR_PATH}" "${BRAIN_PATH}"
    exit 3
fi
log "  upload OK"

# ----- 4b. logs tier — recent journal history, redacted (best-effort) ----
#
# The third tier carries evidence rather than state: container output that used
# to live only inside a container and died with every deploy that recreated it
# (found 2026-09-26; docs/ops/log-aggregation-runbook.md). compose.yml now points
# the Vector sidecar at the journald driver, so the history is on the host; this
# puts a redacted window of it OFF the host, on the credential the nightly
# backup already holds. No new vendor, no new secret.
#
# Strictly best-effort and deliberately non-fatal: a journal problem must never
# starve the brain archive, which is the irreplaceable tier. The script exits 3
# for "no journal to read" so this can tell a skipped tier from a real failure,
# and either way the backup's own exit code is unchanged.

LOGS_NAME="tinyassets-logs-${TS}.tar.gz"
LOGS_PATH="/tmp/${LOGS_NAME}"
LOG_TIER_SCRIPT="$(dirname "$(realpath "$0")")/../scripts/backup_log_tier.py"
BACKUP_LOG_SINCE="${BACKUP_LOG_SINCE:-3 days ago}"
logs_tier_built=0

log "building logs tier (journal since '${BACKUP_LOG_SINCE}', redacted)..."
set +e
python3 "${LOG_TIER_SCRIPT}" --out "${LOGS_PATH}" --since "${BACKUP_LOG_SINCE}" \
    2>&1 | while IFS= read -r line; do log "  ${line}"; done
logs_tier_status="${PIPESTATUS[0]}"
set -e
if [[ "${logs_tier_status}" -eq 0 && -f "${LOGS_PATH}" ]]; then
    logs_tier_built=1
    log "  logs archive size: $(stat -c %s "${LOGS_PATH}" 2>/dev/null || echo '?') bytes"
    log "uploading logs tier to ${BACKUP_DEST}/${LOGS_NAME}..."
    if ! rclone copyto --contimeout 60s --timeout 900s \
            "${LOGS_PATH}" "${BACKUP_DEST}/${LOGS_NAME}"; then
        log "WARN: logs tier rclone upload failed (state tiers already uploaded)"
    else
        log "  logs upload OK"
    fi
elif [[ "${logs_tier_status}" -eq 3 ]]; then
    log "WARN: no readable journal — logs tier skipped (state tiers unaffected)"
else
    log "WARN: logs tier exited ${logs_tier_status} — skipped (state tiers unaffected)"
fi

# ----- 5. offsite upload (GH release assets) ----------------------------
# Best-effort; failure is non-fatal so local backup still counts as done.
# Activated only when GH_TOKEN is set. Ships every tier that was built.

SHIP_SCRIPT="$(dirname "$(realpath "$0")")/../scripts/backup_ship_gh.py"
SHIP_PATHS=("${TAR_PATH}" "${BRAIN_PATH}")
if [[ "${logs_tier_built}" -eq 1 ]]; then
    SHIP_PATHS+=("${LOGS_PATH}")
fi
if [[ -n "${GH_TOKEN:-}" ]]; then
    for ship_path in "${SHIP_PATHS[@]}"; do
        log "shipping $(basename "${ship_path}") to GitHub releases (${BACKUP_GH_REPO:-Jonnyton/tinyassets-backups})..."
        set +e
        python3 "${SHIP_SCRIPT}" "${ship_path}" 2>&1 | while IFS= read -r line; do
            log "  gh-ship: ${line}"
        done
        ship_status=$?
        set -e
        if [[ "${ship_status}" -ne 0 ]]; then
            log "WARN: GH offsite ship exited ${ship_status} for $(basename "${ship_path}") (local backup succeeded)"
        fi
    done
else
    log "GH_TOKEN not set — skipping offsite GH release upload"
fi

rm -f "${TAR_PATH}" "${BRAIN_PATH}" "${LOGS_PATH}"

# ----- 6. retention prune ----------------------------------------------

# Keep, per tier prefix (tinyassets-data-, tinyassets-brain-):
#   - last BACKUP_RETAIN_DAILY daily archives (most recent N)
#   - first archive of each week for last BACKUP_RETAIN_WEEKLY weeks
#   - first archive of each month for last BACKUP_RETAIN_MONTHLY months
# Prune is best-effort; failure is non-fatal. backup_prune.py only ever
# emits names matching the tier prefixes — unknown files at the
# destination are never deleted.
#
# Python replaces awk here: mawk (Debian default) lacks the 3-arg match()
# and gensub() extensions used by GNU awk. Python 3 is guaranteed present
# on the droplet (disk_watch.py depends on it).
log "pruning retention (daily=${BACKUP_RETAIN_DAILY} weekly=${BACKUP_RETAIN_WEEKLY} monthly=${BACKUP_RETAIN_MONTHLY})..."
PRUNE_SCRIPT="$(dirname "$(realpath "$0")")/../scripts/backup_prune.py"
set +e
set +o pipefail
# rclone lsf default output is filename-per-line — no --format flag needed
# (prior --format n was invalid; 'n' isn't a valid format char and made
# rclone exit 1, which pipefail propagated → systemd marked service failed).
rclone lsf "${BACKUP_DEST}/" 2>/dev/null \
    | python3 "${PRUNE_SCRIPT}" \
        --keep-daily "${BACKUP_RETAIN_DAILY}" \
        --keep-weekly "${BACKUP_RETAIN_WEEKLY}" \
        --keep-monthly "${BACKUP_RETAIN_MONTHLY}" \
    | while read -r victim; do
        log "  prune: ${victim}"
        rclone deletefile "${BACKUP_DEST}/${victim}" || \
            log "    WARN: delete failed for ${victim}"
    done
prune_status=$?
set -eo pipefail

if [[ "${prune_status}" -ne 0 ]]; then
    log "WARN: retention prune exited ${prune_status} (backup itself succeeded)"
    exit 4
fi

log "backup complete."
exit 0
