#!/usr/bin/env bash
# Container startup shim for the non-LLM cloud daemon.

set -euo pipefail

# Fail loudly when compose silently supplied an empty env file.
_env_sentinels=(CLOUDFLARE_TUNNEL_TOKEN SUPABASE_DB_URL TINYASSETS_IMAGE)
_any_set=0
for _name in "${_env_sentinels[@]}"; do
    if [[ -n "${!_name:-}" ]]; then
        _any_set=1
        break
    fi
done
if [[ "${_any_set}" -eq 0 ]]; then
    echo "ENV-UNREADABLE: entrypoint saw no populated secrets; compose env_file likely empty or unreadable" >&2
    echo "ENV-UNREADABLE: expected at least one of ${_env_sentinels[*]} to be set" >&2
    exit 1
fi

# The platform daemon never inherits provider authority. Requester-owned
# credentials are materialized only for one authorized serving invocation.
_ambient_provider_env=(
    OPENAI_API_KEY OPENAI_BASE_URL OPENAI_API_BASE ANTHROPIC_API_KEY
    ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL GEMINI_API_KEY GOOGLE_API_KEY
    GROQ_API_KEY XAI_API_KEY OLLAMA_HOST CODEX_HOME CLAUDE_CONFIG_DIR
    CLAUDE_CODE_OAUTH_TOKEN TINYASSETS_CODEX_AUTH_JSON_B64
    TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64
    TINYASSETS_ALLOW_API_KEY_PROVIDERS
    CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX
    ANTHROPIC_VERTEX_PROJECT_ID ANTHROPIC_VERTEX_REGION CLOUD_ML_REGION
    GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT
    GOOGLE_CLOUD_QUOTA_PROJECT CLOUDSDK_AUTH_ACCESS_TOKEN AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_REGION
    AWS_DEFAULT_REGION AWS_BEARER_TOKEN_BEDROCK
)
for _name in "${_ambient_provider_env[@]}"; do
    if [[ -n "${!_name:-}" ]]; then
        echo "[entrypoint] removing ambient provider authority: ${_name}" >&2
    fi
    unset "${_name}"
done

_tinyassets_bash_path() {
    local _path="${1:-}"
    if [[ "${_path}" =~ ^([A-Za-z]):([\\/].*)$ ]]; then
        if command -v cygpath >/dev/null 2>&1; then
            cygpath -u "${_path}"
        else
            local _drive _prefix _rest
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

_tinyassets_package_root="$(_tinyassets_bash_path "${TINYASSETS_PACKAGE_ROOT:-/app}")"
_required_data_files=(data/world_rules.lp)
for _rel in "${_required_data_files[@]}"; do
    _expected="${_tinyassets_package_root}/${_rel}"
    if [[ ! -f "${_expected}" ]]; then
        echo "DATA-FILE-MISSING: ${_rel} (expected at ${_expected})" >&2
        exit 1
    fi
done

exec "$@"
