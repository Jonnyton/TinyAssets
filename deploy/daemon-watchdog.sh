#!/usr/bin/env bash
# Recover the Workflow daemon when the systemd unit, compose containers, or
# daemon heartbeat stop advancing. Intended for systemd timer execution.

set -euo pipefail

COMPOSE_FILE="${WORKFLOW_COMPOSE_FILE:-/opt/workflow/compose.yml}"
SERVICE_UNIT="${WORKFLOW_DAEMON_UNIT:-workflow-daemon.service}"
DATA_VOLUME="${WORKFLOW_DATA_VOLUME:-workflow-data}"
# Empty default -> auto-discover the freshest worker-supervisor heartbeat
# (see heartbeat_path). Set WORKFLOW_HEARTBEAT_RELATIVE to a
# "<universe>/<file>" path under the data volume to pin a specific one.
HEARTBEAT_RELATIVE="${WORKFLOW_HEARTBEAT_RELATIVE:-}"
HEARTBEAT_MAX_AGE_SECONDS="${WORKFLOW_HEARTBEAT_MAX_AGE_SECONDS:-900}"
LOCK_FILE="${WORKFLOW_DAEMON_WATCHDOG_LOCK:-/run/workflow-daemon-watchdog.lock}"
LOG_TAG="daemon-watchdog"

log() {
    printf '%s [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$LOG_TAG" "$*"
}

restart_daemon() {
    local reason="$1"
    log "restarting ${SERVICE_UNIT}: ${reason}"
    systemctl reset-failed "${SERVICE_UNIT}" >/dev/null 2>&1 || true
    systemctl restart "${SERVICE_UNIT}"
}

container_running() {
    local name="$1"
    local state
    state="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)"
    [[ "$state" == "true" ]]
}

heartbeat_path() {
    local mountpoint
    mountpoint="$(docker volume inspect "$DATA_VOLUME" --format '{{ .Mountpoint }}' 2>/dev/null || true)"
    if [[ -z "$mountpoint" ]]; then
        return 1
    fi
    # Operator-pinned path wins.
    if [[ -n "$HEARTBEAT_RELATIVE" ]]; then
        printf '%s/%s\n' "$mountpoint" "$HEARTBEAT_RELATIVE"
        return 0
    fi
    # Auto-discover: the active universe rewrites
    # <universe>/.worker_supervisor*.json every ~15s. Check the FRESHEST one so
    # a restart fires only when the ENTIRE fleet has gone silent — not a single
    # dormant universe. The legacy default (earthos/heartbeat) pointed at a path
    # that never existed, so heartbeat detection was effectively dead.
    local freshest
    freshest="$(find "$mountpoint" -name '.worker_supervisor*.json' -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-)"
    if [[ -z "$freshest" ]]; then
        return 1
    fi
    printf '%s\n' "$freshest"
}

heartbeat_stale() {
    local path="$1"
    [[ -f "$path" ]] || return 1

    local now mtime age
    now="$(date +%s)"
    mtime="$(stat -c %Y "$path")"
    age=$(( now - mtime ))
    if (( age > HEARTBEAT_MAX_AGE_SECONDS )); then
        log "heartbeat stale: ${path} age=${age}s max=${HEARTBEAT_MAX_AGE_SECONDS}s"
        return 0
    fi
    return 1
}

main() {
    exec 9>"$LOCK_FILE"
    if ! flock -n 9; then
        log "another watchdog run is active; exiting"
        exit 0
    fi

    if ! command -v docker >/dev/null 2>&1; then
        log "docker is unavailable"
        exit 1
    fi

    if ! systemctl is-active --quiet "$SERVICE_UNIT"; then
        restart_daemon "systemd unit is not active"
        exit 0
    fi

    if ! container_running workflow-daemon; then
        restart_daemon "workflow-daemon container is not running"
        exit 0
    fi

    if [[ -f "$COMPOSE_FILE" ]]; then
        docker compose -f "$COMPOSE_FILE" ps >/dev/null
    fi

    local hb_path=""
    if hb_path="$(heartbeat_path)"; then
        if heartbeat_stale "$hb_path"; then
            restart_daemon "heartbeat stale"
            exit 0
        fi
    else
        log "heartbeat volume ${DATA_VOLUME} is not available yet; relying on unit/container checks"
    fi

    log "healthy: unit active, workflow-daemon running"
}

main "$@"
