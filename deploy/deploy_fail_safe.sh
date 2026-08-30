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
#     ->  validate + snapshot + install the runtime bundle
#     ->  swap TINYASSETS_IMAGE + compose up -d
#     ->  health + running-image check
#     ->  restore the bundle snapshot AND roll back the image if unhealthy
#
# It NEVER leaves prod stopped: the worst case restores the previous healthy
# image, and compose `restart: unless-stopped` + systemd `Restart=always` are
# the backstop. There is a brief recreate window on `systemctl restart`; true
# zero-downtime (blue/green) is a later refinement, not required by the
# never-zero-containers invariant.
#
# RUNTIME BUNDLE TRANSACTION (2026-08-29, Codex ADAPT on PR #2685)
# ----------------------------------------------------------------
# compose.yml, the three vector inputs and the systemd unit are part of the
# deploy: PR #2442 dropped their sync and every compose-level change was inert
# in production for nine days. Restoring the sync as a separate workflow step
# put config mutation OUTSIDE the transaction — a failed auth-volume step, a
# lost lock or a bad candidate image each left the NEW config installed under
# the OLD image, and neither rollback path restored it. So the workflow now only
# STAGES the five files into $BUNDLE_DIR and this script owns the transaction:
#
#   claim_bundle      copies the stage into a private mktemp dir UNDER THE LOCK;
#                     everything below reads that copy. The workflow populates
#                     the stage before this lock exists, so validating one set of
#                     bytes and installing another was a live race.
#   validate_bundle   `docker compose config` on the CLAIMED copy with the
#                     production env file and the candidate image; asserts the
#                     production invariants — service set, container names,
#                     restart policy, digest-pinned sidecar images, the daemon's
#                     env_file / /data volume / healthcheck / memory limit, that
#                     the SOURCE text interpolates ${TINYASSETS_IMAGE}, and the
#                     logs read-only mounts. A miss refuses, prod untouched.
#   snapshot_bundle   copies what is live into
#                     $BUNDLE_STATE_DIR/bundle-snapshots/<UTC stamp>-XXXXXX/ with
#                     a `manifest` recording each file's uid/gid/mode, so a
#                     restore puts back exactly what was there
#   install_bundle    installs the claimed files, daemon-reloads, records whether
#                     any vector input changed
#   <converge>        plus `up -d --force-recreate logs` when vector inputs
#                     changed — vector-entrypoint.sh copies the mounted files
#                     into /run/vector-config only at container start, so an
#                     unchanged image would otherwise keep the old config
#   restore           both rollback paths reinstall the snapshot the
#                     $BUNDLE_STATE_DIR/bundle-previous pointer names BEFORE
#                     converging the previous image
#
# The pointer advances ATOMICALLY (tmp + rename) and only after a SUCCESSFUL
# install, so a rollback restores exactly the state that install replaced.
# Failing to advance it is fatal, not a warning: every later rollback would read
# the PREVIOUS deploy's snapshot and restore a bundle that was never live.
#
# Every post-install failure is fail-loud. A restore that does not complete
# leaves $BUNDLE_STATE_DIR/bundle-dirty behind and reports
# `deploy_result=rollback_failed`; while that marker exists a normal deploy
# REFUSES with `bundle_dirty`, because snapshotting a half-installed tree would
# make the mixed state the next rollback target. `--restore-bundle` is the way
# out, and clears it.
#
# An absent stage directory is not an error: it means "image-only deploy" (a
# manual run, or `--restore-bundle` on a box that never staged one). A PARTIAL
# stage directory is an error — half a bundle is the 2026-08 502. An image-only
# deploy that FAILS never touches the bundle: a surviving pointer belongs to an
# earlier deploy and names a state this run did not create.
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
#     it is separately managed. A code deploy leaves it on its prior image. Its
#     definition IS carried in the bundle, so the next profiled convergence uses
#     the deployed compose.yml.
#   - The runtime healthcheck is a local MCP initialize; the CALLER should run
#     the public `mcp_public_canary --assert-handles` gate after this returns 0
#     and roll forward/back on its result (review #10).
#   - A candidate that runs an irreversible /data migration before failing can
#     make an image-only rollback insufficient (review #11). Startup migrations
#     must stay additive/backward-compatible.
#
# Usage:
#   sudo deploy_fail_safe.sh <new_image_ref>
#   sudo deploy_fail_safe.sh --restore-bundle <previous_image_ref>
#
# `--restore-bundle` is the public-canary rollback path: it reinstalls the
# snapshot named by the bundle pointer and THEN converges <previous_image_ref>.
# It never installs the staged bundle (that is what it is undoing).
#
# The env helper /tmp/install-tinyassets-env.sh must already be present.
# <new_image_ref> must be an immutable ghcr.io/...@sha256:<digest> reference
# (the caller verifies ancestry/provenance).
#
# Exit codes:
#   0  deployed the new image (daemon healthy + cloudflared + logs up)
#   1  refused, and the box is back where it started: bad args, lock, pull,
#      import, `bundle_invalid`, `bundle_dirty`, or a post-install failure whose
#      restore COMPLETED (`bundle_install_failed`, `bundle_pointer_failed`,
#      `failed_env_write`)
#   2  new image unhealthy; rolled back to the previous image + bundle (healthy)
#   3  manual intervention required — the rollback itself did not complete
#      (`rollback_failed`, `rollback_env_write_failed`, `rollback_unhealthy`,
#      `failed_no_rollback_target`). On `rollback_failed` the bundle-dirty
#      marker is set and normal deploys refuse until `--restore-bundle` clears it.
set -uo pipefail

RESTORE_BUNDLE=0
case "${1:-}" in
  --restore-bundle)
    RESTORE_BUNDLE=1
    NEW_IMAGE="${2:-}"
    ;;
  *)
    NEW_IMAGE="${1:-}"
    ;;
esac

