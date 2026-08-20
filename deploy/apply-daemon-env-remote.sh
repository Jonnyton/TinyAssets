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
# Behaviour: snapshot prior value -> set new -> restart daemon -> ACCEPT only when
# the daemon is healthy AND the tunnel is up AND the value is live in the running
# process. On ANY failure of that chain — including a failed `systemctl restart` —
# restore the prior value (or delete the key) and restart again, then verify the
# rollback is itself accepted. A bad flag can never wedge prod.
#
# Snapshot note: this reads the prior value with a canonical `^KEY=` match, which
# is exactly the format install-tinyassets-env.sh `set` writes. These flags are
# only ever set through that helper, so the snapshot round-trips faithfully.
#
# Exit: 0 applied+effective; 2 rolled back (prod accepted on prior value);
#       1 bad invocation / integrity; 3 rollback itself not accepted (loud).
set -uo pipefail

KEY="${1:?KEY required}"
VAL="${2?VALUE required}"
HELPER="${3:?HELPER_PATH required}"
WANT_SHA="${4:?HELPER_SHA required}"

ENV_FILE=/etc/tinyassets/env
UNIT=tinyassets-daemon
DAEMON_CONTAINER=tinyassets-daemon
TUNNEL_CONTAINER=tinyassets-tunnel
HEALTH_TRIES=24
HEALTH_INTERVAL=5
TUNNEL_TRIES=6

err() { printf '::error::%s\n' "$*" >&2; }

# --- integrity + preconditions (before any mutation) ----------------------
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
    state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$DAEMON_CONTAINER" 2>/dev/null || echo error)"
    [ "$state" = healthy ] && return 0
    case "$state" in dead|exited) err "daemon terminal state ${state}"; return 1 ;; esac
    sleep "$HEALTH_INTERVAL"
  done
  err "daemon did not reach healthy within $((HEALTH_TRIES * HEALTH_INTERVAL))s"
  return 1
}

tunnel_up() {
  local i s
  for i in $(seq 1 "$TUNNEL_TRIES"); do
    s="$(docker inspect -f '{{.State.Status}}' "$TUNNEL_CONTAINER" 2>/dev/null || echo missing)"
    [ "$s" = running ] && return 0
    sleep "$HEALTH_INTERVAL"
  done
  err "cloudflared tunnel not running (public surface down)"
  return 1
}

value_live() {  # the requested value must actually be live in the running process
  local live
  live="$(docker exec "$DAEMON_CONTAINER" printenv "$1" 2>/dev/null || true)"
  [ "$live" = "$2" ] && return 0
  err "${1} is '${live}', not '${2}' — a compose/env override is winning"
  return 1
}

# apply_and_accept and roll_back_and_accept are invoked in `if` conditions so a
# failed restart (or any inner command) surfaces as a return code and funnels to
# rollback, rather than aborting the script mid-mutation.
apply_and_accept() {
  printf '%s' "$VAL" | bash "$HELPER" set "$KEY" || { err "env write failed"; return 1; }
  restart_daemon || { err "daemon restart failed"; return 1; }
  daemon_healthy || return 1
  tunnel_up || return 1
  value_live "$KEY" "$VAL" || return 1
  return 0
}

roll_back_and_accept() {
  if [ "$HAD_PRIOR" = 1 ]; then
    printf '%s' "$PRIOR_VAL" | bash "$HELPER" set "$KEY" || { err "restore write failed"; return 1; }
  else
    bash "$HELPER" delete "$KEY" || { err "restore delete failed"; return 1; }
  fi
  restart_daemon || { err "restart during rollback failed"; return 1; }
  daemon_healthy || return 1
  tunnel_up || return 1
  # Verify the restored state actually took (absent, or the prior value).
  if [ "$HAD_PRIOR" = 1 ]; then
    value_live "$KEY" "$PRIOR_VAL" || return 1
  elif docker exec "$DAEMON_CONTAINER" printenv "$KEY" >/dev/null 2>&1; then
    err "rollback did not remove ${KEY} from the running process"; return 1
  fi
  return 0
}

# --- apply -----------------------------------------------------------------
if apply_and_accept; then
  echo "applied ${KEY}=${VAL}; live in the running daemon + public path up"
  exit 0
fi

# --- rollback --------------------------------------------------------------
if [ "$HAD_PRIOR" = 1 ]; then
  err "apply of ${KEY}=${VAL} not accepted; restoring prior value ${PRIOR_VAL}"
else
  err "apply of ${KEY}=${VAL} not accepted; removing the key (had no prior value)"
fi
if roll_back_and_accept; then
  echo "rolled back ${KEY}; prod accepted on the prior state"
  exit 2
fi
err "rollback of ${KEY} was not accepted — manual intervention required"
exit 3
