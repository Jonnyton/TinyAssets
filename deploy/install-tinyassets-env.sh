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
#   # Set an immutable key once; a different existing value fails closed:
#   printf '%s' "$SECRET" | sudo bash install-tinyassets-env.sh set-once KEY
#
# Idempotency
# -----------
# `set` is idempotent — running twice with the same value is a no-op
# from the file's perspective (same content, same mode, same owner).
# `set-once` accepts an absent/empty key or the exact existing value and
# refuses replacement. It is for persisted HMAC roots that require a
# versioned migration before rotation.
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
#   2  env bootstrap failed before install(1).
#   3  install(1) failed.
#   4  post-write readability assert failed (tinyassets user cannot read).
#   5  set-once refused replacement of an existing non-empty value.

set -euo pipefail

ENV_FILE="${TINYASSETS_ENV_FILE-/etc/tinyassets/env}"
LEGACY_ENV_FILE="${TINYASSETS_LEGACY_ENV_FILE-/etc/workflow/env}"
ENV_OWNER="${TINYASSETS_ENV_OWNER-root:tinyassets}"
ENV_MODE="${TINYASSETS_ENV_MODE-640}"
ENV_READ_USER="${TINYASSETS_ENV_READ_USER-tinyassets}"
ENV_READ_USER_HOME="${TINYASSETS_ENV_READ_USER_HOME-/opt/tinyassets}"
ENV_READ_USER_SHELL="${TINYASSETS_ENV_READ_USER_SHELL-/usr/sbin/nologin}"
ACTIVE_BUILDER_PID=""

stop_content_builder() {
    if [ -n "${ACTIVE_BUILDER_PID}" ]; then
        kill -TERM "${ACTIVE_BUILDER_PID}" 2>/dev/null || true
        wait "${ACTIVE_BUILDER_PID}" 2>/dev/null || true
        ACTIVE_BUILDER_PID=""
    fi
    return 0
}

handle_signal() {
    local signal="$1"
    stop_content_builder
    trap - "${signal}"
    kill -s "${signal}" "$$"
}

trap stop_content_builder EXIT
trap 'handle_signal HUP' HUP
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