# Paths and ownership are env-overridable ONLY so the transaction is testable
# against a fake docker and a temp root (tests/test_deploy_bundle_transaction.py).
# The workflow invokes this under `sudo`, which strips the environment apart
# from the variables it names explicitly, so production always takes the
# defaults below.
ENV_FILE="${ENV_FILE:-/etc/tinyassets/env}"
ENV_HELPER="${ENV_HELPER:-/tmp/install-tinyassets-env.sh}"
UNIT="${UNIT:-tinyassets-daemon}"
RUNTIME_DIR="${RUNTIME_DIR:-/opt/tinyassets}"
COMPOSE_FILE="${COMPOSE_FILE:-${RUNTIME_DIR}/compose.yml}"
UNIT_FILE="${UNIT_FILE:-/etc/systemd/system/tinyassets-daemon.service}"
# Where the workflow scp's the five runtime files. Staging only — nothing here
# is authoritative. The workflow uses a per-run directory
# (/tmp/tinyassets-bundle-<run id>-<attempt>) and passes it in BUNDLE_DIR; the
# bare default is the manual-deploy path.
BUNDLE_DIR="${BUNDLE_DIR:-/tmp/tinyassets-bundle}"
BUNDLE_STATE_DIR="${BUNDLE_STATE_DIR:-/var/lib/tinyassets-deploy}"
SNAPSHOT_ROOT="${BUNDLE_STATE_DIR}/bundle-snapshots"
BUNDLE_POINTER="${BUNDLE_STATE_DIR}/bundle-previous"
# Durable "a bundle install did not finish cleanly" flag. Written before the
# first install byte and cleared only by a completed install or a completed
# restore. While it exists a normal deploy REFUSES: the alternative is that the
# next deploy snapshots the mixed state and legitimizes it as the rollback
# target (Codex round 2, §1). `--restore-bundle` runs regardless — it is the way
# out — and clears the marker when its restore completes.
BUNDLE_DIRTY="${BUNDLE_STATE_DIR}/bundle-dirty"
BUNDLE_KEEP=5
# The pre-#2442 install contract: the systemd unit runs compose as `tinyassets`
# (deploy/tinyassets-daemon.service), so the runtime files it reads are owned by
# that user; the unit itself is systemd's and stays root-owned.
RUNTIME_OWNER="${RUNTIME_OWNER:-tinyassets}"
RUNTIME_GROUP="${RUNTIME_GROUP:-tinyassets}"
UNIT_OWNER="${UNIT_OWNER:-root}"
UNIT_GROUP="${UNIT_GROUP:-root}"
DAEMON_CONTAINER=tinyassets-daemon
TUNNEL_CONTAINER=tinyassets-tunnel
LOGS_CONTAINER=tinyassets-logs
# Shared host-mutation lock (same path the watchdog uses); serializes all
# image mutators so deploy/watchdog/autoheal cannot race.
LOCK_FILE="${LOCK_FILE:-/var/lock/tinyassets-host-mutation.lock}"
LOCK_WAIT=120            # seconds to wait for the lock before refusing
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"   # seconds to reach 'healthy'
HEALTH_INTERVAL=5
INSPECT_ERR_TOLERANCE=6  # consecutive docker-inspect transport errors tolerated

# The five files the workflow stages, by basename.
BUNDLE_FILES=(
  compose.yml
  vector.yaml
  vector-betterstack.yaml
  vector-entrypoint.sh
  tinyassets-daemon.service
)

# snapshot-relative path | live destination | mode | owner class
# The claimed source for each row is $BUNDLE_WORK/<basename of the rel path>,
# which is why both compose destinations map back to the one staged compose.yml.
BUNDLE_MAP=(
  "compose.yml|${RUNTIME_DIR}/compose.yml|0644|runtime"
  "deploy/compose.yml|${RUNTIME_DIR}/deploy/compose.yml|0644|runtime"
  "deploy/vector.yaml|${RUNTIME_DIR}/deploy/vector.yaml|0644|runtime"
  "deploy/vector-betterstack.yaml|${RUNTIME_DIR}/deploy/vector-betterstack.yaml|0644|runtime"
  "deploy/vector-entrypoint.sh|${RUNTIME_DIR}/deploy/vector-entrypoint.sh|0755|runtime"
  "systemd/tinyassets-daemon.service|${UNIT_FILE}|0644|unit"
)

# Vector reads these only at container start (vector-entrypoint.sh copies them
# into /run/vector-config), so a change here needs a force-recreate, not a
# config reload.
VECTOR_INPUTS=(
  "${RUNTIME_DIR}/deploy/vector.yaml"
  "${RUNTIME_DIR}/deploy/vector-betterstack.yaml"
  "${RUNTIME_DIR}/deploy/vector-entrypoint.sh"
)

SNAPSHOT_PATH=""         # set by snapshot_bundle
VECTOR_CHANGED=0         # set by the install / restore stages
INSTALLED_THIS_RUN=0     # 1 only after install_bundle has written a byte
BUNDLE_WORK=""           # private copy of the stage, made under the lock
MARKER_STALE=0           # 1 if the dirty marker could not be cleared
RESTORE_SNAPSHOT=""      # the snapshot restore_previous_bundle resolved

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

accept() {  # daemon healthy AND running the requested image AND tunnel up AND logs up
  local want="$1"
  health_ok || return 1
  if ! running_image_matches "$want"; then
    err "daemon is healthy but NOT running ${want} (running: $(docker inspect -f '{{.Config.Image}}' "$DAEMON_CONTAINER" 2>/dev/null || echo unknown))"
    return 1
  fi
  local i tunnel=0
  for i in 1 2 3 4 5 6; do tunnel_up && { tunnel=1; break; }; sleep 5; done
  if [ "$tunnel" = "0" ]; then
    err "daemon healthy but cloudflared tunnel not running (public surface down)"
    return 1
  fi
  # LAST, deliberately. logs_running() returns on the first 'running' sighting,
  # and health_ok can then burn up to HEALTH_TIMEOUT seconds — long enough for a
  # freshly recreated vector to crash on a bad config after we already saw it up
  # (Codex round 2, §4). Re-check at the end so acceptance reflects the state we
  # are actually accepting.
  local logs_state
  logs_state="$(docker inspect -f '{{.State.Status}}' "$LOGS_CONTAINER" 2>/dev/null || echo missing)"
  if [ "$logs_state" != "running" ]; then
    err "daemon and tunnel are up but ${LOGS_CONTAINER} is '${logs_state}' (log forwarding down)"
    return 1
  fi
  return 0
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

# `up -d` does NOT recreate a container whose image and compose config are
# unchanged, and the logs service's config lives in bind-mounted FILES that
# vector copies into /run/vector-config at start. Changing vector.yaml alone is
# therefore invisible to a running tinyassets-logs until it is recreated.
logs_running() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT)) s=""
  while [ "$SECONDS" -lt "$deadline" ]; do
    s="$(docker inspect -f '{{.State.Status}}' "$LOGS_CONTAINER" 2>/dev/null || echo missing)"
    case "$s" in
      running)      return 0 ;;
      dead|exited)  err "${LOGS_CONTAINER} terminal state '${s}' after force-recreate"; return 1 ;;
    esac
    sleep "$HEALTH_INTERVAL"
  done
  err "${LOGS_CONTAINER} did not reach 'running' within ${HEALTH_TIMEOUT}s (last: ${s:-unknown})"
  return 1
}

