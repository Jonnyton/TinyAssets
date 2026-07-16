#!/usr/bin/env bash
# docker-entrypoint.sh - container startup shim.
#
# 1. Detect silently-empty env_file and emit canonical ENV-UNREADABLE
#    markers to stderr so p0-outage-triage can grep and repair without
#    an SSH shell. Navigator 2026-04-22 section b layer-3.
# 2. By default, strip API-key provider environment variables before
#    the daemon starts. API-key providers require an explicit host opt-in.
# 3. Keep subscription-backed Codex auth under CODEX_HOME, defaulting to
#    /data/.codex so the shared tinyassets-data volume preserves rotated
#    OAuth tokens across redeploys. Optionally seed auth.json from
#    TINYASSETS_CODEX_AUTH_JSON_B64 only when missing. Legacy
#    `codex login --with-api-key` from OPENAI_API_KEY is intentionally
#    not run.
# 4. Keep Claude subscription auth under CLAUDE_CONFIG_DIR, defaulting
#    to /data/.claude on the same durable tinyassets-data volume.
# 5. Fail loud if required static data files are missing from the image.
# 6. exec the passed CMD (preserves tini PID-1 signal forwarding).
#
# Placed before CMD so operators can override CMD freely.

set -euo pipefail

# ---------------------------------------------------------------------
# ENV-UNREADABLE canary
# ---------------------------------------------------------------------
# The systemd unit's ExecStartPre catches the dominant failure shape
# (/etc/tinyassets/env not readable by user=tinyassets on the host). This
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
    TINYASSETS_IMAGE
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

if ! _truthy "${TINYASSETS_ALLOW_API_KEY_PROVIDERS:-}"; then
    for _name in "${_api_key_env[@]}"; do
        if [[ -n "${!_name:-}" ]]; then
            echo "[entrypoint] ignoring ${_name}: default daemon auth is subscription-only; set TINYASSETS_ALLOW_API_KEY_PROVIDERS=1 only for an intentional API-key daemon" >&2
            unset "${_name}"
        fi
    done
else
    echo "[entrypoint] API-key providers explicitly enabled by TINYASSETS_ALLOW_API_KEY_PROVIDERS=1" >&2
fi

# ── Coding-node OS-sandbox attestation (patch-loop S3) ───────────────────────
# TINYASSETS_OS_SANDBOX_ATTESTED is DELIBERATELY UNSET here.
#
# Sandbox-required coding nodes (the patch loop's draft_patch etc.) run a coding
# agent with real filesystem/shell tools. tinyassets/providers/base.py
# enforce_os_sandbox() FAILS CLOSED unless this var is truthy — so on this
# container (which does NOT yet provide per-job OS isolation) every coding node
# is refused at run time BY DESIGN. That is the intended state until a host that
# actually confines each job exists; the S6 daemon-setup walkthrough expects
# users to hit this wall. Design-only branches are unaffected.
#
# TINYASSETS_OS_SANDBOX_ATTESTED may ONLY be set by an entrypoint whose per-job
# runner provides ALL of (the deferred production enabler — NOT built yet):
#   (a) a prepared per-job repo checkout (the job's own working tree),
#   (b) tenant/host path invisibility (no /data, no other tenants, no platform
#       source visible to the job),
#   (c) restricted network egress,
#   (d) resource limits (cpu/mem/pids/time), and
#   (e) scoped credential brokering — the job sees ONLY its own owner-scoped
#       credential, never the platform-global CODEX_HOME / CLAUDE_* on /data.
# Setting it without ALL five re-opens the exact exfiltration vector the gate
# closes. Do not add it here as a convenience.

# Codex stores auth in CODEX_HOME/auth.json. In production CODEX_HOME
# defaults to /data/.codex so daemon + worker share one durable auth
# lineage on the tinyassets-data volume. Local/dev containers that do not
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

