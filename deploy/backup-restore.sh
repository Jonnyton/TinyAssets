#!/usr/bin/env bash
# backup-restore.sh — stage and restore tinyassets-data from a full snapshot.
#
# The script restores data only. It stops containers that mount the selected
# volume, but it never starts services; the caller owns startup and health
# verification after inspecting the retained pre-restore directory.
#
# Usage:
#   sudo bash deploy/backup-restore.sh
#   sudo bash deploy/backup-restore.sh --timestamp=2026-04-20T02-00-00Z
#   sudo bash deploy/backup-restore.sh --list
#   BACKUP_FILE=/tmp/tinyassets-data-....tar.gz sudo bash deploy/backup-restore.sh
#   DRY_RUN=1 sudo bash deploy/backup-restore.sh
#
# Required for remote mode:
#   BACKUP_DEST      rclone destination used by backup.sh
#
# Optional:
#   BACKUP_FILE      absolute, readable non-symlink local full archive; bypasses rclone
#   BACKUP_VOLUME    Docker volume name (default: tinyassets-data)
#   DRY_RUN          "1" to skip all mutations
#   BACKUP_LOG       log file (default: /var/log/tinyassets-backup.log)
#
# Exit codes:
#   0  restore complete (or DRY_RUN=1); caller starts services
#   1  configuration, argument, path, or lock failure
#   2  archive not found
#   3  remote download failed
#   4  archive validation, extraction, stop, or swap failed
#   5  reserved legacy restart failure; never emitted

set -euo pipefail

BACKUP_VOLUME="${BACKUP_VOLUME:-tinyassets-data}"
BACKUP_FILE="${BACKUP_FILE:-}"
DRY_RUN="${DRY_RUN:-0}"
BACKUP_LOG="${BACKUP_LOG:-/var/log/tinyassets-backup.log}"

TIMESTAMP_ARG=""
LIST_MODE=0
DOWNLOAD_DIR=""
STAGE_DIR=""
VOLUME_PARENT=""

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

cleanup() {
    if [[ -n "${STAGE_DIR}" && -d "${STAGE_DIR}" ]]; then
        case "${STAGE_DIR}" in
            "${VOLUME_PARENT}"/.tinyassets-restore-stage.*)
                rm -rf -- "${STAGE_DIR}"
                ;;
            *)
                log "ERROR: refusing to clean unexpected stage path ${STAGE_DIR}"
                ;;
        esac
    fi
    if [[ -n "${DOWNLOAD_DIR}" && -d "${DOWNLOAD_DIR}" ]]; then
        case "${DOWNLOAD_DIR}" in
            "${TMPDIR:-/tmp}"/.tinyassets-restore-download.*)
                rm -rf -- "${DOWNLOAD_DIR}"
                ;;
            *)
                log "ERROR: refusing to clean unexpected download path ${DOWNLOAD_DIR}"
                ;;
        esac
    fi
}
trap cleanup EXIT