recreate_logs() {
  log "vector inputs changed; force-recreating ${LOGS_CONTAINER} so it re-reads /etc/vector"
  if ! docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --force-recreate logs; then
    err "force-recreate of the logs service failed"
    return 1
  fi
  logs_running
}

# --- runtime bundle transaction -------------------------------------------

# The state directory holds the rollback contract; nothing outside root needs
# to read it, and the pointer names a path an unprivileged writer must not be
# able to redirect.
ensure_state_dir() {
  local previous_umask
  previous_umask="$(umask)"
  umask 077
  mkdir -p "$SNAPSHOT_ROOT"
  local rc=$?
  umask "$previous_umask"
  if [ "$rc" -ne 0 ]; then
    err "cannot create ${SNAPSHOT_ROOT}"
    return 1
  fi
  chmod 700 "$BUNDLE_STATE_DIR" 2>/dev/null || true
  chmod 700 "$SNAPSHOT_ROOT" 2>/dev/null || true
  # Sweep private work copies a previous run died before removing. Snapshot
  # retention does not cover these, so without this they accumulate forever on
  # persistent state (Codex round 3, §5).
  find "$BUNDLE_STATE_DIR" -maxdepth 1 -name '.bundle-work.*' -type d -mmin +1440 \
    -exec rm -rf {} + 2>/dev/null || true
  return 0
}

# The private copy is scratch, and it holds a full bundle. Remove it on EVERY
# exit path, including the refusals that exit before the install.
cleanup_bundle_work() {
  if [ -n "$BUNDLE_WORK" ] && [ -d "$BUNDLE_WORK" ]; then
    rm -rf "$BUNDLE_WORK" 2>/dev/null || true
  fi
  return 0
}
trap cleanup_bundle_work EXIT

# Atomic: a truncating redirect that dies half-written leaves a pointer naming
# nothing, and the rollback that reads it restores nothing while reporting
# success (Codex round 2, §3).
write_pointer() {
  local value="$1" tmp
  tmp="$(mktemp "${BUNDLE_STATE_DIR}/.bundle-previous.XXXXXX")" || return 1
  chmod 600 "$tmp" 2>/dev/null || true
  printf '%s\n' "$value" >"$tmp" || { rm -f "$tmp"; return 1; }
  # -T so a destination that is somehow a DIRECTORY is an error. Plain `mv`
  # would happily move the temp file INSIDE it and report success, leaving the
  # pointer unreadable and the failure invisible.
  mv -fT "$tmp" "$BUNDLE_POINTER" || { rm -f "$tmp"; return 1; }
  chmod 600 "$BUNDLE_POINTER" 2>/dev/null || true
  return 0
}

read_pointer() {
  [ -f "$BUNDLE_POINTER" ] || return 1
  cat "$BUNDLE_POINTER" 2>/dev/null
}

# The marker NAMES the snapshot that has to go back. A bare flag would be
# useless on the first bundle deploy a box ever runs: the install fails before
# the pointer exists, so nothing would name the snapshot the operator needs.
# Same atomicity as the pointer, and for the same reason: a truncating write
# that dies half-way leaves an EMPTY marker, which blocks every normal deploy
# while naming no snapshot to restore (Codex round 3, §2).
mark_dirty() {
  local value="${1:-}" tmp
  if [ -z "$value" ]; then
    err "refusing to write an empty dirty marker: it would block deploys while naming nothing"
    return 1
  fi
  tmp="$(mktemp "${BUNDLE_STATE_DIR}/.bundle-dirty.XXXXXX")" || {
    err "cannot stage the dirty marker"
    return 1
  }
  chmod 600 "$tmp" 2>/dev/null || true
  printf '%s\n' "$value" >"$tmp" || { rm -f "$tmp"; return 1; }
  mv -fT "$tmp" "$BUNDLE_DIRTY" || { rm -f "$tmp"; return 1; }
  chmod 600 "$BUNDLE_DIRTY" 2>/dev/null || true
  return 0
}

# What a restore must put back: the interrupted run's snapshot if there is one,
# otherwise the last successful install's. The marker wins — it names a run that
# did NOT finish, and that is the state nothing else has accounted for.
#   0  printed a target
#   1  no marker and no pointer
#   2  the marker exists but is EMPTY: dirty, with no recorded snapshot. Falling
#      through to the pointer there would restore the last GOOD state over an
#      interrupted one and call it success (Codex round 3, §2).
restore_target() {
  if [ -f "$BUNDLE_DIRTY" ]; then
    local marked
    marked="$(cat "$BUNDLE_DIRTY" 2>/dev/null || true)"
    if [ -z "${marked//[[:space:]]/}" ]; then
      return 2
    fi
    printf '%s' "$marked"
    return 0
  fi
  read_pointer
}

# A marker that will not clear is TERMINAL, not a warning: the run can be a
# complete success while every later normal deploy refuses. MARKER_STALE carries
# that to the exit so the operator learns it from the result, not a log line.
clear_dirty() {
  rm -f "$BUNDLE_DIRTY" 2>/dev/null
  if [ -e "$BUNDLE_DIRTY" ]; then
    err "cannot clear the dirty marker ${BUNDLE_DIRTY}; the NEXT normal deploy will refuse with bundle_dirty until it is removed by hand"
    MARKER_STALE=1
    return 1
  fi
  return 0
}

# Single exit for every path that would otherwise report success. A stale marker
# turns any of them into marker_clear_failed, and deployed_image= is still
# printed because the image DID change and the operator has to know which.
finish() {
  local result="$1" image="$2" code="$3"
  if [ "$MARKER_STALE" = "1" ]; then
    err "the run reached '${result}' but ${BUNDLE_DIRTY} is still present"
    [ -n "$image" ] && echo "deployed_image=${image}"
    echo "deploy_result=marker_clear_failed"
    exit 3
  fi
  echo "deploy_result=${result}"
  [ -n "$image" ] && echo "deployed_image=${image}"
  exit "$code"
}

