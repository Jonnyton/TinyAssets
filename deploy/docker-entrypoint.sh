#!/usr/bin/env bash
# docker-entrypoint.sh - container startup shim.
#
# 1. Detect silently-empty env_file and emit canonical ENV-UNREADABLE
#    markers to stderr so p0-outage-triage can grep and repair without
#    an SSH shell. Navigator 2026-04-22 section b layer-3.
# 2. By default, strip API-key provider environment variables before
#    the daemon starts. API-key providers require an explicit host opt-in.
# 3. Keep subscription-backed Codex auth under CODEX_HOME, defaulting to
#    /data/.codex so the shared workflow-data volume preserves rotated
#    OAuth tokens across redeploys. Optionally seed auth.json from
#    WORKFLOW_CODEX_AUTH_JSON_B64 only when missing. Legacy
#    `codex login --with-api-key` from OPENAI_API_KEY is intentionally
#    not run.
# 4. Keep Claude subscription auth under CLAUDE_CONFIG_DIR, defaulting
#    to /data/.claude on the same durable workflow-data volume.
# 5. Fail loud if required static data files are missing from the image.
# 6. exec the passed CMD (preserves tini PID-1 signal forwarding).
#
# Placed before CMD so operators can override CMD freely.

set -euo pipefail

# ---------------------------------------------------------------------
# ENV-UNREADABLE canary
# ---------------------------------------------------------------------
# The systemd unit's ExecStartPre catches the dominant failure shape
# (/etc/workflow/env not readable by user=workflow on the host). This
# entrypoint-level check catches an adjacent subclass: compose read the
# env_file, but the file was empty or stripped, so the container boots
# with no real env, silently broken.
#
# Heuristic: at least one of the required secrets must be non-empty. An
# all-empty env indicates compose silently passed an empty file. The
# ENV-UNREADABLE marker keeps the grep class the same regardless of
# which layer detected the problem.
_env_sentinels=(
    CLOUDFLARE_TUNNEL_TOKEN
    SUPABASE_DB_URL
    WORKFLOW_IMAGE
)
_any_set=0
for _name in "${_env_sentinels[@]}"; do
    if [[ -n "${!_name:-}" ]]; then
        _any_set=1
        break
    fi
done
if [[ "${_any_set}" -eq 0 ]]; then
    # All sentinel env vars empty. compose env_file silently empty/unreadable.
    echo "ENV-UNREADABLE: entrypoint saw no populated secrets; compose env_file likely empty or unreadable" >&2
    echo "ENV-UNREADABLE: expected at least one of ${_env_sentinels[*]} to be set" >&2
    exit 1
fi

_truthy() {
    case "${1:-}" in
        1|true|TRUE|True|yes|YES|Yes|on|ON|On) return 0 ;;
        *) return 1 ;;
    esac
}

_api_key_env=(
    OPENAI_API_KEY
    ANTHROPIC_API_KEY
    ANTHROPIC_BASE_URL
    GEMINI_API_KEY
    GROQ_API_KEY
    XAI_API_KEY
)

if ! _truthy "${WORKFLOW_ALLOW_API_KEY_PROVIDERS:-}"; then
    for _name in "${_api_key_env[@]}"; do
        if [[ -n "${!_name:-}" ]]; then
            echo "[entrypoint] ignoring ${_name}: default daemon auth is subscription-only; set WORKFLOW_ALLOW_API_KEY_PROVIDERS=1 only for an intentional API-key daemon" >&2
            unset "${_name}"
        fi
    done
else
    echo "[entrypoint] API-key providers explicitly enabled by WORKFLOW_ALLOW_API_KEY_PROVIDERS=1" >&2
fi

