#!/usr/bin/env bash
# backup-restore.sh — restore tinyassets-data from a remote snapshot.
#
# Self-host migration Row J per
# docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md.
#
# Pulls a named (or latest) archive from the rclone remote and restores
# it into the tinyassets-data Docker named volume. Stops the daemon before
# restore and restarts it after.
#
# Usage:
#   sudo bash deploy/backup-restore.sh                     # latest archive
#   sudo bash deploy/backup-restore.sh --timestamp=2026-04-20T02-00-00Z
#   sudo bash deploy/backup-restore.sh --list              # list available
#   DRY_RUN=1 sudo bash deploy/backup-restore.sh           # show plan only
#
# Required env (same as backup.sh — from /etc/tinyassets/env):
#   BACKUP_DEST   rclone destination URL (same value used by backup.sh)
#
# Optional env:
#   BACKUP_VOLUME    Docker volume name (default: tinyassets-data)
#   DRY_RUN          "1" to skip all mutations
#   BACKUP_LOG       log file path (default: /var/log/tinyassets-backup.log)
#
# Exit codes:
#   0  restore complete (or DRY_RUN=1). Data is extracted; caller is
#      responsible for starting the daemon (normally `docker compose up
#      -d daemon` or `systemctl restart tinyassets-daemon`). The restore
#      script intentionally does NOT start services — the DR drill
#      workflow's dedicated "Start compose on drill Droplet" step owns
#      that with full retry + probe logic, and coupling them here caused
#      the drill to abort early in the 2026-04-22 rehearsal.
#   1  config missing or bad arguments.
#   2  archive not found on remote.
#   3  rclone download failed.
#   4  tar extract failed.
#   5  RESERVED — legacy code emitted this when the in-script daemon
#      restart failed. No longer used; kept in the exit-code doc so
#      older callers checking for 5 don't regress silently.

set -euo pipefail

BACKUP_VOLUME="${BACKUP_VOLUME:-tinyassets-data}"
DRY_RUN="${DRY_RUN:-0}"
BACKUP_LOG="${BACKUP_LOG:-/var/log/tinyassets-backup.log}"

TIMESTAMP_ARG=""
LIST_MODE=0

for arg in "$@"; do
    case "${arg}" in
        --timestamp=*) TIMESTAMP_ARG="${arg#--timestamp=}" ;;
        --list)        LIST_MODE=1 ;;
        *) echo "Unknown argument: ${arg}" >&2; exit 1 ;;
    esac
done

log() {
    local msg="[restore $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    echo "${msg}"
    echo "${msg}" >> "${BACKUP_LOG}" 2>/dev/null || true
}

# ----- 1. validate env --------------------------------------------------

if [[ -z "${BACKUP_DEST:-}" ]]; then
    log "ERROR: BACKUP_DEST is not set"
    log "Set it in /etc/tinyassets/env, e.g.: BACKUP_DEST=s3://my-bucket/tinyassets-backups"
    exit 1
fi

# ----- 2. list mode -----------------------------------------------------

if [[ "${LIST_MODE}" -eq 1 ]]; then
    log "available archives at ${BACKUP_DEST}:"
    rclone lsf --format tp "${BACKUP_DEST}/" 2>/dev/null \
        | sort -r \
        | awk -F';' '{print "  " $2}'
    exit 0
fi

# ----- 3. resolve archive -----------------------------------------------

if [[ -n "${TIMESTAMP_ARG}" ]]; then
    TAR_NAME="tinyassets-data-${TIMESTAMP_ARG}.tar.gz"
else
    TAR_NAME="$(rclone lsf --format tp "${BACKUP_DEST}/" 2>/dev/null \
        | sort -r \
        | awk -F';' 'NR==1 {print $2}')"
    if [[ -z "${TAR_NAME}" ]]; then
        log "ERROR: no archives found at ${BACKUP_DEST}/"
        exit 2
    fi
fi

log "target archive: ${TAR_NAME}"

# Verify it exists on remote.
if ! rclone ls "${BACKUP_DEST}/${TAR_NAME}" > /dev/null 2>&1; then
    log "ERROR: archive not found: ${BACKUP_DEST}/${TAR_NAME}"
    exit 2
fi

if [[ "${DRY_RUN}" == "1" ]]; then
    log "DRY_RUN=1 — would restore ${TAR_NAME} into volume ${BACKUP_VOLUME}. No mutations."
    exit 0
fi

