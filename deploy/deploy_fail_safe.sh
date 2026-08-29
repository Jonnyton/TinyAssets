#!/usr/bin/env bash
# Fail-safe single-daemon production deploy. Runs ON the droplet.
#
# Design (host directive 2026-08-18): the prior "retire-cheat-loop" stop-writer
# fence quiesced prod BEFORE proving the new image and could not reliably
# restore it, so every failed deploy left prod with ZERO containers. That fence
# guarded a multi-container writer fleet that no longer exists (cheat-loop
# retired 2026-06-25; only the daemon + sidecars remain). This replaces it with
# a plain, fail-safe image swap:
#
#   lock  ->  record current image  ->  pull new  ->  prove it loads (ephemeral)
#     ->  swap TINYASSETS_IMAGE + compose up -d  ->  health + running-image check
#     ->  roll back to the recorded image if unhealthy
#
# It NEVER leaves prod stopped: the worst case restores the previous healthy
# image, and compose `restart: unless-stopped` + systemd `Restart=always` are
# the backstop. There is a brief recreate window on `systemctl restart`; true
# zero-downtime (blue/green) is a later refinement, not required by the
# never-zero-containers invariant.
#
# Serialization (Codex review #7): takes the SAME host-mutation flock the
# watchdog/autoheal use so a manual deploy cannot race a watchdog restart.
# Public reachability (Codex review #8): after the daemon is healthy, requires
# the cloudflared sidecar to be running before accepting. Health probe (Codex
# review #12): validates the timeout, fails fast on terminal states, and does
# NOT treat a bare "running" (no healthcheck yet) as success.
#
# KNOWN FOLLOW-UPS (documented, not silently dropped):
#   - Slack-agent is profile-gated and outside this swap/rollback (review #9);
#     it is separately managed. A code deploy leaves it on its prior image.
#   - The runtime healthcheck is a local MCP initialize; the CALLER should run
#     the public `mcp_public_canary --assert-handles` gate after this returns 0
#     and roll forward/back on its result (review #10).
#   - A candidate that runs an irreversible /data migration before failing can
#     make an image-only rollback insufficient (review #11). Startup migrations
#     must stay additive/backward-compatible.
#
# Usage:  sudo deploy_fail_safe.sh <new_image_ref>
# The env helper /tmp/install-tinyassets-env.sh must already be present.
# <new_image_ref> must be an immutable ghcr.io/...@sha256:<digest> reference
# (the caller verifies ancestry/provenance).
#
# Exit codes:
#   0  deployed the new image (daemon healthy + cloudflared up)
#   1  refused before any host mutation (bad args / lock / pull / import) — prod untouched
#   2  new image unhealthy; rolled back to the previous image (healthy)
#   3  rollback also unhealthy — manual intervention required (loud)
set -uo pipefail

NEW_IMAGE="${1:-}"
ENV_FILE=/etc/tinyassets/env
ENV_HELPER=/tmp/install-tinyassets-env.sh
UNIT=tinyassets-daemon
COMPOSE_FILE=/opt/tinyassets/compose.yml
DAEMON_CONTAINER=tinyassets-daemon
TUNNEL_CONTAINER=tinyassets-tunnel
# Shared host-mutation lock (same path the watchdog uses); serializes all
# image mutators so deploy/watchdog/autoheal cannot race.
LOCK_FILE=/var/lock/tinyassets-host-mutation.lock
LOCK_WAIT=120            # seconds to wait for the lock before refusing
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"   # seconds to reach 'healthy'
HEALTH_INTERVAL=5
INSPECT_ERR_TOLERANCE=6  # consecutive docker-inspect transport errors tolerated

log() { printf '%s %s\n' "[deploy-fail-safe]" "$*"; }
err() { printf '::error::%s\n' "$*" >&2; }

# --- guards, before any mutation ------------------------------------------
if [ -z "$NEW_IMAGE" ]; then err "new image ref is required"; exit 1; fi
case "$NEW_IMAGE" in
  *@sha256:*) : ;;  # immutable digest ref required
  *) err "new image must be an immutable @sha256: ref (got: ${NEW_IMAGE})"; exit 1 ;;