if [[ -n "${TINYASSETS_CODEX_AUTH_JSON_B64:-}" && ! -f "${CODEX_AUTH_FILE}" ]]; then
    echo "[entrypoint] seeding codex auth.json at ${CODEX_AUTH_FILE} (first boot / volume recovery)"
    CODEX_AUTH_DIR="$(dirname "${CODEX_AUTH_FILE}")"
    CODEX_AUTH_TMP="$(mktemp "${CODEX_AUTH_DIR}/auth.json.XXXXXX")"
    if printf '%s' "${TINYASSETS_CODEX_AUTH_JSON_B64}" | base64 -d > "${CODEX_AUTH_TMP}"; then
        chmod 600 "${CODEX_AUTH_TMP}"
        mv "${CODEX_AUTH_TMP}" "${CODEX_AUTH_FILE}"
    else
        rm -f "${CODEX_AUTH_TMP}"
        echo "[entrypoint] failed to decode TINYASSETS_CODEX_AUTH_JSON_B64" >&2
        exit 1
    fi
elif [[ -f "${CODEX_AUTH_FILE}" ]]; then
    echo "[entrypoint] preserving existing codex auth.json at ${CODEX_AUTH_FILE} (in-place refresh chain)"
fi
unset TINYASSETS_CODEX_AUTH_JSON_B64

# Claude Code honors CLAUDE_CONFIG_DIR directly. Production defaults to the
# shared /data volume so daemon + worker preserve one subscription login state
# across image redeploys, matching the Codex /data/.codex pattern.
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/data/.claude}"
CLAUDE_CREDENTIALS_FILE="${CLAUDE_CONFIG_DIR}/.credentials.json"
mkdir -p "${CLAUDE_CONFIG_DIR}"
chmod 700 "${CLAUDE_CONFIG_DIR}" 2>/dev/null || true

# Seed Claude auth so a FRESH /data volume is not left "Not logged in" —
# which fails every pinned claude-code writer call (the 2026-06-25 loop-wedge
# incident: missing creds silently took out half the worker fleet). Mirrors
# the Codex auth.json block above. Two sources, both first-boot-only so a
# rotated in-place token is never clobbered:
#   * CLAUDE_CODE_OAUTH_TOKEN — a `claude setup-token` long-lived token that
#     Claude Code reads straight from the env (no file needed). Preferred: it
#     sidesteps shared-refresh-token rotation between machines.
#   * TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64 — base64 of a subscription
#     ~/.claude/.credentials.json bundle, decoded to the config dir (the direct
#     Codex-style mirror for hosts that seed a credentials file).
if [[ -n "${TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64:-}" && ! -f "${CLAUDE_CREDENTIALS_FILE}" ]]; then
    echo "[entrypoint] seeding claude credentials at ${CLAUDE_CREDENTIALS_FILE} (first boot / volume recovery)"
    CLAUDE_CRED_TMP="$(mktemp "${CLAUDE_CONFIG_DIR}/.credentials.json.XXXXXX")"
    if printf '%s' "${TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64}" | base64 -d > "${CLAUDE_CRED_TMP}"; then
        chmod 600 "${CLAUDE_CRED_TMP}"
        mv "${CLAUDE_CRED_TMP}" "${CLAUDE_CREDENTIALS_FILE}"
    else
        rm -f "${CLAUDE_CRED_TMP}"
        echo "[entrypoint] failed to decode TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64" >&2
        exit 1
    fi
elif [[ -f "${CLAUDE_CREDENTIALS_FILE}" ]]; then
    echo "[entrypoint] preserving existing claude credentials at ${CLAUDE_CREDENTIALS_FILE} (in-place refresh chain)"
elif [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then
    echo "[entrypoint] using CLAUDE_CODE_OAUTH_TOKEN from env for claude-code auth (no credentials file needed)"
else
    echo "[entrypoint] WARNING: no claude credentials present and neither TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64 nor CLAUDE_CODE_OAUTH_TOKEN is set — claude-code writer will be unauthenticated (codex-only fleet OK; pinned claude workers will fail)" >&2
fi
unset TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64

_tinyassets_bash_path() {
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

_tinyassets_package_root="$(_tinyassets_bash_path "${TINYASSETS_PACKAGE_ROOT:-/app}")"
_required_data_files=(
    data/world_rules.lp
)

for _rel in "${_required_data_files[@]}"; do
    _expected="${_tinyassets_package_root}/${_rel}"
    if [[ ! -f "${_expected}" ]]; then
        echo "DATA-FILE-MISSING: ${_rel} (expected at ${_expected})" >&2
        exit 1
    fi
done

exec "$@"
