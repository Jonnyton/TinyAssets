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
# STAGES the five files into $BUNDLE_STAGE and this script owns the transaction:
#
#   validate_bundle   `docker compose config` on the STAGED file with the
#                     production env file and the candidate image; asserts the
#                     production invariants (service set, container names,
#                     daemon memory limit, the logs read-only mounts), not just
#                     service names. A miss refuses with prod untouched.
#   snapshot_bundle   copies what is live into
#                     $BUNDLE_STATE_DIR/bundle-snapshots/<UTC stamp>/ (last 5 kept)
#   install_bundle    installs the staged files, daemon-reloads, records whether
#                     any vector input changed
#   <converge>        plus `up -d --force-recreate logs` when vector inputs
#                     changed — vector-entrypoint.sh copies the mounted files
#                     into /run/vector-config only at container start, so an
#                     unchanged image would otherwise keep the old config
#   restore           both rollback paths reinstall the snapshot the
#                     $BUNDLE_STATE_DIR/bundle-previous pointer names BEFORE
#                     converging the previous image
#
# The pointer only advances after a SUCCESSFUL install, so a rollback restores
# exactly the state that install replaced. An absent stage directory is not an
# error: it means "image-only deploy" (a manual run, or `--restore-bundle` on a
# box that never staged one). A PARTIAL stage directory is an error — half a
# bundle is the 2026-08 502.
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
#   0  deployed the new image (daemon healthy + cloudflared up)
#   1  refused before any host mutation (bad args / lock / pull / import /
#      invalid bundle) — prod untouched
#   2  new image unhealthy; rolled back to the previous image + bundle (healthy)
#   3  rollback also unhealthy — manual intervention required (loud)
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
# is authoritative until install_bundle copies it into place.
BUNDLE_STAGE="${BUNDLE_STAGE:-/tmp/tinyassets-bundle}"
BUNDLE_STATE_DIR="${BUNDLE_STATE_DIR:-/var/lib/tinyassets-deploy}"
SNAPSHOT_ROOT="${BUNDLE_STATE_DIR}/bundle-snapshots"
BUNDLE_POINTER="${BUNDLE_STATE_DIR}/bundle-previous"
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
# The staged source for each row is $BUNDLE_STAGE/<basename of the rel path>,
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

# "absent"  no stage directory at all -> image-only deploy, not an error
# "ready"   all five staged files present
# "partial" the directory exists but is incomplete -> refuse
bundle_state() {
  local f
  if [ ! -d "$BUNDLE_STAGE" ]; then printf 'absent'; return 0; fi
  for f in "${BUNDLE_FILES[@]}"; do
    if [ ! -f "${BUNDLE_STAGE}/${f}" ]; then printf 'partial'; return 0; fi
  done
  printf 'ready'
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
        -f "${BUNDLE_STAGE}/compose.yml" config --format json >"$cfg" 2>"${cfg}.err"; then
    err "staged compose.yml does not parse with ${ENV_FILE}: $(head -c 800 "${cfg}.err" 2>/dev/null)"
    rm -f "$cfg" "${cfg}.err"
    return 1
  fi
  RUNTIME_DIR="$RUNTIME_DIR" EXPECT_IMAGE="$NEW_IMAGE" python3 - "$cfg" <<'PY'
import json
import os
import sys

runtime = os.environ["RUNTIME_DIR"]
expect_image = os.environ["EXPECT_IMAGE"]

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)

services = config.get("services") or {}
problems = []

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
  rm -f "$cfg" "${cfg}.err"
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
  for entry in "${BUNDLE_MAP[@]}"; do
    IFS='|' read -r rel dest mode owner <<<"$entry"
    if [ -f "$dest" ]; then
      if ! cp -p "$dest" "${snap}/${rel}"; then
        err "snapshot: cannot copy ${dest} into ${snap}"
        return 1
      fi
    else
      log "snapshot: ${dest} is absent; recorded so a restore removes it"
      : >"${snap}/${rel}.absent" || { err "snapshot: cannot mark ${rel} absent"; return 1; }
    fi
  done
  SNAPSHOT_PATH="$snap"
  log "bundle snapshot written to ${snap}"
  # Keep the newest BUNDLE_KEEP snapshots; UTC stamps sort lexically.
  while IFS= read -r old; do
    [ -n "$old" ] && rm -rf "$old"
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
  for entry in "${BUNDLE_MAP[@]}"; do
    IFS='|' read -r rel dest mode owner <<<"$entry"
    src="${BUNDLE_STAGE}/$(basename "$rel")"
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
    err "note: systemctl daemon-reload failed after installing ${UNIT_FILE}"
  fi
  return 0
}