# ----- 4. stop daemon ---------------------------------------------------

log "stopping tinyassets-daemon..."
docker stop tinyassets-daemon 2>/dev/null || log "  daemon was not running"

# ----- 5. download archive ----------------------------------------------

TAR_PATH="/tmp/${TAR_NAME}"
log "downloading ${TAR_NAME}..."
if ! rclone copyto --contimeout 60s --timeout 900s \
        "${BACKUP_DEST}/${TAR_NAME}" "${TAR_PATH}"; then
    log "ERROR: rclone download failed"
    exit 3
fi
log "  download OK ($(stat -c %s "${TAR_PATH}" 2>/dev/null || echo '?') bytes)"

# ----- 6. locate / create volume ----------------------------------------

VOLUME_DIR="/var/lib/docker/volumes/${BACKUP_VOLUME}/_data"
if [[ ! -d "${VOLUME_DIR}" ]]; then
    VOLUME_DIR="$(docker volume inspect --format '{{ .Mountpoint }}' "${BACKUP_VOLUME}" 2>/dev/null || echo '')"
    if [[ -z "${VOLUME_DIR}" ]]; then
        log "  volume ${BACKUP_VOLUME} not found; creating..."
        docker volume create "${BACKUP_VOLUME}" >/dev/null
        VOLUME_DIR="$(docker volume inspect --format '{{ .Mountpoint }}' "${BACKUP_VOLUME}")"
    fi
fi

log "restoring into ${VOLUME_DIR}..."

# ----- 7. extract -------------------------------------------------------

rm -rf "${VOLUME_DIR:?}/"*

if ! tar -xzf "${TAR_PATH}" -C "$(dirname "${VOLUME_DIR}")" \
        --strip-components=1 "$(basename "${VOLUME_DIR}")"; then
    log "ERROR: tar extract failed"
    rm -f "${TAR_PATH}"
    exit 4
fi

rm -f "${TAR_PATH}"
log "  extract OK"

# ----- 7b. vault anti-rollback guard ------------------------------------
#
# A restored data volume is by definition a rollback of the credential
# vault's recovery domain. Advance the external epoch guard so EVERY vault
# operation fails closed into whole-store re-authorization — intended
# behavior, not an error: a restored one-use refresh token may already
# have been redeemed at the provider, so serving restored credentials
# would be dishonest. scripts/vault_restore_bump.py bumps through the
# backend's OWN identity-derived epoch guard (never a raw store_id, which
# would silently target the wrong guard row). The guard volume is the
# persistent NON-/data tinyassets-vault-guard volume (see compose.yml).
DAEMON_IMAGE="$(docker inspect tinyassets-daemon --format '{{.Config.Image}}' 2>/dev/null || echo "${TINYASSETS_IMAGE:-}")"
if [[ -n "${DAEMON_IMAGE}" ]]; then
    log "advancing vault anti-rollback guard..."
    if docker run --rm \
            -e TINYASSETS_DATA_DIR=/data \
            -e TINYASSETS_VAULT_ROLLBACK_GUARD=/vault-guard \
            -v "${BACKUP_VOLUME}:/data" \
            -v tinyassets-vault-guard:/vault-guard \
            "${DAEMON_IMAGE}" \
            python /app/scripts/vault_restore_bump.py; then
        log "  vault guard advanced — credentials now require re-authorization (intended)"
    else
        log "ERROR: vault guard bump failed; restored credentials cannot be"
        log "  proven invalidated. Refusing to report a usable restore."
        exit 6
    fi
else
    log "ERROR: no daemon image found for the mandatory vault guard bump."
    log "  Refusing to report a usable restore."
    exit 6
fi

# ----- 8. done — caller starts the daemon -------------------------------
#
# Restore's job is to put the data in the right place. Starting the
# daemon is the caller's responsibility. This separation is load-bearing
# for the DR drill: the drill's dedicated "Start compose on drill
# Droplet" step owns start + retry + probe. Coupling them caused the
# 2026-04-22 drill to abort at step 13 because cloudflared couldn't
# initialize without a real CLOUDFLARE_TUNNEL_TOKEN — the daemon itself
# was perfectly capable of starting.

log "restore complete. Data extracted into ${VOLUME_DIR}."
log "NEXT — start the daemon via one of:"
log "  docker compose -f /opt/tinyassets/deploy/compose.yml up -d daemon"
log "  systemctl restart tinyassets-daemon"
exit 0
