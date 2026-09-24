#!/usr/bin/env bash
# retire_platform_llm_logins.sh - remove the platform's own model credentials
# and GitHub push credential from the production host. Idempotent; run by
# deploy-prod.yml ONLY after the new image's public canary is green.
#
# The platform has no LLM (AGENTS.md Hard Rule 15). Before 2026-09-24 the
# daemon container carried host-level Codex and Claude CLI logins on the data
# volume plus model API keys in the host env file, kept alive by two weekly
# keepalive workflows. The image and compose file no longer read any of it
# (deploy/docker-entrypoint.sh strips the names unconditionally); this script
# removes what is still lying on the host:
#
#   1. scrubs the retired variables from /etc/tinyassets/env through the
#      atomic helper (deploy/install-tinyassets-env.sh `delete`);
#   2. deletes the credential file inside each platform login directory
#      (`.codex/auth.json`, `.claude/.credentials.json`);
#   3. deletes both platform login directories IN FULL, transcripts included
#      (`sessions/`, `projects/`, the CLI state databases, `.claude.json` and its
#      backups). Founder decision 2026-09-24, taken after the read-only Hard
#      Rule 13 inventory: delete rather than archive. Guards, all required:
#        - targets are built ONLY from the two constant labels `.codex` and
#          `.claude`;
#        - the volume: `realpath -e` of the `tinyassets-data` mountpoint equals
#          the mountpoint itself, AND `docker inspect` shows that same volume
#          mounted at `/data` in the daemon;
#        - each target: `[ ! -L ]`, then `realpath -e "$vol/$label"` equals
#          exactly `$vol_real/$label`. Universes live beside them at the volume
#          root as `u-*`; the exact-path match is what keeps them out;
#        - immediately before the `rm`, no symlink under a universe resolves
#          into the target and no universe config names it;
#        - `rm -rf --one-file-system -- "$real"`: never crosses into another
#          mount, and a symlink inside a target is removed as a link, never
#          followed.
#      A failed guard leaves the target untouched and the script exits 1.
#      Transcripts are logged as COUNTS only, never names or contents;
#   4. retires the platform GitHub push path: the push-capability maps in the
#      env file (step 1), the GitHub App token refresher's systemd timer and
#      service, its script copy, its env file, and the App private key at its
#      documented path. A key configured at any OTHER path is not deleted; it
#      is named and left for the founder.
#
# It logs variable/unit NAMES and file COUNTS only, never a value, a
# transcript name or any file content.
#
# Precondition: the running daemon must already be the new release -- its
# container config must not define CODEX_HOME or CLAUDE_CONFIG_DIR. If it does,
# the old compose file is still live and nothing is touched (exit 1, loud).
#
# Usage (root): retire_platform_llm_logins.sh <path-to-install-tinyassets-env.sh>
# Exit: 0 done (including "nothing to do"); 1 precondition or verification
# failure; 2 bad invocation.

set -euo pipefail

ENV_HELPER="${1:-}"
ENV_FILE="${TINYASSETS_ENV_FILE:-/etc/tinyassets/env}"
DAEMON="${TINYASSETS_DAEMON_CONTAINER:-tinyassets-daemon}"
VOLUME="${TINYASSETS_DATA_VOLUME:-tinyassets-data}"
ETC_DIR="${TINYASSETS_ETC_DIR:-/etc/tinyassets}"
OPT_DIR="${TINYASSETS_OPT_DIR:-/opt/tinyassets}"
SYSTEMD_DIR="${TINYASSETS_SYSTEMD_DIR:-/etc/systemd/system}"

if [ -z "${ENV_HELPER}" ] || [ ! -f "${ENV_HELPER}" ]; then
    echo "usage: retire_platform_llm_logins.sh <install-tinyassets-env.sh>" >&2
    exit 2
fi

# Every host-env name through which the platform held, seeded or enabled a
# model credential or a GitHub push credential.
# tests/test_no_platform_llm_credentials.py and
# tests/test_no_platform_github_push_credential.py require this list to cover
# all of them.
RETIRED_ENV=(
    CODEX_HOME
    CLAUDE_CONFIG_DIR
    CLAUDE_CODE_OAUTH_TOKEN
    OPENAI_API_KEY
    ANTHROPIC_API_KEY
    ANTHROPIC_BASE_URL
    GEMINI_API_KEY
    GOOGLE_API_KEY
    GROQ_API_KEY
    XAI_API_KEY
    TINYASSETS_ALLOW_API_KEY_PROVIDERS
    TINYASSETS_CODEX_AUTH_JSON_B64
    TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64
    TINYASSETS_GITHUB_PUSH_CAPABILITIES
    TINYASSETS_GITHUB_PR_CAPABILITIES
)