esac
if ! printf '%s' "$HEALTH_TIMEOUT" | grep -Eq '^[1-9][0-9]{0,3}$'; then
  err "HEALTH_TIMEOUT must be a positive integer 1..9999 (got: ${HEALTH_TIMEOUT})"; exit 1
fi
if [ ! -r "$ENV_FILE" ]; then err "${ENV_FILE} not readable"; exit 1; fi
if [ ! -f "$ENV_HELPER" ]; then err "${ENV_HELPER} missing (workflow must scp it first)"; exit 1; fi

# --- acquire the shared host-mutation lock (review #7) --------------------
exec 9>"$LOCK_FILE" || { err "cannot open lock ${LOCK_FILE}"; exit 1; }
if ! flock -w "$LOCK_WAIT" 9; then
  err "another host mutation holds ${LOCK_FILE} after ${LOCK_WAIT}s; refusing (prod untouched)"; exit 1
fi

container_state() {
  # Prints "<health-or-status>" for a container, or "missing" / "error".
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null || echo error
}

# Health probe: wait up to HEALTH_TIMEOUT for the daemon to be healthy.
# Fail-fast on terminal states; do NOT accept a bare "running" (no healthcheck
# result yet) as success; tolerate a bounded number of inspect errors.
health_ok() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT)) status errs=0
  while [ "$SECONDS" -lt "$deadline" ]; do
    status="$(container_state "$DAEMON_CONTAINER")"
    case "$status" in
      healthy)          return 0 ;;
      dead|exited)      err "daemon container terminal state '${status}'"; return 1 ;;
      error|missing)    errs=$((errs + 1)); [ "$errs" -ge "$INSPECT_ERR_TOLERANCE" ] && { err "daemon inspect unavailable ${errs}x"; return 1; } ;;
      *)                errs=0 ;;   # starting / running (no healthcheck verdict yet) -> keep waiting
    esac
    sleep "$HEALTH_INTERVAL"
  done
  err "daemon did not reach 'healthy' within ${HEALTH_TIMEOUT}s (last: ${status:-unknown})"
  return 1
}

# The daemon is only usable publicly if the cloudflared tunnel is running.
tunnel_up() {
  local s; s="$(docker inspect -f '{{.State.Status}}' "$TUNNEL_CONTAINER" 2>/dev/null || echo missing)"
  [ "$s" = "running" ]
}

set_image() { printf '%s' "$1" | bash "$ENV_HELPER" set TINYASSETS_IMAGE; }

# The container must actually be RUNNING the requested image. A healthy daemon
# is not proof: when the systemd unit could not start (2026-08-21), the OLD
# container kept running under docker's restart policy, health_ok passed, and
# every deploy reported "healthy" while changing nothing - a false green with a
# success receipt. Compare image ids, not health.
running_image_matches() {
  local want have
  want="$(docker image inspect -f '{{.Id}}' "$1" 2>/dev/null || true)"
  have="$(docker inspect -f '{{.Image}}' "$DAEMON_CONTAINER" 2>/dev/null || true)"
  [ -n "$want" ] && [ "$want" = "$have" ]
}

accept() {  # daemon healthy AND running the requested image AND tunnel up
  local want="$1"
  health_ok || return 1
  if ! running_image_matches "$want"; then
    err "daemon is healthy but NOT running ${want} (running: $(docker inspect -f '{{.Config.Image}}' "$DAEMON_CONTAINER" 2>/dev/null || echo unknown))"
    return 1
  fi
  local i
  for i in 1 2 3 4 5 6; do tunnel_up && return 0; sleep 5; done
  err "daemon healthy but cloudflared tunnel not running (public surface down)"
  return 1
}

