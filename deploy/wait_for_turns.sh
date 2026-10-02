#!/usr/bin/env bash
# Hold a deploy while the live daemon is running someone's work. Runs on the
# GitHub runner, NOT the droplet: it reaches the droplet over ssh.
#
# A deploy recreates the daemon, and that kills every turn running in it: on
# 2026-10-02 it cut the founder's live village turn twice. Each poll pipes
# scripts/turns_in_flight.py into the RUNNING container (so it works whatever
# image that is) and asks whether anything is in flight: seats a live process
# holds, or graph runs a live process owns. The loop proceeds on
#   idle                    nothing in flight
#   daemon_not_serving      container absent, stopped or unhealthy: nothing to
#                           protect, and the deploy may be its fix
#   check_unavailable       three unanswerable polls in a row; "cannot tell" is
#                           never read as idle, and never holds prod on an old image
#   yield_to_host_mutation  a recovery workflow (YIELD_WORKFLOWS) is queued behind
#                           this run's concurrency group; a P0 repair must not
#                           wait out a 45 min turn, so the deploy goes now
#   cap_reached             TURN_WAIT_CAP_S elapsed; the startup reconcile then
#                           tells the user their turn was cut off
#
# "idle" is a moment, not a promise: a turn can start between the last poll and
# the swap, and the 20s drain bound then cuts it. IMAGE_REF is pulled BEFORE the
# wait so the fail-safe's own pull is a no-op, which leaves the candidate proof
# plus the converge as the window rather than a 2.7 GB download. Closing it
# entirely needs an admission hold, and that ships only together with
# persist-and-replay of the held messages.
#
# Every remote call is bounded (CHECK_TIMEOUT_S plus ssh keepalives): a hung ssh
# or docker exec counts as "cannot tell"; it must not stall past the cap.
#
# Env: DO_SSH_USER DO_DROPLET_HOST TURN_WAIT_CAP_S TURN_POLL_S GITHUB_OUTPUT;
#      optional TARGET_REVISION RUN_URL IMAGE_REF CHECK_TIMEOUT_S, and
#      YIELD_WORKFLOWS with GH_TOKEN + GITHUB_REPOSITORY.
# Writes outcome / waited_s / polls to GITHUB_OUTPUT. Always exits 0.
#
# `set +e` on purpose: every poll's exit status is data (10 busy, 20 not
# serving, 2 unknown), and the step's `bash -e` must not turn "busy" into a
# failed deploy.
set +e
set -uo pipefail
: "${DO_SSH_USER:?}" "${DO_DROPLET_HOST:?}" "${TURN_WAIT_CAP_S:?}" "${TURN_POLL_S:?}"
: "${GITHUB_OUTPUT:?}"
TARGET_REVISION="${TARGET_REVISION:-}"
RUN_URL="${RUN_URL:-}"
CHECK_TIMEOUT_S="${CHECK_TIMEOUT_S:-90}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
probe="${here}/../scripts/turns_in_flight.py"
host="${DO_SSH_USER}@${DO_DROPLET_HOST}"
SSH_OPTS=(-i ~/.ssh/do_deploy -o BatchMode=yes -o ConnectTimeout=15
          -o ServerAliveInterval=10 -o ServerAliveCountMax=3)

remote() { timeout "${CHECK_TIMEOUT_S}" ssh "${SSH_OPTS[@]}" "${host}" "$@"; }

timeout "${CHECK_TIMEOUT_S}" scp "${SSH_OPTS[@]}" "${probe}" "${host}:/tmp/turns_in_flight.py" \
  || echo "::warning::could not ship the in-flight probe; polls will report unknown"

if [ -n "${IMAGE_REF:-}" ]; then
  # Adds only the image the fail-safe would pull anyway; touches no container.
  # A failure here is the fail-safe's to report.
  if timeout 900 ssh "${SSH_OPTS[@]}" "${host}" \
       "sudo docker pull -q $(printf '%q' "${IMAGE_REF}")" >/dev/null; then
    echo "prefetched ${IMAGE_REF}"
  else
    echo "::warning::prefetch of ${IMAGE_REF} failed; the fail-safe pulls it itself"
  fi
fi

# $@ = the probe's arguments. All generated here (a sha, epochs, our own run
# URL), never user text; printf %q keeps each one word anyway.
check() {
  local args
  args="$(printf ' %q' "$@")"
  remote "state=\$(sudo docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{end}}' tinyassets-daemon 2>/dev/null); \
    case \"\$state\" in running/healthy|running/) ;; *) echo \"daemon_state=\${state:-absent}\"; exit 20;; esac; \
    sudo docker exec -i tinyassets-daemon python -${args} < /tmp/turns_in_flight.py"
}

# Is a host-mutating recovery run queued behind us? "Cannot tell" counts as no.
recovery_waiting() {
  [ -n "${YIELD_WORKFLOWS:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ] || return 1
  local wf n
  for wf in ${YIELD_WORKFLOWS}; do
    n="$(timeout 30 gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/${wf}/runs?per_page=10" \
          --jq '[.workflow_runs[] | select(.status == "queued" or .status == "pending" or .status == "waiting" or .status == "requested")] | length' \
          2>/dev/null)" || continue
    if [ "${n:-0}" -gt 0 ] 2>/dev/null; then
      echo "::notice::${wf} is queued behind this deploy; not making it wait"
      return 0
    fi
  done
  return 1
}

start="$(date +%s)"
deadline=$(( start + TURN_WAIT_CAP_S ))
unknown=0
outcome=""
polls=0
while :; do
  polls=$(( polls + 1 ))
  out="$(check --mark-pending --target "${TARGET_REVISION}" \
           --waiting-since "${start}" --deadline "${deadline}" \
           --ttl $(( TURN_POLL_S * 4 )) --run-url "${RUN_URL}")"
  rc=$?
  printf '%s\n' "${out}"
  now="$(date +%s)"
  case "${rc}" in
    0)  outcome="idle"; break ;;
    20) outcome="daemon_not_serving"; break ;;
    10) unknown=0
        if recovery_waiting; then outcome="yield_to_host_mutation"; break; fi ;;
    *)  unknown=$(( unknown + 1 ))
        echo "::warning::in-flight check could not answer (rc=${rc}, ${unknown}/3)"
        if [ "${unknown}" -ge 3 ]; then outcome="check_unavailable"; break; fi ;;
  esac
  if [ "${now}" -ge "${deadline}" ]; then outcome="cap_reached"; break; fi
  sleep "${TURN_POLL_S}"
done
waited=$(( $(date +%s) - start ))
# The marker says "an update is waiting". Clear it whatever the outcome; a
# stale one also expires on its own (--ttl).
check --clear-pending >/dev/null 2>&1 || true
{
  echo "outcome=${outcome}"
  echo "waited_s=${waited}"
  echo "polls=${polls}"
} >> "${GITHUB_OUTPUT}"
case "${outcome}" in
  idle) echo "::notice::no work in flight after ${waited}s" ;;
  daemon_not_serving) echo "::notice::daemon not serving; nothing to protect" ;;
  check_unavailable) echo "::warning::in-flight check unavailable; proceeding without proof that no turn is running" ;;
  yield_to_host_mutation) echo "::warning::yielding to a queued recovery workflow; work in flight will be cut off by the restart" ;;
  cap_reached) echo "::warning::work still in flight after the ${TURN_WAIT_CAP_S}s cap; proceeding, and the turn will be reported as cut off by the restart" ;;
esac
exit 0