# ---------------------------------------------------------------------------
# 0. precondition: the new release is the one running
# ---------------------------------------------------------------------------
running_env_names="$(docker inspect "${DAEMON}" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1)" || {
    echo "::error::retire-platform-llm-logins: cannot inspect ${DAEMON}; nothing touched" >&2
    exit 1
}
for name in CODEX_HOME CLAUDE_CONFIG_DIR; do
    if printf '%s\n' "${running_env_names}" | grep -qx "${name}"; then
        echo "::error::retire-platform-llm-logins: ${DAEMON} still defines ${name}; the retired compose file is live, so nothing was touched" >&2
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# 1. host env file
# ---------------------------------------------------------------------------
if [ ! -r "${ENV_FILE}" ]; then
    echo "::error::retire-platform-llm-logins: ${ENV_FILE} unreadable; nothing touched" >&2
    exit 1
fi
present=()
for name in "${RETIRED_ENV[@]}"; do
    # assert-absent exits non-zero when a Compose-recognized assignment exists
    # (the file is readable, checked above).
    if ! TINYASSETS_ENV_FILE="${ENV_FILE}" bash "${ENV_HELPER}" assert-absent "${name}" >/dev/null 2>&1; then
        present+=("${name}")
    fi
done
if [ "${#present[@]}" -gt 0 ]; then
    TINYASSETS_ENV_FILE="${ENV_FILE}" bash "${ENV_HELPER}" delete "${present[@]}" >/dev/null
    for name in "${present[@]}"; do
        if ! TINYASSETS_ENV_FILE="${ENV_FILE}" bash "${ENV_HELPER}" assert-absent "${name}" >/dev/null 2>&1; then
            echo "::error::retire-platform-llm-logins: ${name} is still assigned in ${ENV_FILE} after delete" >&2
            exit 1
        fi
    done
    echo "retire-platform-llm-logins: removed from ${ENV_FILE}: ${present[*]}"
    echo "retire-platform-llm-logins: the running container keeps these names in its config until its next recreate; its process never saw them (entrypoint strip)"
else
    echo "retire-platform-llm-logins: ${ENV_FILE} holds none of the retired names"
fi

# ---------------------------------------------------------------------------
# 4. the GitHub App token refresher (platform push credential)
# ---------------------------------------------------------------------------
refresher_env="${ETC_DIR}/github-app-token-refresher.env"
documented_key="${ETC_DIR}/github-app-private-key.pem"
held_github=0
if [ -f "${refresher_env}" ]; then
    # App and installation ids are public identifiers, not secrets; they are
    # what the founder needs to uninstall or delete the App in GitHub.
    for id_name in GITHUB_APP_ID GITHUB_APP_INSTALLATION_ID; do
        id_value="$(grep -E "^${id_name}=" "${refresher_env}" | head -1 | cut -d= -f2- | tr -cd '0-9' || true)"
        if [ -n "${id_value}" ]; then
            echo "retire-platform-llm-logins: refresher config ${id_name}=${id_value}"
        fi
    done
    configured_key="$(grep -E '^GITHUB_APP_PRIVATE_KEY_FILE=' "${refresher_env}" | head -1 | cut -d= -f2- || true)"
    if [ -n "${configured_key}" ] && [ "${configured_key}" != "${documented_key}" ]; then
        held_github=1
        echo "::warning::retire-platform-llm-logins: the refresher points at a private key outside ${documented_key}; not deleted, left for the founder (path: ${configured_key})"
    fi
fi
if command -v systemctl >/dev/null 2>&1; then
    for unit in github-app-token-refresher.timer github-app-token-refresher.service; do
        if [ -e "${SYSTEMD_DIR}/${unit}" ]; then
            systemctl disable --now "${unit}" >/dev/null 2>&1 || true
        fi
    done
fi
removed_github=()
for path in \
    "${SYSTEMD_DIR}/github-app-token-refresher.timer" \
    "${SYSTEMD_DIR}/github-app-token-refresher.service" \
    "${OPT_DIR}/scripts/github-app-token-refresher.py" \
    "${refresher_env}" \
    "${documented_key}"; do
    if [ -e "${path}" ] || [ -L "${path}" ]; then
        rm -f -- "${path}"
        removed_github+=("${path}")
    fi
done
if [ "${#removed_github[@]}" -gt 0 ]; then
    command -v systemctl >/dev/null 2>&1 && systemctl daemon-reload || true
    echo "retire-platform-llm-logins: removed GitHub push refresher files: ${removed_github[*]}"
else
    echo "retire-platform-llm-logins: no GitHub push refresher files present"
fi

# ---------------------------------------------------------------------------
# 2 + 3. platform login directories on the data volume
# ---------------------------------------------------------------------------
vol="$(docker volume inspect "${VOLUME}" --format '{{ .Mountpoint }}' 2>/dev/null || true)"
if [ -z "${vol}" ] || [ "${vol#/}" = "${vol}" ] || [ ! -d "${vol}" ]; then
    echo "retire-platform-llm-logins: volume ${VOLUME} not found; no login directories to retire"
    echo "retire_platform_llm_logins_result=$([ "${held_github}" -eq 0 ] && echo complete || echo github_key_held)"
    exit 0
