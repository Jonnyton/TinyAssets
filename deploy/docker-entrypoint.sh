#!/usr/bin/env bash
# docker-entrypoint.sh - container startup shim.
#
# 1. Detect silently-empty env_file and emit canonical ENV-UNREADABLE
#    markers to stderr so p0-outage-triage can grep and repair without
#    an SSH shell. Navigator 2026-04-22 section b layer-3.
# 2. Strip every model-provider credential before the control plane starts.
# 3. Fail loud if required static data files are missing from the image.
# 4. Initialize writable vault state as root, preload root-only KEKs, then
#    drop permanently to the tinyassets user in the Python bootstrap.
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

# A control-plane host must not retain any legacy provider-auth home. Scrubbing
# environment variables is insufficient: re-adding CODEX_HOME (or relying on a
# default path under /data) would silently re-arm platform execution. Refuse to
# boot and leave operator-owned credentials untouched for explicit host cleanup.
case "${TINYASSETS_CONTROL_PLANE:-}" in
    1|true|TRUE|yes|YES|on|ON)
        _control_plane_data_dir="${TINYASSETS_DATA_DIR:-/data}"
        _legacy_provider_auth_dirs=(
            "${_control_plane_data_dir}/.codex"
            "${_control_plane_data_dir}/.claude"
        )
        if [[ -n "${CODEX_HOME:-}" ]]; then
            _legacy_provider_auth_dirs+=("${CODEX_HOME}")
        fi
        if [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
            _legacy_provider_auth_dirs+=("${CLAUDE_CONFIG_DIR}")
        fi
        for _auth_dir in "${_legacy_provider_auth_dirs[@]}"; do
            if [[ -d "${_auth_dir}" ]]; then
                echo "CONTROL-PLANE-PROVIDER-AUTH-PRESENT: remove legacy provider auth from ${_auth_dir} before starting the control plane" >&2
                exit 1
            fi
        done
        ;;
esac

# The production service is a control plane, not an executor. Scrub the same
# provider credential manifest consumed by tinyassets.control_plane so shell
# and Python startup cannot drift into two credential lists.
_entrypoint_dir="${BASH_SOURCE[0]%/*}"
_provider_auth_root="${_entrypoint_dir}"
if [[ "${_provider_auth_root##*/}" == "deploy" ]]; then
    _provider_auth_root="${_provider_auth_root%/*}"
fi
_provider_auth_manifest="${_provider_auth_root}/tinyassets/provider_credential_env_vars.txt"
if [[ ! -r "${_provider_auth_manifest}" ]]; then
    echo "CONTROL-PLANE-PROVIDER-MANIFEST-MISSING: ${_provider_auth_manifest}" >&2
    exit 1
fi
while read -r _kind _name _extra || [[ -n "${_kind:-}${_name:-}${_extra:-}" ]]; do
    if [[ -z "${_kind:-}" || "${_kind}" == \#* ]]; then
        continue
    fi
    case "${_kind}" in
        api_key|host_auth|provider_policy) ;;
        *)
            echo "CONTROL-PLANE-PROVIDER-MANIFEST-INVALID: unknown kind ${_kind}" >&2
            exit 1
            ;;
    esac
    if [[ -z "${_name:-}" || -n "${_extra:-}" || "${_name}" == *[!A-Z0-9_]* ]]; then
        echo "CONTROL-PLANE-PROVIDER-MANIFEST-INVALID: malformed environment name" >&2
        exit 1
    fi
    if [[ -n "${!_name:-}" ]]; then
        echo "[entrypoint] ignoring ${_name}: production is control-plane only" >&2
    fi
    unset "${_name}"
done < "${_provider_auth_manifest}"

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
#       credential, never a platform-global provider-auth home.
# Setting it without ALL five re-opens the exact exfiltration vector the gate
# closes. Do not add it here as a convenience.

# The production image intentionally starts this entrypoint as root. Root may
# read the 0400 KEK mount, but the daemon must not. Prepare the persistent
# writable domains here; tinyassets.vault_bootstrap validates/preloads KEKs
# and drops UID/GID before importing daemon code. Non-root execution remains a
# supported packaging/test probe and passes through without privileged setup.
export TINYASSETS_VAULT_ROLLBACK_GUARD="${TINYASSETS_VAULT_ROLLBACK_GUARD:-/vault-guard}"
if [[ "$(id -u)" -eq 0 ]]; then
    mkdir -p "${TINYASSETS_VAULT_ROLLBACK_GUARD}"
    chown -R tinyassets:tinyassets "${TINYASSETS_VAULT_ROLLBACK_GUARD}"
    chown tinyassets:tinyassets "${TINYASSETS_DATA_DIR:-/data}"
fi

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

if [[ "$(id -u)" -eq 0 ]]; then
    exec python -m tinyassets.vault_bootstrap "$@"
fi
exec "$@"
