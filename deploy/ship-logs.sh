#!/usr/bin/env bash
# Row K — offsite log archiving for the self-hosted TinyAssets daemon.
#
# Ships Docker container logs to an rclone-compatible offsite destination
# (e.g. Hetzner Storage Box via SFTP, DO Spaces via S3). Complements the
# Vector sidecar (vector.yaml) which handles real-time forwarding to
# Better Stack; this script provides a pull-based, time-windowed archive
# for long-retention storage.
#
# Usage:
#   LOG_DEST=sftp:storagebox/tinyassets-logs bash deploy/ship-logs.sh
#
# Environment variables:
#   LOG_DEST          rclone destination URL  (REQUIRED unless DRY_RUN=1)
#   LOG_CONTAINERS    space-separated container names to archive
#                     default: daemon, tunnel, and all four cloud workers
#   LOG_SINCE         docker logs --since window  default: 24h
#   LOG_RETAIN_DAYS   delete remote archives older than N days  default: 30
#   DRY_RUN           set to 1 to validate env + print plan without touching anything
#   LOG_DIR           local scratch dir for log files  default: /tmp/tinyassets-logs-$$
#
# Retention: archives named tinyassets-logs-YYYY-MM-DDTHH-MM-SS.tar.gz;
#   any remote archive older than LOG_RETAIN_DAYS days is deleted.
#
# Requires: bash, docker, rclone, tar (all present on the Hetzner Droplet).

set -euo pipefail

# ---------------------------------------------------------------------------
# Config / defaults
# ---------------------------------------------------------------------------

LOG_DEST="${LOG_DEST:-}"
LOG_CONTAINERS="${LOG_CONTAINERS:-tinyassets-daemon tinyassets-tunnel tinyassets-logs tinyassets-slack-agent}"
LOG_SINCE="${LOG_SINCE:-24h}"
LOG_RETAIN_DAYS="${LOG_RETAIN_DAYS:-30}"
DRY_RUN="${DRY_RUN:-0}"
LOG_DIR="${LOG_DIR:-/tmp/tinyassets-logs-$$}"

TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%S)"
ARCHIVE_NAME="tinyassets-logs-${TIMESTAMP}.tar.gz"

# ---------------------------------------------------------------------------
# Dry-run path — validate env, print plan, exit 0
# ---------------------------------------------------------------------------

if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] ship-logs.sh — no files will be written or uploaded"
    echo "[dry-run] LOG_DEST=${LOG_DEST}"
    echo "[dry-run] LOG_CONTAINERS=${LOG_CONTAINERS}"
    echo "[dry-run] LOG_SINCE=${LOG_SINCE}"
    echo "[dry-run] LOG_RETAIN_DAYS=${LOG_RETAIN_DAYS}"
    echo "[dry-run] archive name would be: ${ARCHIVE_NAME}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Env validation
# ---------------------------------------------------------------------------

if [[ -z "${LOG_DEST}" ]]; then
    echo "ERROR: LOG_DEST is required (e.g. sftp:storagebox/tinyassets-logs or s3://bucket/logs)" >&2
    exit 1
fi

if ! command -v docker &>/dev/null; then
    echo "ERROR: docker not found in PATH" >&2
    exit 1
fi

if ! command -v rclone &>/dev/null; then
    echo "ERROR: rclone not found in PATH" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Collect Docker container logs
# ---------------------------------------------------------------------------

mkdir -p "${LOG_DIR}"
trap 'rm -rf "${LOG_DIR}"' EXIT