fi

# Volume guard 1: the mountpoint is its own real path (no link in the way).
vol_real="$(realpath -e -- "${vol}" 2>/dev/null || true)"
if [ -z "${vol_real}" ] || [ "${vol_real}" != "${vol}" ] || [ "${vol_real}" = "/" ]; then
    echo "::error::retire-platform-llm-logins: ${VOLUME} mountpoint does not resolve to itself; login directories not touched" >&2
    echo "retire_platform_llm_logins_result=refused"
    exit 1
fi
# Volume guard 2: the daemon mounts exactly this volume at /data.
data_mount="$(docker inspect "${DAEMON}" \
    --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Type}}|{{.Name}}|{{.Source}}{{end}}{{end}}' 2>/dev/null || true)"
if [ "${data_mount}" != "volume|${VOLUME}|${vol_real}" ]; then
    echo "::error::retire-platform-llm-logins: ${DAEMON} does not mount ${VOLUME} at /data; login directories not touched" >&2
    echo "retire_platform_llm_logins_result=refused"
    exit 1
fi

# How many universe symlinks resolve into $1, plus universe configs naming it.
# Universes live at the volume root as u-*.
universe_references() {
    local real="$1" label="$2" count=0 link resolved
    local universes=()
    local u
    for u in "${vol_real}"/u-*; do
        [ -d "${u}" ] && [ ! -L "${u}" ] && universes+=("${u}")
    done
    [ "${#universes[@]}" -gt 0 ] || { echo 0; return; }
    while IFS= read -r -d '' link; do
        resolved="$(readlink -f -- "${link}" 2>/dev/null || true)"
        case "${resolved}" in
            "${real}"|"${real}"/*) count=$((count + 1)) ;;
        esac
    done < <(find "${universes[@]}" -type l \( -lname "*${label}" -o -lname "*${label}/*" \) -print0 2>/dev/null)
    local configs
    configs="$(grep -rlsF --include='*.json' --include='*.toml' --include='*.yaml' --include='*.yml' \
        -e "/data/${label}" -e "${real}" "${universes[@]}" 2>/dev/null | wc -l | tr -d ' ')"
    echo $((count + configs))
}

refused=0
retire_dir() {
    local label="$1" credential="$2"
    case "${label}" in
        .codex|.claude) ;;
        *) echo "::error::retire-platform-llm-logins: unexpected label; refused" >&2; refused=1; return ;;
    esac
    local target="${vol_real}/${label}"

    if [ ! -e "${target}" ] && [ ! -L "${target}" ]; then
        echo "retire-platform-llm-logins: ${label} absent"
        return
    fi
    if [ -L "${target}" ]; then
        refused=1
        echo "::error::retire-platform-llm-logins: ${label} is a symlink; refused, not touched" >&2
        return
    fi
    local real
    real="$(realpath -e -- "${vol}/${label}" 2>/dev/null || true)"
    if [ "${real}" != "${vol_real}/${label}" ] || [ ! -d "${real}" ]; then
        refused=1
        echo "::error::retire-platform-llm-logins: ${label} does not resolve to exactly ${vol_real}/${label}; refused, not touched" >&2
        return
    fi

    local refs
    refs="$(universe_references "${real}" "${label}")"
    if [ "${refs}" != "0" ]; then
        refused=1
        echo "::error::retire-platform-llm-logins: ${refs} universe symlink(s)/config(s) point at ${label}; refused, not deleted" >&2
        return
    fi

    if [ -f "${real}/${credential}" ] && [ ! -L "${real}/${credential}" ]; then
        rm -f -- "${real}/${credential}"
        echo "retire-platform-llm-logins: removed credential ${label}/${credential}"
    fi

    local files dirs
    files="$(find "${real}" -xdev \( -type f -o -type l \) | wc -l | tr -d ' ')"
    dirs="$(find "${real}" -xdev -mindepth 1 -type d | wc -l | tr -d ' ')"
    rm -rf --one-file-system -- "${real}"
    if [ -e "${real}" ]; then
        refused=1
        echo "::error::retire-platform-llm-logins: ${label} still present after removal (another mount inside it?)" >&2
        return
    fi
    echo "retire-platform-llm-logins: removed ${label} in full (${files} files, ${dirs} directories)"
}

retire_dir ".codex" "auth.json"
retire_dir ".claude" ".credentials.json"

if [ "${refused}" -ne 0 ]; then
    echo "retire_platform_llm_logins_result=refused"
    exit 1
fi
echo "retire_platform_llm_logins_result=$([ "${held_github}" -eq 0 ] && echo complete || echo github_key_held)"