usage() {
    cat >&2 <<'EOF'
Usage:
  install-tinyassets-env.sh set <KEY>           # value on stdin
  install-tinyassets-env.sh set-once <KEY>      # immutable value on stdin
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

env_owner_user() {
    printf '%s' "${ENV_OWNER%%:*}"
}

env_owner_group() {
    if [[ "${ENV_OWNER}" == *:* ]]; then
        printf '%s' "${ENV_OWNER#*:}"
    else
        id -gn "$(env_owner_user)" 2>/dev/null || id -gn
    fi
}

owner_label() {
    if [ -n "${ENV_OWNER}" ]; then
        printf '%s' "${ENV_OWNER}"
    else
        printf '<current-user>'
    fi
}

install_env_file() {
    local src="$1"
    local owner_args=()
    ensure_owner_principals
    if [ -n "${ENV_OWNER}" ]; then
        owner_args=(-o "$(env_owner_user)" -g "$(env_owner_group)")
    fi
    install -m "${ENV_MODE}" "${owner_args[@]}" "${src}" "${ENV_FILE}"
}

ensure_group_exists() {
    local group="$1"
    [ -n "${group}" ] || return
    if getent group "${group}" >/dev/null 2>&1; then
        return
    fi
    if ! command -v groupadd >/dev/null 2>&1; then
        echo "::error::group ${group} missing and groupadd unavailable" >&2
        exit 2
    fi
    echo "::notice::creating system group ${group}" >&2
    groupadd --system "${group}"
}

ensure_read_user_exists() {
    [ -n "${ENV_READ_USER}" ] || return 0
    if id -u "${ENV_READ_USER}" >/dev/null 2>&1; then
        return
    fi
    if ! command -v useradd >/dev/null 2>&1; then
        echo "::error::user ${ENV_READ_USER} missing and useradd unavailable" >&2
        exit 2
    fi

    local primary_group=""
    if [ -n "${ENV_OWNER}" ]; then
        primary_group="$(env_owner_group)"
        ensure_group_exists "${primary_group}"
    fi

    local user_args=(
        --system
        --home "${ENV_READ_USER_HOME}"
        --create-home
        --shell "${ENV_READ_USER_SHELL}"
        --comment "TinyAssets daemon service account"
    )
    if [ -n "${primary_group}" ]; then
        user_args+=(--gid "${primary_group}")
    fi
    echo "::notice::creating system user ${ENV_READ_USER}" >&2
    useradd "${user_args[@]}" "${ENV_READ_USER}"
}

ensure_docker_membership() {
    [ -n "${ENV_READ_USER}" ] || return 0
    id -u "${ENV_READ_USER}" >/dev/null 2>&1 || return 0
    getent group docker >/dev/null 2>&1 || return 0
    if id -nG "${ENV_READ_USER}" | grep -qw docker; then
        return
    fi
    if command -v usermod >/dev/null 2>&1; then
        usermod -aG docker "${ENV_READ_USER}" || true
    fi
}

ensure_owner_principals() {
    if [ -n "${ENV_OWNER}" ]; then
        ensure_group_exists "$(env_owner_group)"
    fi
    ensure_read_user_exists
    ensure_docker_membership
    return 0
}

# Confirm the tinyassets user can actually read the file. This is the
# canary that the systemd unit's ExecStartPre would have tripped on.
assert_readable() {
    if [ -n "${ENV_READ_USER}" ]; then
        if ! sudo -u "${ENV_READ_USER}" test -r "${ENV_FILE}"; then
            echo "::error::ENV-UNREADABLE: ${ENV_FILE} not readable by user ${ENV_READ_USER} after install" >&2
            ls -l "${ENV_FILE}" >&2 || true
            exit 4
        fi
    elif ! test -r "${ENV_FILE}"; then
        echo "::error::ENV-UNREADABLE: ${ENV_FILE} not readable after install" >&2
        ls -l "${ENV_FILE}" >&2 || true
        exit 4
    fi
}

# Read current file content. If the renamed env file is missing on a
# pre-cutover host, bootstrap it from /etc/workflow/env once. If there is
# no legacy file, create an empty env file so the deploy can write the new
# image pin and secrets through the same atomic helper.
ensure_env_file() {
    if [ -f "${ENV_FILE}" ]; then
        return
    fi

    local env_dir
    env_dir="$(dirname "${ENV_FILE}")"
    if ! mkdir -p "${env_dir}"; then
        echo "::error::failed to create ${env_dir}" >&2
        exit 2
    fi
    ensure_owner_principals
    if [ -n "${ENV_OWNER}" ]; then
        chown "$(env_owner_user):$(env_owner_group)" "${env_dir}" || true
        chmod 750 "${env_dir}" || true
    fi

    local src="/dev/null"
    if [ -f "${LEGACY_ENV_FILE}" ]; then
        src="${LEGACY_ENV_FILE}"
        echo "::notice::${ENV_FILE} missing; bootstrapping from ${LEGACY_ENV_FILE}" >&2
    else
        echo "::notice::${ENV_FILE} missing; creating empty env file" >&2
    fi

    if ! install_env_file "${src}"; then
        echo "::error::install(1) failed bootstrapping ${ENV_FILE}" >&2
        exit 3
    fi
    assert_readable
}

# Atomic write of a buffer to ENV_FILE with correct owner + mode.
# install(1) creates the target with the requested mode/owner in one
# step; no intermediate 0600 root:root state is ever observable.
atomic_install() {
    local content="$1"
    if ! printf '%s' "${content}" \
            | install_env_file /dev/stdin; then
        echo "::error::install(1) failed writing ${ENV_FILE}" >&2
        exit 3
    fi
}

cmd_set() {
    local key="$1"
    local immutable="${2-false}"
    validate_key "${key}"
    ensure_env_file

    # Read new value from stdin (verbatim, including any trailing
    # newline the caller piped in — but we strip a single trailing
    # newline so `echo "foo" | ...` produces `KEY=foo` not `KEY=foo\n`
    # appearing as `KEY=foo` followed by a blank entry line).
    local value
    value="$(cat)"
    value="${value%$'\n'}"

    if [ "${immutable}" = "true" ]; then
        if [[ "${value}" == *$'\n'* || "${value}" == *$'\r'* ]]; then
            echo "::error::set-once requires a single-line value for ${key}" >&2
            exit 1
        fi
        local existing=""
        local assignment_count=0
        local line
        while IFS= read -r line || [ -n "${line}" ]; do
            case "${line}" in
                "${key}="*)
                    assignment_count=$((assignment_count + 1))
                    if [ "${assignment_count}" -gt 1 ]; then
                        echo "::error::set-once refused duplicate assignments for ${key}" >&2
                        exit 5
                    fi
                    existing="${line#*=}"
                    ;;
            esac
        done < "${ENV_FILE}"
        if [ -n "${existing}" ]; then
            if [ "${existing}" != "${value}" ]; then
                echo "::error::set-once refused rotation for ${key}; versioned migration required" >&2
                exit 5
            fi
        fi
    fi

    # Build new content: replace the existing KEY= line, or append if absent.
    # Pass the protected value through an inherited pipe on fd 3 rather than
    # awk argv, environment, or a named plaintext file. Awk reconstructs
    # multi-line values to preserve the existing `set` behavior.
    local new_content=""
    local builder_fd
    local builder_status
    coproc CONTENT_BUILDER {
        exec awk -v k="${key}" '
        BEGIN {
            found = 0
            value_seen = 0
            while ((getline value_line < "/dev/fd/3") > 0) {
                v = v (value_seen ? ORS : "") value_line
                value_seen = 1
            }
            close("/dev/fd/3")
        }
        $0 ~ "^" k "=" { print k "=" v; found = 1; next }
        { print }
        END { if (!found) print k "=" v }
        ' "${ENV_FILE}" 3< <(printf '%s' "${value}")
    }
    ACTIVE_BUILDER_PID="${CONTENT_BUILDER_PID}"
    builder_fd="${CONTENT_BUILDER[0]}"
    IFS= read -r -d '' new_content <&"${builder_fd}" || true
    exec {builder_fd}<&-
    while [[ "${new_content}" == *$'\n' ]]; do
        new_content="${new_content%$'\n'}"
    done
    if wait "${ACTIVE_BUILDER_PID}"; then
        builder_status=0
    else
        builder_status=$?
    fi
    ACTIVE_BUILDER_PID=""
    if [ "${builder_status}" -ne 0 ]; then
        echo "::error::failed constructing updated ${ENV_FILE}" >&2
        exit 3
    fi

    atomic_install "${new_content}"$'\n'
    assert_readable
    echo "set ${key} (${ENV_FILE} $(owner_label) ${ENV_MODE})"
}

cmd_delete() {
    local key
    ensure_env_file

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
    echo "deleted: $* (${ENV_FILE} $(owner_label) ${ENV_MODE})"
}

[ $# -ge 1 ] || usage
subcmd="$1"
shift

case "${subcmd}" in
    set)
        [ $# -eq 1 ] || usage
        cmd_set "$1"
        ;;
    set-once)
        [ $# -eq 1 ] || usage
        cmd_set "$1" true
        ;;
    delete)
        [ $# -ge 1 ] || usage
        cmd_delete "$@"
        ;;
    *)
        usage
        ;;
esac
