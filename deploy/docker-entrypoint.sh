#!/usr/bin/env bash
# docker-entrypoint.sh - container startup shim.
#
# 1. Detect silently-empty env_file and emit canonical ENV-UNREADABLE
#    markers to stderr so p0-outage-triage can grep and repair without
#    an SSH shell. Navigator 2026-04-22 section b layer-3.
# 2. By default, strip API-key provider environment variables before
#    the daemon starts. API-key providers require an explicit host opt-in.
# 3. Optionally install a subscription-backed Codex auth bundle from
#    WORKFLOW_CODEX_AUTH_JSON_B64. Legacy `codex login --with-api-key`
#    from OPENAI_API_KEY is intentionally not run.
# 4. Fail loud if required static data files are missing from the image.
# 5. exec the passed CMD (preserves tini PID-1 signal forwarding).
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

# Codex stores auth in ~/.codex/auth.json relative to the running user.
CODEX_AUTH_FILE="${HOME:-/app}/.codex/auth.json"

if [[ -n "${WORKFLOW_CODEX_AUTH_JSON_B64:-}" ]]; then
    echo "[entrypoint] installing codex subscription auth bundle"
    CODEX_AUTH_DIR="$(dirname "${CODEX_AUTH_FILE}")"
    mkdir -p "${CODEX_AUTH_DIR}"
    CODEX_AUTH_TMP="$(mktemp "${CODEX_AUTH_DIR}/auth.json.XXXXXX")"
    if printf '%s' "${WORKFLOW_CODEX_AUTH_JSON_B64}" | base64 -d > "${CODEX_AUTH_TMP}"; then
        chmod 600 "${CODEX_AUTH_TMP}"
        mv "${CODEX_AUTH_TMP}" "${CODEX_AUTH_FILE}"
    else
        rm -f "${CODEX_AUTH_TMP}"
        echo "[entrypoint] failed to decode WORKFLOW_CODEX_AUTH_JSON_B64" >&2
        exit 1
    fi
    unset WORKFLOW_CODEX_AUTH_JSON_B64
fi

_workflow_bash_path() {
    local _path="${1:-}"
    if [[ "${_path}" =~ ^[A-Za-z]:[\\/].* ]] && command -v cygpath >/dev/null 2>&1; then
        cygpath -u "${_path}"
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