if [[ ! "${BACKUP_VOLUME}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    log "ERROR: invalid Docker volume name ${BACKUP_VOLUME}"
    exit 1
fi

is_full_archive_name() {
    [[ "$1" =~ ^tinyassets-data-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z[.]tar[.]gz$ ]]
}

# ----- 1. select local or remote source --------------------------------

if [[ -n "${BACKUP_FILE}" ]]; then
    if [[ "${LIST_MODE}" -eq 1 || -n "${TIMESTAMP_ARG}" ]]; then
        log "ERROR: BACKUP_FILE cannot be combined with --list or --timestamp"
        exit 1
    fi
    if [[ "${BACKUP_FILE}" != /* || -L "${BACKUP_FILE}" \
            || ! -f "${BACKUP_FILE}" || ! -r "${BACKUP_FILE}" ]]; then
        log "ERROR: BACKUP_FILE must be an absolute readable non-symlink regular file"
        exit 2
    fi
    TAR_PATH="${BACKUP_FILE}"
    TAR_NAME="$(basename "${BACKUP_FILE}")"
    log "target local archive: ${TAR_PATH}"
else
    if [[ -z "${BACKUP_DEST:-}" ]]; then
        log "ERROR: BACKUP_DEST is not set"
        log "Set it in /etc/tinyassets/env or set absolute BACKUP_FILE."
        exit 1
    fi

    if [[ "${LIST_MODE}" -eq 1 ]]; then
        log "available full archives at ${BACKUP_DEST}:"
        rclone lsf --format tp "${BACKUP_DEST}/" 2>/dev/null \
            | awk -F';' '$2 ~ /^tinyassets-data-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z[.]tar[.]gz$/ {print "  " $2}' \
            | sort -r
        exit 0
    fi

    if [[ -n "${TIMESTAMP_ARG}" ]]; then
        if [[ ! "${TIMESTAMP_ARG}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z$ ]]; then
            log "ERROR: invalid UTC backup timestamp ${TIMESTAMP_ARG}"
            exit 1
        fi
        TAR_NAME="tinyassets-data-${TIMESTAMP_ARG}.tar.gz"
    else
        TAR_NAME="$(
            rclone lsf --format tp "${BACKUP_DEST}/" 2>/dev/null \
                | awk -F';' '$2 ~ /^tinyassets-data-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z[.]tar[.]gz$/ {print $2}' \
                | sort -r \
                | awk 'NR==1 {print}'
        )"
        if [[ -z "${TAR_NAME}" ]]; then
            log "ERROR: no full-volume archives found at ${BACKUP_DEST}/"
            exit 2
        fi
    fi
    if ! is_full_archive_name "${TAR_NAME}"; then
        log "ERROR: unsafe or non-full archive name ${TAR_NAME}"
        exit 2
    fi

    log "target remote archive: ${TAR_NAME}"
    if ! rclone ls "${BACKUP_DEST}/${TAR_NAME}" > /dev/null 2>&1; then
        log "ERROR: archive not found: ${BACKUP_DEST}/${TAR_NAME}"
        exit 2
    fi

    if [[ "${DRY_RUN}" == "1" ]]; then
        log "DRY_RUN=1 — would restore ${TAR_NAME} into volume ${BACKUP_VOLUME}. No mutations."
        exit 0
    fi

    DOWNLOAD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/.tinyassets-restore-download.XXXXXX")"
    TAR_PATH="${DOWNLOAD_DIR}/${TAR_NAME}"
    log "downloading ${TAR_NAME}..."
    if ! rclone copyto --contimeout 60s --timeout 900s \
            "${BACKUP_DEST}/${TAR_NAME}" "${TAR_PATH}"; then
        log "ERROR: rclone download failed"
        exit 3
    fi
    log "  download OK ($(stat -c %s "${TAR_PATH}" 2>/dev/null || echo '?') bytes)"
fi

if [[ "${DRY_RUN}" == "1" ]]; then
    log "DRY_RUN=1 — would restore ${TAR_NAME} into volume ${BACKUP_VOLUME}. No mutations."
    exit 0
fi

# ----- 2. resolve and guard the Docker volume --------------------------

VOLUME_DIR="$(
    docker volume inspect --format '{{ .Mountpoint }}' "${BACKUP_VOLUME}" \
        2>/dev/null || true
)"
if [[ -z "${VOLUME_DIR}" ]]; then
    log "  volume ${BACKUP_VOLUME} not found; creating..."
    docker volume create "${BACKUP_VOLUME}" >/dev/null
    VOLUME_DIR="$(
        docker volume inspect --format '{{ .Mountpoint }}' "${BACKUP_VOLUME}"
    )"
fi
if [[ ! -d "${VOLUME_DIR}" ]]; then
    log "ERROR: resolved volume directory does not exist: ${VOLUME_DIR}"
    exit 1
fi
VOLUME_DIR="$(cd "${VOLUME_DIR}" && pwd -P)"
VOLUME_PARENT="$(dirname "${VOLUME_DIR}")"
if [[ "${VOLUME_DIR}" != /* || "$(basename "${VOLUME_DIR}")" != "_data" || "${VOLUME_PARENT}" == "/" ]]; then
    log "ERROR: refusing unsafe volume path ${VOLUME_DIR}"
    exit 1
fi

# The lock lives in the per-volume parent, so different Docker volumes do not
# block each other while a second restore of this volume fails before mutation.
exec 9> "${VOLUME_PARENT}/.tinyassets-restore.lock"
if ! flock -n 9; then
    log "ERROR: restore already in progress for ${VOLUME_DIR}"
    exit 1
fi

# ----- 3. validate and stage before stopping any container -------------

if ! python3 - "${TAR_PATH}" <<'PY'
import pathlib
import sys
import tarfile

archive = sys.argv[1]
try:
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
except (OSError, tarfile.TarError) as exc:
    print(f"archive unreadable: {exc}", file=sys.stderr)
    raise SystemExit(1)

if not members:
    print("archive is empty", file=sys.stderr)
    raise SystemExit(1)

for member in members:
    path = pathlib.PurePosixPath(member.name)
    parts = path.parts
    if path.is_absolute() or not parts or parts[0] != "_data":
        print(f"unsafe archive root: {member.name!r}", file=sys.stderr)
        raise SystemExit(1)
    if any(part in ("", ".", "..") for part in parts):
        print(f"unsafe archive path: {member.name!r}", file=sys.stderr)
        raise SystemExit(1)
    if len(parts) == 1 and not member.isdir():
        print(f"archive root is not a directory: {member.name!r}", file=sys.stderr)
        raise SystemExit(1)
    # Stripping the `_data` root changes link coordinates, so reject links
    # entirely rather than trying to prove their post-strip target safe.
    if member.issym() or member.islnk():
        print(f"archive links are not restorable safely: {member.name!r}", file=sys.stderr)
        raise SystemExit(1)
    if not (member.isfile() or member.isdir()):
        print(f"unsupported archive member type: {member.name!r}", file=sys.stderr)
        raise SystemExit(1)
PY
then
    log "ERROR: archive member validation failed"
    exit 4
fi
if ! tar -tzf "${TAR_PATH}" > /dev/null; then
    log "ERROR: archive integrity check failed"
    exit 4
fi

STAGE_DIR="$(mktemp -d "${VOLUME_PARENT}/.tinyassets-restore-stage.XXXXXX")"
if ! tar -xzf "${TAR_PATH}" -C "${STAGE_DIR}" --strip-components=1; then
    log "ERROR: archive staging extract failed"
    exit 4
fi
if ! chown --reference="${VOLUME_DIR}" "${STAGE_DIR}" \
        || ! chmod --reference="${VOLUME_DIR}" "${STAGE_DIR}"; then
    log "ERROR: failed to preserve volume-root ownership or mode on staging"
    exit 4
fi
log "  archive validated and staged at ${STAGE_DIR}"

# ----- 4. stop every consumer, then swap with automatic rollback -------

if ! CONTAINER_OUTPUT="$(
    docker ps -q --filter "volume=${BACKUP_VOLUME}"
)"; then
    log "ERROR: failed to enumerate running volume consumers"
    exit 4
fi
containers=()
if [[ -n "${CONTAINER_OUTPUT}" ]]; then
    mapfile -t containers <<< "${CONTAINER_OUTPUT}"
fi
if [[ "${#containers[@]}" -gt 0 ]]; then
    log "stopping ${#containers[@]} container(s) mounting ${BACKUP_VOLUME}..."
    if ! docker stop "${containers[@]}"; then
        log "ERROR: failed to stop all running volume consumers"
        exit 4
    fi
fi
if ! CONTAINER_OUTPUT="$(
    docker ps -q --filter "volume=${BACKUP_VOLUME}"
)"; then
    log "ERROR: failed to verify stopped volume consumers"
    exit 4
fi
if [[ -n "${CONTAINER_OUTPUT}" ]]; then
    log "ERROR: running volume consumers remain after stop"
    exit 4
fi

OLD_DIR="$(mktemp -d "${VOLUME_PARENT}/.tinyassets-restore-old.XXXXXX")"
rmdir -- "${OLD_DIR}"
if ! mv -- "${VOLUME_DIR}" "${OLD_DIR}"; then
    log "ERROR: failed to retain current volume at ${OLD_DIR}"
    exit 4
fi
if ! mv -- "${STAGE_DIR}" "${VOLUME_DIR}"; then
    log "ERROR: failed to install staged volume; rolling original back"
    if ! mv -- "${OLD_DIR}" "${VOLUME_DIR}"; then
        log "CRITICAL: failed to restore original volume from ${OLD_DIR}"
    fi
    exit 4
fi
STAGE_DIR=""

# ----- 5. done — caller verifies, starts, and later removes old data ----

log "restore complete. Data installed at ${VOLUME_DIR}."
log "pre-restore volume retained at ${OLD_DIR} until caller health verification."
log "NEXT — start only the intended service, probe it, then remove ${OLD_DIR}."
exit 0