# "absent"  no stage directory at all -> image-only deploy, not an error
# "ready"   all five staged files present
# "partial" the directory exists but is incomplete -> refuse
bundle_state() {
  local f
  if [ ! -d "$BUNDLE_DIR" ]; then printf 'absent'; return 0; fi
  for f in "${BUNDLE_FILES[@]}"; do
    if [ ! -f "${BUNDLE_DIR}/${f}" ]; then printf 'partial'; return 0; fi
  done
  printf 'ready'
}

# Copy the stage into a private directory this run owns, and validate/install
# from that copy ONLY. The workflow populates the stage before the lock is even
# requested, so between our validation and our install another actor — a second
# deploy, a manual run, anything with write access to /tmp — could swap the
# bytes underneath us and we would install something we never validated
# (Codex round 2, §1). Taking our own copy under the lock closes that window.
claim_bundle() {
  local f
  BUNDLE_WORK="$(mktemp -d "${BUNDLE_STATE_DIR}/.bundle-work.XXXXXX")" || {
    err "cannot create a private bundle working directory"
    return 1
  }
  chmod 700 "$BUNDLE_WORK" 2>/dev/null || true
  for f in "${BUNDLE_FILES[@]}"; do
    if ! cp -p "${BUNDLE_DIR}/${f}" "${BUNDLE_WORK}/${f}"; then
      err "cannot copy staged ${f} into ${BUNDLE_WORK}"
      return 1
    fi
  done
  log "claimed the staged bundle into ${BUNDLE_WORK} (validating and installing from there)"
  return 0
}

vector_fingerprint() {
  local f out=""
  for f in "${VECTOR_INPUTS[@]}"; do
    if [ -f "$f" ]; then
      out="${out}$(sha256sum "$f" 2>/dev/null | awk '{print $1}') "
    else
      out="${out}absent "
    fi
  done
  printf '%s' "$out"
}