# Codex stores auth in CODEX_HOME/auth.json. In production CODEX_HOME
# defaults to /data/.codex so daemon + worker share one durable auth
# lineage on the workflow-data volume. Local/dev containers that do not
# set CODEX_HOME still get the same durable default when /data is mounted.
#
# Codex CLI uses OAuth single-use refresh tokens — it rotates them
# in-container during normal operation, writing the new token back to
# auth.json. Overwriting that file on every container start throws away
# rotated tokens, so the next refresh attempt sends a token that's
# already been used -> `refresh_token_reused` error -> codex calls die.
#
# Fix per OpenAI's official Codex CI/CD auth guide
# (https://developers.openai.com/codex/auth/ci-cd-auth): seed auth.json
# only when missing, and persist it across container restarts via a
# volume mount on the parent directory. deploy/compose.yml sets
# CODEX_HOME=/data/.codex for both daemon and worker, so the in-place
# refresh chain survives image redeploys and restarts.
#
# Three branches:
#   1. env set, file missing  -> seed (first boot / volume recovery)
#   2. env set, file present  -> preserve (in-place refresh chain alive)
#   3. env unset, file present -> preserve (volume-only operation)
export CODEX_HOME="${CODEX_HOME:-/data/.codex}"
CODEX_AUTH_FILE="${CODEX_HOME}/auth.json"
CODEX_CONFIG_FILE="${CODEX_HOME}/config.toml"
mkdir -p "${CODEX_HOME}"
chmod 700 "${CODEX_HOME}"

# Containers do not have an OS keyring. Force Codex to use file-backed
# credential storage so auth.json on CODEX_HOME is authoritative.
if ! grep -qs '^cli_auth_credentials_store' "${CODEX_CONFIG_FILE}" 2>/dev/null; then
    printf '%s\n' 'cli_auth_credentials_store = "file"' >> "${CODEX_CONFIG_FILE}"
fi

if [[ -n "${WORKFLOW_CODEX_AUTH_JSON_B64:-}" && ! -f "${CODEX_AUTH_FILE}" ]]; then
    echo "[entrypoint] seeding codex auth.json at ${CODEX_AUTH_FILE} (first boot / volume recovery)"
    CODEX_AUTH_DIR="$(dirname "${CODEX_AUTH_FILE}")"
    CODEX_AUTH_TMP="$(mktemp "${CODEX_AUTH_DIR}/auth.json.XXXXXX")"
    if printf '%s' "${WORKFLOW_CODEX_AUTH_JSON_B64}" | base64 -d > "${CODEX_AUTH_TMP}"; then
        chmod 600 "${CODEX_AUTH_TMP}"
        mv "${CODEX_AUTH_TMP}" "${CODEX_AUTH_FILE}"
    else
        rm -f "${CODEX_AUTH_TMP}"
        echo "[entrypoint] failed to decode WORKFLOW_CODEX_AUTH_JSON_B64" >&2
        exit 1
    fi
elif [[ -f "${CODEX_AUTH_FILE}" ]]; then
    echo "[entrypoint] preserving existing codex auth.json at ${CODEX_AUTH_FILE} (in-place refresh chain)"
fi
unset WORKFLOW_CODEX_AUTH_JSON_B64

# Claude Code honors CLAUDE_CONFIG_DIR directly. Production defaults to the
# shared /data volume so daemon + worker preserve one subscription login state
# across image redeploys, matching the Codex /data/.codex pattern.
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/data/.claude}"
mkdir -p "${CLAUDE_CONFIG_DIR}"
chmod 700 "${CLAUDE_CONFIG_DIR}" 2>/dev/null || true
if [[ -d "${CLAUDE_CONFIG_DIR}" ]]; then
    echo "[entrypoint] preserving Claude subscription auth config at ${CLAUDE_CONFIG_DIR}"
fi

_workflow_bash_path() {
    local _path="${1:-}"
    if [[ "${_path}" =~ ^([A-Za-z]):([\\/].*)$ ]]; then
        if command -v cygpath >/dev/null 2>&1; then
            cygpath -u "${_path}"
        else
            local _drive
            local _prefix
            local _rest
            _drive="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')"
            _rest="${BASH_REMATCH[2]//\\//}"
            _rest="${_rest#/}"
            _prefix="/${_drive}"
            if [[ -d "/mnt/${_drive}" ]]; then
                _prefix="/mnt/${_drive}"
            fi
            printf '%s/%s\n' "${_prefix}" "${_rest}"
        fi
    else
        printf '%s\n' "${_path}"
    fi
}

_workflow_package_root="$(_workflow_bash_path "${WORKFLOW_PACKAGE_ROOT:-/app}")"
_required_data_files=(
    data/world_rules.lp
)

for _rel in "${_required_data_files[@]}"; do
    _expected="${_workflow_package_root}/${_rel}"
    if [[ ! -f "${_expected}" ]]; then
        echo "DATA-FILE-MISSING: ${_rel} (expected at ${_expected})" >&2
        exit 1
    fi
done

exec "$@"