echo "[ship-logs] collecting logs for containers: ${LOG_CONTAINERS}"
manifest="${LOG_DIR}/fleet-manifest.tsv"
printf 'container\tcontainer_id\tstatus\tlog_file\n' > "${manifest}"
archive_files=("$(basename -- "${manifest}")")
collected_names=()
collected_ids=()
for container in ${LOG_CONTAINERS}; do
    log_file="${LOG_DIR}/${container}.log"
    if ! identity_state="$(
        docker inspect -f '{{.Id}} {{.State.Status}}' "${container}" 2>/dev/null
    )"; then
        echo "ERROR: required log container ${container} is missing" >&2
        exit 1
    fi
    read -r container_id status extra <<< "${identity_state}"
    if [[ ! "${container_id}" =~ ^[0-9a-f]{64}$ || -z "${status}" || -n "${extra:-}" ]]; then
        echo "ERROR: required log container ${container} has malformed identity state" >&2
        exit 1
    fi
    if ! docker logs "${container_id}" --since "${LOG_SINCE}" >"${log_file}" 2>&1; then
        echo "ERROR: logs for required container ${container} are unreadable" >&2
        exit 1
    fi
    if ! current_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" \
        || [ "${current_id}" != "${container_id}" ]; then
        echo "ERROR: required log container ${container} changed generation during collection" >&2
        exit 1
    fi
    log_name="$(basename -- "${log_file}")"
    printf '%s\t%s\t%s\t%s\n' \
        "${container}" "${container_id}" "${status}" "${log_name}" >> "${manifest}"
    archive_files+=("${log_name}")
    collected_names+=("${container}")
    collected_ids+=("${container_id}")
    lines=$(wc -l <"${log_file}")
    echo "[ship-logs] ${container}: status=${status}; ${lines} lines (since ${LOG_SINCE})"
done

for index in "${!collected_names[@]}"; do
    container="${collected_names[${index}]}"
    container_id="${collected_ids[${index}]}"
    if ! current_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" \
        || [ "${current_id}" != "${container_id}" ]; then
        echo "ERROR: required log container ${container} changed generation during collection" >&2
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

echo "[ship-logs] creating archive: ${ARCHIVE_NAME}"
tar -czf "${LOG_DIR}/${ARCHIVE_NAME}" -C "${LOG_DIR}" \
    "${archive_files[@]}"

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

echo "[ship-logs] uploading to ${LOG_DEST}/${ARCHIVE_NAME}"
rclone copyto "${LOG_DIR}/${ARCHIVE_NAME}" "${LOG_DEST}/${ARCHIVE_NAME}"

echo "[ship-logs] upload complete"

# ---------------------------------------------------------------------------
# Prune old archives (retention window)
# ---------------------------------------------------------------------------

echo "[ship-logs] pruning archives older than ${LOG_RETAIN_DAYS} days from ${LOG_DEST}"
CUTOFF_TS="$(date -d "-${LOG_RETAIN_DAYS} days" +%s 2>/dev/null \
    || date -v "-${LOG_RETAIN_DAYS}d" +%s 2>/dev/null \
    || echo 0)"

# rclone lsf --format tp → "size;path" per line, sorted oldest-first
rclone lsf --format "tp" "${LOG_DEST}/" 2>/dev/null \
    | sort \
    | while IFS=";" read -r _size path; do
        # Extract timestamp from tinyassets-logs-YYYY-MM-DDTHH-MM-SS.tar.gz
        ts_str=$(echo "${path}" | grep -oP '\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}' || true)
        if [[ -z "${ts_str}" ]]; then
            continue
        fi
        # Normalize dashes back to colons for date parsing
        ts_iso="${ts_str:0:10}T${ts_str:11:2}:${ts_str:14:2}:${ts_str:17:2}Z"
        file_ts=$(date -d "${ts_iso}" +%s 2>/dev/null \
            || date -j -f "%Y-%m-%dT%H:%M:%SZ" "${ts_iso}" +%s 2>/dev/null \
            || echo 0)
        if [[ "${file_ts}" -lt "${CUTOFF_TS}" ]]; then
            echo "[ship-logs] pruning: ${path}"
            rclone deletefile "${LOG_DEST}/${path}" || true
        fi
    done

echo "[ship-logs] done"