# Reinstall a snapshot over the live paths, with the same ownership rules the
# forward install uses.
restore_bundle_from() {
  local snap="$1" entry rel dest mode owner file_owner file_group rc=0
  for entry in "${BUNDLE_MAP[@]}"; do
    IFS='|' read -r rel dest mode owner <<<"$entry"
    if [ "$owner" = "unit" ]; then
      file_owner="$UNIT_OWNER"; file_group="$UNIT_GROUP"
    else
      file_owner="$RUNTIME_OWNER"; file_group="$RUNTIME_GROUP"
    fi
    if [ -f "${snap}/${rel}" ]; then
      if ! install -m "$mode" -o "$file_owner" -g "$file_group" "${snap}/${rel}" "$dest"; then
        err "restore: failed to reinstall ${dest} from ${snap}"
        rc=1
      fi
    elif [ -f "${snap}/${rel}.absent" ]; then
      rm -f "$dest" || { err "restore: cannot remove ${dest}"; rc=1; }
    else
      err "restore: snapshot ${snap} has no entry for ${rel}"
      rc=1
    fi
  done
  systemctl daemon-reload || err "note: systemctl daemon-reload failed during bundle restore"
  return $rc
}

# Restore whatever the pointer names, recording whether vector inputs moved.
# Returns 0 when there is nothing to restore (image-only) or the restore
# succeeded; 1 when a NAMED snapshot could not be restored. Callers keep going
# on 1: getting prod back onto the previous image matters more than a config
# file that is already wrong.
restore_previous_bundle() {
  local snap before after rc
  if [ ! -f "$BUNDLE_POINTER" ]; then
    log "bundle: no ${BUNDLE_POINTER} pointer; image-only rollback"
    return 0
  fi
  snap="$(cat "$BUNDLE_POINTER" 2>/dev/null || true)"
  if [ -z "$snap" ] || [ ! -d "$snap" ]; then
    err "bundle pointer names a missing snapshot '${snap}'; image-only rollback"
    return 1
  fi
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
if [ "$RESTORE_BUNDLE" = "1" ]; then
  # Undoing an install, never performing one: the staged bundle (if it is even
  # still on the box) is exactly what this run is rolling back.
  restore_previous_bundle || err "bundle restore incomplete; continuing with the image rollback"
else
  BUNDLE_STATE="$(bundle_state)"
  case "$BUNDLE_STATE" in
    absent)
      log "bundle: absent, image-only deploy"
      ;;
    partial)
      err "bundle: ${BUNDLE_STAGE} exists but is incomplete; refusing to install a partial bundle (prod untouched)"
      echo "deploy_result=bundle_invalid"
      exit 1
      ;;
    ready)
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
      BUNDLE_VECTOR_BEFORE="$(vector_fingerprint)"
      if ! install_bundle; then
        err "bundle install failed part-way; restoring ${SNAPSHOT_PATH}"
        restore_bundle_from "$SNAPSHOT_PATH" \
          || err "bundle restore after a failed install ALSO failed — inspect ${SNAPSHOT_PATH}"
        echo "deploy_result=bundle_install_failed"
        exit 1
      fi
      if [ "$BUNDLE_VECTOR_BEFORE" != "$(vector_fingerprint)" ]; then
        VECTOR_CHANGED=1
        log "vector inputs changed in this bundle"
      fi
      # Only NOW is the pointer allowed to move: it must name the snapshot that
      # this install replaced, so a rollback restores exactly that.
      if ! printf '%s\n' "$SNAPSHOT_PATH" >"$BUNDLE_POINTER"; then
        err "could not advance ${BUNDLE_POINTER} to ${SNAPSHOT_PATH}; rollback would restore a stale bundle"
      fi
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
  if [ -n "$SNAPSHOT_PATH" ]; then
    err "restoring the runtime bundle so the box is not left on a new config under the old image"
    restore_bundle_from "$SNAPSHOT_PATH" || err "bundle restore failed — inspect ${SNAPSHOT_PATH}"
  fi
  echo "deploy_result=failed_env_write"
  exit 1
fi
restart_stack || true
LOGS_OK=1
if [ "$VECTOR_CHANGED" = "1" ]; then
  recreate_logs || LOGS_OK=0
fi

# --- 5. accept the new image (healthy + RUNNING it + tunnel up) -----------
if [ "$LOGS_OK" = "1" ] && accept "$NEW_IMAGE"; then
  log "deploy healthy on ${NEW_IMAGE}"
  echo "deploy_result=deployed"
  echo "deployed_image=${NEW_IMAGE}"
  exit 0
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
VECTOR_CHANGED=0
restore_previous_bundle || err "bundle restore incomplete; continuing with the image rollback"
if ! set_image "$PREV_IMAGE"; then
  err "could not record rollback image ${PREV_IMAGE} in ${ENV_FILE} — manual intervention required"
  echo "deploy_result=rollback_env_write_failed"
  exit 3
fi
restart_stack || true
if [ "$VECTOR_CHANGED" = "1" ]; then
  recreate_logs || err "note: logs force-recreate failed during rollback; the daemon rollback continues"
fi
if accept "$PREV_IMAGE"; then
  log "rolled back to previous image ${PREV_IMAGE} (healthy)"
  echo "deploy_result=rolled_back"
  echo "deployed_image=${PREV_IMAGE}"
  exit 2
fi

err "rollback to ${PREV_IMAGE} ALSO did not become acceptable — manual intervention required"
echo "deploy_result=rollback_unhealthy"
exit 3