# Converge the production services onto TINYASSETS_IMAGE. Drives docker
# compose DIRECTLY (root, proven in the 2026-08-21 recovery) so the deploy
# never depends on the systemd unit being startable; the unit is then asked to
# track the new state best-effort so `systemctl status` stays truthful. The
# three production services are named explicitly: the worker fleet is gone
# (2026-08-29) but `slack-agent` sits behind a profile, and naming them keeps
# a future service from starting by accident. `up -d` recreates only the
# services whose image or config changed (the tunnel keeps running).
restart_stack() {
  systemctl reset-failed "$UNIT" 2>/dev/null || true
  if ! docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d daemon cloudflared logs; then
    err "docker compose up -d failed"
    return 1
  fi
  systemctl start "$UNIT" 2>/dev/null || err "note: ${UNIT} did not start (stack converged directly; see journalctl -u ${UNIT})"
  return 0
}

# --- 1. record the current (rollback) image -------------------------------
# The rollback target is what is actually RUNNING, not what the env file says:
# after a failed deploy the env file already names the failed image (the
# 2026-08-21 incident state), so rolling back to it would change nothing.
# Captured as an IMMUTABLE repo digest (repo@sha256:...), never a tag: the
# rollback ref is written to the env file and must be re-pullable as exactly
# the bytes that were running.
PREV_IMAGE="$(docker inspect -f '{{.Image}}' "$DAEMON_CONTAINER" 2>/dev/null \
  | xargs -r docker image inspect -f '{{index .RepoDigests 0}}' 2>/dev/null || true)"
case "$PREV_IMAGE" in
  *@sha256:*) ;;
  *) PREV_IMAGE="$(grep -E '^TINYASSETS_IMAGE=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)" ;;
esac
log "previous image: ${PREV_IMAGE:-<none>}"
log "target image:   ${NEW_IMAGE}"

# --- 2. pull the new image (still no prod mutation) -----------------------
if ! docker pull "$NEW_IMAGE" >/dev/null 2>&1; then
  err "failed to pull ${NEW_IMAGE}; prod untouched"; exit 1
fi

# --- 3. prove the new image LOADS before touching prod --------------------
if ! timeout 90 docker run --rm --memory=512m --memory-swap=512m --network=none \
      --entrypoint python "$NEW_IMAGE" -c 'import tinyassets.universe_server' >/dev/null 2>&1; then
  err "candidate image failed to load; refusing to swap. prod untouched"; exit 1
fi
log "candidate image loads cleanly"

# --- 4. swap + restart ----------------------------------------------------
log "swapping TINYASSETS_IMAGE and converging the stack"
if ! set_image "$NEW_IMAGE"; then
  err "could not record TINYASSETS_IMAGE=${NEW_IMAGE} in ${ENV_FILE}; nothing mutated"
  echo "deploy_result=failed_env_write"
  exit 1
fi
restart_stack || true

# --- 5. accept the new image (healthy + RUNNING it + tunnel up) -----------
if accept "$NEW_IMAGE"; then
  log "deploy healthy on ${NEW_IMAGE}"
  echo "deploy_result=deployed"
  echo "deployed_image=${NEW_IMAGE}"
  exit 0
fi

# --- 6. unhealthy -> roll back to the recorded previous image -------------
err "new image did not become acceptable; rolling back"
if [ -z "$PREV_IMAGE" ]; then
  err "no previous image recorded; cannot roll back automatically"
  echo "deploy_result=failed_no_rollback_target"
  exit 3
fi
if ! set_image "$PREV_IMAGE"; then
  err "could not record rollback image ${PREV_IMAGE} in ${ENV_FILE} — manual intervention required"
  echo "deploy_result=rollback_env_write_failed"
  exit 3
fi
restart_stack || true
if accept "$PREV_IMAGE"; then
  log "rolled back to previous image ${PREV_IMAGE} (healthy)"
  echo "deploy_result=rolled_back"
  echo "deployed_image=${PREV_IMAGE}"
  exit 2
fi

err "rollback to ${PREV_IMAGE} ALSO did not become acceptable — manual intervention required"
echo "deploy_result=rollback_unhealthy"
exit 3
