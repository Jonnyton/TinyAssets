#!/usr/bin/env bash
# Remote half of the "Apply daemon env flag" workflow. Runs ON the prod droplet,
# under the shared host-mutation flock, invoked as:
#
#   sudo flock -w 120 /var/lock/tinyassets-host-mutation.lock \
#     bash /tmp/apply-daemon-env-remote.sh <KEY> <VALUE> <HELPER_PATH> <HELPER_SHA>
#
# Contract (all validated caller-side in .github/workflows/apply-daemon-env.yml):
#   KEY         an allowlisted non-secret TINYASSETS_* feature flag
#   VALUE       single-line, matches the per-key value allowlist
#   HELPER_PATH staged install-tinyassets-env.sh (the atomic env writer)
#   HELPER_SHA  expected sha256 of HELPER_PATH (integrity check inside the lock)
#
# Behaviour: snapshot prior value -> set new -> restart daemon -> require healthy
# AND the value live in the running process -> on any failure restore the prior
# value (or delete the key) and restart again. Never leaves prod wedged on a bad
# flag.
#
# Exit: 0 applied+effective; 2 rolled back (prod healthy on prior value);
#       1 bad invocation / integrity; 3 rollback itself unhealthy (loud).
set -euo pipefail

KEY="${1:?KEY required}"
VAL="${2?VALUE required}"
HELPER="${3:?HELPER_PATH required}"
WANT_SHA="${4:?HELPER_SHA required}"

ENV_FILE=/etc/tinyassets/env
UNIT=tinyassets-daemon
HEALTH_TRIES=24
HEALTH_INTERVAL=5

err() { printf '::error::%s\n' "$*" >&2; }

[ -r "$HELPER" ] || { err "staged helper ${HELPER} not readable"; exit 1; }
got_sha="$(sha256sum "$HELPER" | awk '{print $1}')"
[ "$got_sha" = "$WANT_SHA" ] || { err "staged helper checksum mismatch (got ${got_sha}, want ${WANT_SHA})"; exit 1; }
[ -r "$ENV_FILE" ] || { err "${ENV_FILE} not readable"; exit 1; }

# Snapshot prior state for rollback.
if grep -qE "^${KEY}=" "$ENV_FILE"; then
  HAD_PRIOR=1
  PRIOR_VAL="$(grep -E "^${KEY}=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
else
  HAD_PRIOR=0
  PRIOR_VAL=""
fi

restart_daemon() {
  systemctl reset-failed "$UNIT" 2>/dev/null || true
  systemctl restart "$UNIT"
}

daemon_healthy() {
  local i state
  for i in $(seq 1 "$HEALTH_TRIES"); do
    state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$UNIT" 2>/dev/null || echo error)"
    [ "$state" = healthy ] && return 0
    case "$state" in dead|exited) err "daemon terminal state ${state}"; return 1 ;; esac
    sleep "$HEALTH_INTERVAL"
  done
  err "daemon did not reach healthy within $((HEALTH_TRIES * HEALTH_INTERVAL))s"
  return 1
}

restore_prior() {
  if [ "$HAD_PRIOR" = 1 ]; then
    printf '%s' "$PRIOR_VAL" | bash "$HELPER" set "$KEY"
  else
    bash "$HELPER" delete "$KEY" || true
  fi
  restart_daemon
}

# --- apply -----------------------------------------------------------------
printf '%s' "$VAL" | bash "$HELPER" set "$KEY"
restart_daemon

# Require healthy AND the value live in the running process. A compose
# `environment:` entry or a later env_file could override the env file, making a
# green health check a silent no-op — printenv proves the value is effective.
if daemon_healthy; then
  live="$(docker exec "$UNIT" printenv "$KEY" 2>/dev/null || true)"
  if [ "$live" = "$VAL" ]; then
    echo "applied ${KEY}=${VAL}; live in the running daemon"
    exit 0
  fi
  err "daemon healthy but ${KEY} is '${live}', not '${VAL}' — a compose/env override is winning; rolling back"
fi

# --- rollback --------------------------------------------------------------
err "apply of ${KEY}=${VAL} not effective; restoring prior value"
restore_prior
if daemon_healthy; then
  echo "rolled back ${KEY} (prior: ${HAD_PRIOR:+set}); daemon healthy"
  exit 2
fi
err "rollback of ${KEY} did not reach healthy — manual intervention required"
exit 3