# Parse the STAGED compose file with the production env file and the candidate
# image, and assert the production invariants. `config --services` only proved
# the three names existed (Codex: "any syntactically valid file containing three
# skeletal services named daemon/cloudflared/logs passes"), so this asserts what
# an incomplete file would actually be missing. Profiles are honoured by
# `config` itself, so slack-agent is absent here by construction — the check
# compares SETS, never a literal string.
validate_bundle() {
  local cfg rc
  cfg="$(mktemp)" || { err "cannot create a temp file for bundle validation"; return 1; }
  if ! TINYASSETS_IMAGE="$NEW_IMAGE" docker compose --env-file "$ENV_FILE" \
        -f "${BUNDLE_WORK}/compose.yml" config --format json >"$cfg" 2>"${cfg}.err"; then
    err "staged compose.yml does not parse with ${ENV_FILE}: $(head -c 800 "${cfg}.err" 2>/dev/null)"
    rm -f "$cfg" "${cfg}.err" "${cfg}.raw" "${cfg}.raw.err"
    return 1
  fi
  # A second, UNINTERPOLATED render for the env_file posture. Compose v5 (the
  # droplet runs v5.1.3) resolves every env_file into `environment` and drops
  # the `env_file` key from the default render, so the first deploy after
  # #2685 was refused with "daemon.env_file is []" (2026-08-30 00:34Z, run
  # 33283629722) although the staged file carried it. `--no-interpolate`
  # keeps `env_file` as {path, required} mappings; paths are literals, so
  # interpolation is not needed to read them.
  if ! TINYASSETS_IMAGE="$NEW_IMAGE" docker compose --env-file "$ENV_FILE" \
        -f "${BUNDLE_WORK}/compose.yml" config --format json --no-interpolate \
        >"${cfg}.raw" 2>"${cfg}.raw.err"; then
    err "staged compose.yml does not render uninterpolated: $(head -c 800 "${cfg}.raw.err" 2>/dev/null)"
    rm -f "$cfg" "${cfg}.err" "${cfg}.raw" "${cfg}.raw.err"
    return 1
  fi
  # argv[1] is the RENDERED config; argv[2] is the RAW source, because the
  # rendered daemon image proves only that THIS invocation resolved to the
  # candidate — a literal candidate ref, or a different variable that happens to
  # resolve the same, renders identically (Codex round 2, §2). argv[3] is the
  # uninterpolated render (env_file survives there).
  RUNTIME_DIR="$RUNTIME_DIR" EXPECT_IMAGE="$NEW_IMAGE" ENV_FILE="$ENV_FILE" \
    python3 - "$cfg" "${BUNDLE_WORK}/compose.yml" "${cfg}.raw" <<'PY'
import json
import os
import re
import sys

runtime = os.environ["RUNTIME_DIR"]
expect_image = os.environ["EXPECT_IMAGE"]
env_file = os.environ["ENV_FILE"]

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
with open(sys.argv[2], encoding="utf-8") as handle:
    source_lines = handle.read().splitlines()
with open(sys.argv[3], encoding="utf-8") as handle:
    uninterpolated = json.load(handle)

services = config.get("services") or {}
raw_services = uninterpolated.get("services") or {}
problems = []


def strip_comment(line):
    """Drop a trailing YAML comment.

    `image: <literal> # ${TINYASSETS_IMAGE}` passed the substring check while
    the effective image was a literal (Codex round 3, S3). A `#` only starts a
    comment at the start of a line or after whitespace, which is enough for this
    file -- no value here contains a quoted `#`.
    """
    for position, char in enumerate(line):
        if char == "#" and (position == 0 or line[position - 1] in " 	"):
            return line[:position]
    return line


source_stripped = [strip_comment(line) for line in source_lines]


def indent_of(line):
    return len(line) - len(line.lstrip())


def daemon_image_lines():
    """`image:` lines of services.daemon, and nothing else.

    Anchored at a TOP-LEVEL `services:` key and its direct child `daemon:`: an
    earlier `x-anything:` extension mapping with its own indented `daemon:`
    block would otherwise be picked up first and satisfy the check while the
    real service used a literal.
    """
    services_at = None
    for index, line in enumerate(source_stripped):
        if indent_of(line) == 0 and re.match(r"^services:\s*$", line):
            services_at = index
            break
    if services_at is None:
        return None

    child_indent = None
    daemon_at = None
    for index in range(services_at + 1, len(source_stripped)):
        line = source_stripped[index]
        if not line.strip():
            continue
        if indent_of(line) == 0:
            break  # the next top-level key ends the services mapping
        if child_indent is None:
            child_indent = indent_of(line)
        if indent_of(line) == child_indent and re.match(r"^\s*daemon:\s*$", line):
            daemon_at = index
            break
    if daemon_at is None or child_indent is None:
        return None

    lines = []
    for index in range(daemon_at + 1, len(source_stripped)):
        line = source_stripped[index]
        if not line.strip():
            continue
        if indent_of(line) <= child_indent:
            break  # the next service, or the end of the mapping
        lines.append(line)
    return [line for line in lines if re.match(r"^\s*image:\s*\S", line)]


image_lines = daemon_image_lines()
if image_lines is None:
    problems.append(
        "no top-level `services:` mapping with a `daemon:` child in the source file"
    )
    image_lines = []
if not image_lines:
    problems.append("no `image:` line found in the daemon block of the source file")
elif "${TINYASSETS_IMAGE" not in image_lines[0]:
    problems.append(
        "daemon image line does not interpolate ${TINYASSETS_IMAGE}: %r"
        % (image_lines[0].strip(),)
    )

expected_services = {"daemon", "cloudflared", "logs"}
if set(services) != expected_services:
    problems.append(
        "default service set is %s, expected %s"
        % (sorted(services), sorted(expected_services))
    )


def svc(name):
    value = services.get(name)
    return value if isinstance(value, dict) else {}


for service, container in (
    ("daemon", "tinyassets-daemon"),
    ("cloudflared", "tinyassets-tunnel"),
    ("logs", "tinyassets-logs"),
):
    got = svc(service).get("container_name")
    if got != container:
        problems.append("%s.container_name is %r, expected %r" % (service, got, container))
    restart = svc(service).get("restart")
    if restart != "unless-stopped":
        problems.append("%s.restart is %r, expected 'unless-stopped'" % (service, restart))

image = svc("daemon").get("image")
if image != expect_image:
    problems.append(
        "daemon.image resolved to %r; it must interpolate ${TINYASSETS_IMAGE} "
        "(candidate %r)" % (image, expect_image)
    )

# The sidecars carry no ${TINYASSETS_IMAGE}, so nothing above constrains them at
# all: an arbitrary or unpinned cloudflared/vector image passed every check
# (Codex round 2, §2). Both must be the expected upstream repo AND digest-pinned.
for service, prefix in (
    ("cloudflared", "cloudflare/cloudflared:"),
    ("logs", "timberio/vector:"),
):
    sidecar_image = svc(service).get("image") or ""
    if not sidecar_image.startswith(prefix):
        problems.append(
            "%s.image is %r, expected an image starting %r"
            % (service, sidecar_image, prefix)
        )
    if "@sha256:" not in sidecar_image:
        problems.append("%s.image %r is not digest-pinned" % (service, sidecar_image))

# The daemon's own posture. A compose file that starts a daemon with no env
# file, no data volume and no healthcheck converges "successfully" and serves
# nothing: no secrets, an empty /data, and a container docker will never report
# unhealthy no matter what it is doing.
# Read env_file from the uninterpolated render (Compose v5 drops it from the
# interpolated one); fall back to the interpolated render for older Compose.
raw_daemon = raw_services.get("daemon")
raw_daemon = raw_daemon if isinstance(raw_daemon, dict) else {}
daemon_env_files = raw_daemon.get("env_file") or svc("daemon").get("env_file") or []
env_file_paths = [
    entry if isinstance(entry, str) else (entry or {}).get("path", "")
    for entry in daemon_env_files
]
if env_file not in env_file_paths:
    problems.append(
        "daemon.env_file is %s; it must include %r or the daemon starts with no "
        "secrets at all" % (sorted(str(p) for p in env_file_paths), env_file)
    )

daemon_data_mount = None
for volume in svc("daemon").get("volumes") or []:
    if isinstance(volume, str):
        parts = volume.split(":")
        if len(parts) >= 2 and parts[1] == "/data":
            daemon_data_mount = parts[0]
    elif isinstance(volume, dict) and volume.get("target") == "/data":
        daemon_data_mount = volume.get("source")
if daemon_data_mount != "tinyassets-data":
    problems.append(
        "daemon has no /data volume from 'tinyassets-data' (found %r); every "
        "universe, both auth bundles and the OAuth db live there"
        % (daemon_data_mount,)
    )

if not svc("daemon").get("healthcheck"):
    problems.append(
        "daemon has no healthcheck; this script's accept() would then wait on a "
        "verdict docker will never produce"
    )

daemon_environment = svc("daemon").get("environment") or {}
if isinstance(daemon_environment, list):
    daemon_environment = dict(
        entry.split("=", 1) for entry in daemon_environment if "=" in str(entry)
    )
if str(daemon_environment.get("TINYASSETS_DATA_DIR")) != "/data":
    problems.append(
        "daemon environment TINYASSETS_DATA_DIR is %r, expected '/data' — the "
        "resolver would otherwise write beside the mount, not into it"
        % (daemon_environment.get("TINYASSETS_DATA_DIR"),)
    )


def as_bytes(value):
    """compose emits mem_limit as bytes, but tolerate a '4g'-style string."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        multiplier = 1
        for suffix, factor in (
            ("gb", 1024 ** 3),
            ("mb", 1024 ** 2),
            ("kb", 1024),
            ("g", 1024 ** 3),
            ("m", 1024 ** 2),
            ("k", 1024),
            ("b", 1),
        ):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                multiplier = factor
                break
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return None
    return None


raw_mem = svc("daemon").get("mem_limit")
if raw_mem is None:
    raw_mem = (
        ((svc("daemon").get("deploy") or {}).get("resources") or {})
        .get("limits", {})
        .get("memory")
    )
mem = as_bytes(raw_mem)
if not mem or mem <= 0:
    problems.append(
        "daemon.mem_limit is %r; a positive limit is required (docker reported "
        "mem_limit=0 on 2026-08-28 and the daemon could consume the box)" % (raw_mem,)
    )

want_mounts = {
    "%s/deploy/vector.yaml" % runtime,
    "%s/deploy/vector-betterstack.yaml" % runtime,
    "%s/deploy/vector-entrypoint.sh" % runtime,
}
binds = {}
for volume in svc("logs").get("volumes") or []:
    if isinstance(volume, str):
        parts = volume.split(":")
        if len(parts) < 2:
            continue
        binds[parts[0]] = len(parts) > 2 and "ro" in parts[2].split(",")
    elif isinstance(volume, dict):
        if volume.get("type") != "bind":
            continue
        binds[volume.get("source")] = bool(volume.get("read_only"))

if set(binds) != want_mounts:
    problems.append(
        "logs bind mounts are %s, expected exactly %s"
        % (sorted(str(key) for key in binds), sorted(want_mounts))
    )
for source, read_only in sorted(binds.items(), key=lambda item: str(item[0])):
    if not read_only:
        problems.append("logs mount %s is not read-only" % (source,))

if problems:
    for problem in problems:
        sys.stderr.write("::error::staged bundle rejected: %s\n" % problem)
    sys.exit(1)

print(
    "[deploy-fail-safe] bundle validated: services=%s, daemon image + mem_limit ok, "
    "logs mounts read-only" % sorted(services)
)
PY
  rc=$?
  rm -f "$cfg" "${cfg}.err" "${cfg}.raw" "${cfg}.raw.err"
  return $rc
}

# Copy what is LIVE into a stamped snapshot directory. Runs before install, so
# the snapshot is exactly the state a rollback has to get back to. A destination
# that does not exist yet is recorded as a `.absent` marker so a restore removes
# it again rather than leaving a file this deploy created.
snapshot_bundle() {
  local stamp snap entry rel dest mode owner old
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  # mktemp, not a bare stamp: two deploys inside the same UTC second would share
  # a directory, and the second would snapshot the files the FIRST installed --
  # silently replacing the rollback target with the state being rolled back
  # from. The stamp stays the prefix so retention can sort lexically.
  if ! mkdir -p "$SNAPSHOT_ROOT"; then
    err "cannot create snapshot root ${SNAPSHOT_ROOT}"
    return 1
  fi
  snap="$(mktemp -d "${SNAPSHOT_ROOT}/${stamp}-XXXXXX")" || {
    err "cannot create a snapshot directory under ${SNAPSHOT_ROOT}"
    return 1
  }
  if ! mkdir -p "${snap}/deploy" "${snap}/systemd"; then
    err "cannot create snapshot directory ${snap}"
    return 1
  fi
  # The manifest is what makes this an EXACT restoration. Forcing the current
  # ownership contract on the way back would rewrite live `/opt/tinyassets/
  # compose.yml` from root:root to tinyassets:tinyassets — a rollback that
  # changes something (Codex round 2, §3). Record what was there; put that back.
  : >"${snap}/manifest" || { err "snapshot: cannot create ${snap}/manifest"; return 1; }
  chmod 600 "${snap}/manifest" 2>/dev/null || true
  for entry in "${BUNDLE_MAP[@]}"; do
    IFS='|' read -r rel dest mode owner <<<"$entry"
    if [ -f "$dest" ]; then
      if ! cp -p "$dest" "${snap}/${rel}"; then
        err "snapshot: cannot copy ${dest} into ${snap}"
        return 1
      fi
      local meta
      meta="$(stat -c '%u %g %a' "$dest" 2>/dev/null)" || {
        err "snapshot: cannot stat ${dest}"
        return 1
      }
      printf '%s|present|%s\n' "$rel" "$meta" >>"${snap}/manifest" || {
        err "snapshot: cannot record ${rel} in the manifest"
        return 1
      }
    else
      log "snapshot: ${dest} is absent; recorded so a restore removes it"
      : >"${snap}/${rel}.absent" || { err "snapshot: cannot mark ${rel} absent"; return 1; }
      printf '%s|absent|\n' "$rel" >>"${snap}/manifest" || {
        err "snapshot: cannot record ${rel} in the manifest"
        return 1
      }
    fi
  done
  SNAPSHOT_PATH="$snap"
  log "bundle snapshot written to ${snap}"
  return 0
}

# Retention runs AFTER the pointer advances, and never deletes what the pointer
# names. Pruning before the advance meant a run of failed installs produced
# newer snapshots while the pointer stayed put, until retention deleted the
# rollback target out from under it (Codex round 2, §3).
prune_snapshots() {
  local keep old pointed
  pointed="$(read_pointer || true)"
  pointed="${pointed%/}"
  while IFS= read -r old; do
    [ -n "$old" ] || continue
    old="${old%/}"
    if [ -n "$pointed" ] && [ "$old" = "$pointed" ]; then
      log "retention: keeping ${old} — the bundle pointer names it"
      continue
    fi
    rm -rf "$old"
  done < <(ls -1d "${SNAPSHOT_ROOT}"/*/ 2>/dev/null | sort | head -n "-${BUNDLE_KEEP}")
  return 0
}

install_bundle() {
  local entry rel dest mode owner src file_owner file_group
  if ! mkdir -p "${RUNTIME_DIR}/deploy"; then
    err "cannot create ${RUNTIME_DIR}/deploy"
    return 1
  fi
  if ! mkdir -p "$(dirname "$UNIT_FILE")"; then
    err "cannot create $(dirname "$UNIT_FILE")"
    return 1
  fi
  # INSTALLED_THIS_RUN flips on the first byte, not on success: a failure after
  # this point is what the restore and the dirty marker exist for.
  INSTALLED_THIS_RUN=1
  for entry in "${BUNDLE_MAP[@]}"; do
    IFS='|' read -r rel dest mode owner <<<"$entry"
    src="${BUNDLE_WORK}/$(basename "$rel")"
    if [ "$owner" = "unit" ]; then
      file_owner="$UNIT_OWNER"; file_group="$UNIT_GROUP"
    else
      file_owner="$RUNTIME_OWNER"; file_group="$RUNTIME_GROUP"
    fi
    if ! install -m "$mode" -o "$file_owner" -g "$file_group" "$src" "$dest"; then
      err "failed to install ${src} -> ${dest}"
      return 1
    fi
    log "installed ${dest} (mode ${mode}, owner ${file_owner}:${file_group})"
  done
  if ! systemctl daemon-reload; then
    err "systemctl daemon-reload failed after installing ${UNIT_FILE}"
    return 1
  fi
  return 0
}

# Reinstall a snapshot over the live paths, restoring the uid/gid/mode the
# manifest recorded rather than re-asserting the forward install's contract.
# A snapshot with no manifest is REFUSED: guessing the ownership is how a
# rollback silently changes something.
restore_bundle_from() {
  local snap="$1" entry rel dest mode owner rc=0 line state meta uid gid perms
  if [ ! -f "${snap}/manifest" ]; then
    err "restore: snapshot ${snap} has no manifest; refusing to guess ownership"
    return 1
  fi
  for entry in "${BUNDLE_MAP[@]}"; do
    IFS='|' read -r rel dest mode owner <<<"$entry"
    # Exact key match on field 1. `grep -F "${rel}|"` was a SUBSTRING match, so a
    # missing `compose.yml|` row silently matched `deploy/compose.yml|` and the
    # root compose file was restored with the deploy copy's uid/gid/mode --
    # `deployed` over a tree that is not the snapshot's (Codex round 3, §1).
    line="$(awk -F'|' -v k="$rel" '$1 == k { print; exit }' "${snap}/manifest" 2>/dev/null || true)"
    if [ -z "$line" ]; then
      err "restore: snapshot ${snap} manifest has no row for ${rel}"
      rc=1
      continue
    fi
    state="$(printf '%s' "$line" | cut -d'|' -f2)"
    meta="$(printf '%s' "$line" | cut -d'|' -f3)"
    if [ "$state" = "absent" ]; then
      rm -f "$dest" || { err "restore: cannot remove ${dest}"; rc=1; }
      continue
    fi
    if [ ! -f "${snap}/${rel}" ]; then
      err "restore: snapshot ${snap} claims ${rel} is present but the file is missing"
      rc=1
      continue
    fi
    uid="$(printf '%s' "$meta" | awk '{print $1}')"
    gid="$(printf '%s' "$meta" | awk '{print $2}')"
    perms="$(printf '%s' "$meta" | awk '{print $3}')"
    if [ -z "$uid" ] || [ -z "$gid" ] || [ -z "$perms" ]; then
      err "restore: manifest row for ${rel} is malformed ('${line}')"
      rc=1
      continue
    fi
    if ! install -m "$perms" -o "$uid" -g "$gid" "${snap}/${rel}" "$dest"; then
      err "restore: failed to reinstall ${dest} from ${snap}"
      rc=1
      continue
    fi
    log "restored ${dest} (mode ${perms}, owner ${uid}:${gid})"
  done
  if ! systemctl daemon-reload; then
    err "systemctl daemon-reload failed during bundle restore"
    rc=1
  fi
  return $rc
}

# Has this box EVER installed a bundle? Distinguishes "nothing to roll back"
# from "the rollback contract is broken". Both look like a missing pointer.
bundle_history_exists() {
  [ -f "$BUNDLE_POINTER" ] && return 0
  [ -f "$BUNDLE_DIRTY" ] && return 0
  [ -d "$SNAPSHOT_ROOT" ] && [ -n "$(ls -A "$SNAPSHOT_ROOT" 2>/dev/null)" ] && return 0
  return 1
}

# Restore whatever the pointer names, recording whether vector inputs moved.
#   0  restored, or this box has never installed a bundle (image-only)
#   1  the rollback contract is broken: pointer missing while snapshots exist,
#      pointer naming a missing snapshot, or a restore that did not complete
# Callers treat 1 as FATAL. Previously this was best-effort and the caller kept
# going, so a half-restored bundle could still be reported `rolled_back` /
# `deployed` (Codex round 2, §1) — a success receipt over a mixed tree.
restore_previous_bundle() {
  local snap before after rc target_rc
  snap="$(restore_target)"; target_rc=$?
  snap="${snap%/}"
  if [ "$target_rc" = "2" ]; then
    err "bundle: ${BUNDLE_DIRTY} exists but is EMPTY -- a bundle install was interrupted and recorded no snapshot."
    err "refusing to fall through to ${BUNDLE_POINTER}: that names the last GOOD state, not the interrupted one, and restoring it would report success over a tree nobody has accounted for."
    err "inspect ${SNAPSHOT_ROOT} and point ${BUNDLE_DIRTY} at the right snapshot by hand."
    return 1
  fi
  if [ -z "$snap" ]; then
    if bundle_history_exists; then
      err "bundle: no pointer and no dirty marker, but this box has bundle state; refusing to report a rollback that did not happen"
      return 1
    fi
    log "bundle: no bundle has ever been installed here; image-only rollback"
    return 0
  fi
  if [ ! -d "$snap" ]; then
    err "bundle pointer names a missing snapshot '${snap}'; cannot restore"
    return 1
  fi
  RESTORE_SNAPSHOT="$snap"
  log "restoring runtime bundle from ${snap}"
  before="$(vector_fingerprint)"
  restore_bundle_from "$snap"
  rc=$?
  after="$(vector_fingerprint)"
  if [ "$before" != "$after" ]; then
    VECTOR_CHANGED=1
    log "bundle restore changed the vector inputs the running ${LOGS_CONTAINER} started from"
  fi
  return $rc
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
if [ "$RESTORE_BUNDLE" = "1" ]; then
  log "mode: --restore-bundle (reinstall the previous bundle, then converge ${NEW_IMAGE})"
fi

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

# --- 3b. the runtime bundle: validate -> snapshot -> install ---------------
if ! ensure_state_dir; then
  err "cannot prepare ${BUNDLE_STATE_DIR}; refusing (prod untouched)"
  echo "deploy_result=bundle_invalid"
  exit 1
fi

# Restore the snapshot recorded before the failed install, and clear the dirty
# marker only if that restore completes. Used by every post-install failure
# path so none of them can report success over a mixed tree.
recover_from_failed_install() {
  local result="$1"
  err "restoring ${SNAPSHOT_PATH} and leaving the pointer where it was"
  if restore_bundle_from "$SNAPSHOT_PATH"; then
    clear_dirty || true
    finish "$result" "" 1
  fi
  err "restore from ${SNAPSHOT_PATH} ALSO failed — ${BUNDLE_DIRTY} stays, and the next normal deploy will refuse until --restore-bundle clears it"
  echo "deploy_result=rollback_failed"
  exit 3
}

if [ "$RESTORE_BUNDLE" = "1" ]; then
  # Undoing an install, never performing one: the staged bundle (if it is even
  # still on the box) is exactly what this run is rolling back. This path runs
  # even with the dirty marker set — it is the way out of that state.
  if ! restore_previous_bundle; then
    err "--restore-bundle could not restore the previous bundle; refusing to converge an image over a bundle in an unknown state"
    [ -n "$RESTORE_SNAPSHOT" ] && { mark_dirty "$RESTORE_SNAPSHOT" || true; }
    echo "deploy_result=rollback_failed"
    exit 3
  fi
  clear_dirty || true
else
  if [ -f "$BUNDLE_DIRTY" ]; then
    err "a previous bundle install did not finish and was not restored (${BUNDLE_DIRTY} exists)."
    err "refusing: snapshotting this tree would legitimize a mixed bundle as the rollback target."
    err "run: sudo bash $0 --restore-bundle <image ref>"
    echo "deploy_result=bundle_dirty"
    exit 1
  fi
  BUNDLE_STATE="$(bundle_state)"
  case "$BUNDLE_STATE" in
    absent)
      log "bundle: absent, image-only deploy"
      ;;
    partial)
      err "bundle: ${BUNDLE_DIR} exists but is incomplete; refusing to install a partial bundle (prod untouched)"
      echo "deploy_result=bundle_invalid"
      exit 1
      ;;
    ready)
      if ! claim_bundle; then
        err "could not take a private copy of the staged bundle (prod untouched)"
        echo "deploy_result=bundle_invalid"
        exit 1
      fi
      if ! validate_bundle; then
        err "staged bundle failed validation; refusing to install it. prod untouched"
        echo "deploy_result=bundle_invalid"
        exit 1
      fi
      if ! snapshot_bundle; then
        err "could not snapshot the live runtime files; refusing to install (prod untouched)"
        echo "deploy_result=bundle_invalid"
        exit 1
      fi
      if ! mark_dirty "$SNAPSHOT_PATH"; then
        err "cannot record the dirty marker; refusing to install without it (prod untouched)"
        echo "deploy_result=bundle_invalid"
        exit 1
      fi
      BUNDLE_VECTOR_BEFORE="$(vector_fingerprint)"
      if ! install_bundle; then
        err "bundle install failed part-way"
        recover_from_failed_install bundle_install_failed
      fi
      if [ "$BUNDLE_VECTOR_BEFORE" != "$(vector_fingerprint)" ]; then
        VECTOR_CHANGED=1
        log "vector inputs changed in this bundle"
      fi
      # Only NOW is the pointer allowed to move: it must name the snapshot that
      # this install replaced, so a rollback restores exactly that. A pointer
      # that did not advance is FATAL — every later rollback would read the
      # previous deploy's snapshot and restore a bundle that was never live.
      if ! write_pointer "$SNAPSHOT_PATH"; then
        err "could not advance ${BUNDLE_POINTER} to ${SNAPSHOT_PATH}; a rollback would restore a stale bundle"
        recover_from_failed_install bundle_pointer_failed
      fi
      clear_dirty || true
      prune_snapshots
      ;;
    *)
      err "unexpected bundle state '${BUNDLE_STATE}'"
      echo "deploy_result=bundle_invalid"
      exit 1
      ;;
  esac
fi

# --- 4. swap + restart ----------------------------------------------------
log "swapping TINYASSETS_IMAGE and converging the stack"
if ! set_image "$NEW_IMAGE"; then
  err "could not record TINYASSETS_IMAGE=${NEW_IMAGE} in ${ENV_FILE}"
  if [ "$INSTALLED_THIS_RUN" = "1" ]; then
    err "restoring the runtime bundle so the box is not left on a new config under the old image"
    if ! restore_bundle_from "$SNAPSHOT_PATH"; then
      err "bundle restore failed — inspect ${SNAPSHOT_PATH}"
      mark_dirty "$SNAPSHOT_PATH" || true
      echo "deploy_result=rollback_failed"
      exit 3
    fi
  fi
  echo "deploy_result=failed_env_write"
  exit 1
fi
# A failed converge is NOT recoverable by waiting: compose may have brought up
# some services and not others, and accept() on a partially converged stack is
# how a mixed state earns a success receipt (Codex round 2, §1).
CONVERGED=1
restart_stack || CONVERGED=0
if [ "$CONVERGED" = "1" ] && [ "$VECTOR_CHANGED" = "1" ]; then
  recreate_logs || CONVERGED=0
fi

# --- 5. accept the new image (healthy + RUNNING it + tunnel + logs up) -----
if [ "$CONVERGED" = "1" ] && accept "$NEW_IMAGE"; then
  log "deploy healthy on ${NEW_IMAGE}"
  finish deployed "$NEW_IMAGE" 0
fi

# --- 6. unhealthy -> restore the bundle, then roll back the image ---------
err "new image did not become acceptable; rolling back"
if [ -z "$PREV_IMAGE" ]; then
  err "no previous image recorded; cannot roll back automatically"
  echo "deploy_result=failed_no_rollback_target"
  exit 3
fi
# Config first, then the image: converging the previous image against the NEW
# compose file is what left 2026-08's rollbacks running a config prod had never
# been healthy on.
#
# Only if THIS run installed a bundle. An image-only deploy that fails must not
# touch a pointer left by an earlier bundle deploy — that pointer names the
# state before THAT deploy, so restoring it here would change a bundle this run
# never modified (Codex round 2, §1).
VECTOR_CHANGED=0
if [ "$INSTALLED_THIS_RUN" = "1" ]; then
  if ! restore_previous_bundle; then
    err "the runtime bundle could not be restored; refusing to report a rollback over a bundle in an unknown state"
    mark_dirty "$SNAPSHOT_PATH" || true
    echo "deploy_result=rollback_failed"
    exit 3
  fi
  clear_dirty || true
else
  log "bundle: this run installed none; leaving the runtime files untouched during the image rollback"
fi
if ! set_image "$PREV_IMAGE"; then
  err "could not record rollback image ${PREV_IMAGE} in ${ENV_FILE} — manual intervention required"
  echo "deploy_result=rollback_env_write_failed"
  exit 3
fi
if ! restart_stack; then
  err "the rollback converge failed — manual intervention required"
  echo "deploy_result=rollback_failed"
  exit 3
fi
if [ "$VECTOR_CHANGED" = "1" ] && ! recreate_logs; then
  err "the restored vector config could not be brought up; log forwarding is down on the rolled-back stack"
  echo "deploy_result=rollback_failed"
  exit 3
fi
if accept "$PREV_IMAGE"; then
  log "rolled back to previous image ${PREV_IMAGE} (healthy)"
  finish rolled_back "$PREV_IMAGE" 2
fi

err "rollback to ${PREV_IMAGE} ALSO did not become acceptable — manual intervention required"
echo "deploy_result=rollback_unhealthy"
exit 3
