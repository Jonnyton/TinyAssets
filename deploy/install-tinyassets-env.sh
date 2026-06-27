#!/usr/bin/env bash
# install-tinyassets-env.sh — atomic edit of /etc/tinyassets/env.
#
# Replaces every existing `sudo sed -i ... /etc/tinyassets/env && sudo
# chown root:tinyassets ... && sudo chmod 640 ...` chain (CI workflows +
# any future call site) with a single atomic write that cannot leave
# the file in a wrong-perm state.
#
# Background — `/etc/tinyassets/env` mode-flip class
# ------------------------------------------------
# `sed -i` writes a temp file then `rename(2)`s it over the target. The
# new inode is created with default ownership (root:root) and umask-
# derived mode (typically 0600). Any error or signal between the `sed`
# and the follow-up `chown + chmod` leaves the file unreadable by the
# `tinyassets` user → systemd unit's `ExecStartPre=test -r` fails →
# docker compose silently crash-loops → cloudflared never starts →
# public endpoint dark. Root cause of the 2026-04-21 P0 outage.
#
# `install -m 640 -o root -g tinyassets` writes the new file at the
# target path with the correct owner and perms in a single syscall
# sequence, leaving NO intermediate state with wrong perms. Closes
# RC-1 from `docs/audits/2026-04-25-etc-workflow-env-mode-flip.md`.
#
# Usage (from a CI workflow over SSH)
# -----------------------------------
#   # Set/replace a key — value comes from stdin (multi-line OK):
#   echo "ghcr.io/jonnyton/tinyassets-daemon:abc123" \
#     | ssh "$DROPLET" 'sudo bash -s -- set TINYASSETS_IMAGE' \
#     < deploy/install-tinyassets-env.sh
#
#   # Delete one or more keys (no stdin needed):
#   ssh "$DROPLET" 'sudo bash -s -- delete TINYASSETS_WIKI_PATH' \
#     < deploy/install-tinyassets-env.sh
#
# Idempotency
# -----------
# `set` is idempotent — running twice with the same value is a no-op
# from the file's perspective (same content, same mode, same owner).
# `delete` is idempotent — deleting an already-absent key is a no-op.
#
# Required privilege
# ------------------
# Must run as root (`sudo bash -s --` over SSH). The script `exec`s
# `install(1)` which needs root to chown to root:tinyassets.
#
# Exit codes
# ----------
#   0  success — file rewritten with new content (or no-op for absent
#      delete targets), owner=root:tinyassets, mode=640, readable by the
#      tinyassets user (post-write assert passes).
#   1  bad invocation (unknown subcommand, missing args, missing key
#      name, value containing forbidden chars).
#   2  /etc/tinyassets/env missing — bootstrap should have created it.
#   3  install(1) failed.
#   4  post-write readability assert failed (tinyassets user cannot read).

set -euo pipefail

ENV_FILE="/etc/tinyassets/env"
ENV_OWNER="root:tinyassets"
ENV_MODE="640"

usage() {
    cat >&2 <<'EOF'
Usage:
  install-tinyassets-env.sh set <KEY>           # value on stdin
  install-tinyassets-env.sh delete <KEY> [KEY...]
EOF
    exit 1
}

# Validate KEY: env var name shape (letters, digits, underscore; not
# starting with a digit). Refusing odd characters keeps the sed
# expression safe under any caller.
validate_key() {
    local key="$1"
    if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "::error::invalid env key: ${key}" >&2
        exit 1
    fi
}

# Read current file content. Required-exists — the bootstrap creates
# this file on first install, so absence is a real failure not a
# silent create-on-write.
require_env_file() {
    if [ ! -f "${ENV_FILE}" ]; then
        echo "::error::${ENV_FILE} missing — bootstrap should have created it" >&2
        exit 2
    fi
}

# Atomic write of a buffer to ENV_FILE with correct owner + mode.
# install(1) creates the target with the requested mode/owner in one
# step; no intermediate 0600 root:root state is ever observable.
atomic_install() {
    local content="$1"
    if ! printf '%s' "${content}" \
            | install -m "${ENV_MODE}" -o root -g tinyassets \
                /dev/stdin "${ENV_FILE}"; then
        echo "::error::install(1) failed writing ${ENV_FILE}" >&2
        exit 3
    fi
}

# Confirm the tinyassets user can actually read the file. This is the
# canary that the systemd unit's ExecStartPre would have tripped on.
assert_readable() {
    if ! sudo -u tinyassets test -r "${ENV_FILE}"; then
        echo "::error::ENV-UNREADABLE: ${ENV_FILE} not readable by user tinyassets after install" >&2
        ls -l "${ENV_FILE}" >&2 || true
        exit 4
    fi
}

cmd_set() {
    local key="$1"
    validate_key "${key}"
    require_env_file

    # Read new value from stdin (verbatim, including any trailing
    # newline the caller piped in — but we strip a single trailing
    # newline so `echo "foo" | ...` produces `KEY=foo` not `KEY=foo\n`
    # appearing as `KEY=foo` followed by a blank entry line).
    local value
    value="$(cat)"
    value="${value%$'\n'}"

    # Build new content: replace the existing KEY= line, or append if
    # absent. Done in awk for correctness with values containing `|`,
    # `&`, `\`, etc. that would break a `sed s|...|...|` expression.
    local new_content
    new_content="$(awk -v k="${key}" -v v="${value}" '
        BEGIN { found = 0 }
        $0 ~ "^" k "=" { print k "=" v; found = 1; next }
        { print }
        END { if (!found) print k "=" v }
    ' "${ENV_FILE}")"

    atomic_install "${new_content}"$'\n'
    assert_readable
    echo "set ${key} (${ENV_FILE} root:tinyassets ${ENV_MODE})"
}

cmd_delete() {
    local key
    require_env_file

    # Build a single awk filter that drops every requested KEY= line
    # in one pass.
    local awk_expr=""
    for key in "$@"; do
        validate_key "${key}"
        awk_expr+="\$0 ~ \"^${key}=\" { next } "
    done
    awk_expr+="{ print }"

    local new_content
    new_content="$(awk "${awk_expr}" "${ENV_FILE}")"

    atomic_install "${new_content}"$'\n'
    assert_readable
    echo "deleted: $* (${ENV_FILE} root:tinyassets ${ENV_MODE})"
}

[ $# -ge 1 ] || usage
subcmd="$1"
shift

case "${subcmd}" in
    set)
        [ $# -eq 1 ] || usage
        cmd_set "$1"
        ;;
    delete)
        [ $# -ge 1 ] || usage
        cmd_delete "$@"
        ;;
    *)
        usage
        ;;
esac
