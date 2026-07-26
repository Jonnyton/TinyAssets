#!/usr/bin/env bash
# Install the complete TinyAssets host-uptime systemd/runtime closure.

set -euo pipefail

SOURCE_ROOT="${TINYASSETS_SOURCE_ROOT:-/opt/tinyassets}"
RUNTIME_ROOT="${TINYASSETS_RUNTIME_ROOT:-/opt/tinyassets-host-uptime}"
SYSTEMD_DIR="${TINYASSETS_SYSTEMD_DIR:-/etc/systemd/system}"
SUDOERS_DIR="${TINYASSETS_SUDOERS_DIR:-/etc/sudoers.d}"
LOCK_DIR="${TINYASSETS_LOCK_DIR:-/run/lock}"
SOURCE_SHA="${TINYASSETS_SOURCE_SHA:-}"
ALLOW_TEST_ROOTS="${TINYASSETS_ALLOW_TEST_ROOTS:-0}"
ACTIVE_WAIT_SECONDS="${TINYASSETS_ACTIVE_WAIT_SECONDS:-180}"
LOCK_WAIT_SECONDS="${TINYASSETS_LOCK_WAIT_SECONDS:-300}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-/usr/bin/systemctl}"
VISUDO_BIN="${VISUDO_BIN:-/usr/sbin/visudo}"
TINYASSETS_USER="${TINYASSETS_USER:-tinyassets}"
PRINT_MANIFEST="${TINYASSETS_PRINT_MANIFEST:-0}"

TIMERS=(
    tinyassets-watchdog.timer
    daemon-watchdog.timer
    tinyassets-backup.timer
    tinyassets-prune.timer
    tinyassets-disk-watch.timer
)
SERVICES=(
    tinyassets-watchdog.service
    daemon-watchdog.service
    tinyassets-backup.service
    tinyassets-prune.service
    tinyassets-disk-watch.service
)
UNIT_FILES=(
    tinyassets-watchdog.service tinyassets-watchdog.timer
    daemon-watchdog.service daemon-watchdog.timer
    tinyassets-backup.service tinyassets-backup.timer
    tinyassets-prune.service tinyassets-prune.timer
    tinyassets-disk-watch.service tinyassets-disk-watch.timer
)
RUNTIME_FILES=(
    deploy/daemon-watchdog.sh
    deploy/backup.sh
    scripts/__init__.py
    scripts/watchdog.py
    scripts/mcp_public_canary.py
    scripts/disk_watch.py
    scripts/disk_autoprune.py
    scripts/rotate_run_transcripts.py
    scripts/backup_ship_gh.py
    scripts/backup_prune.py
    tinyassets/__init__.py
    tinyassets/storage/__init__.py
    tinyassets/storage/rotation.py
)
# Release root plus deploy/, scripts/, tinyassets/, and tinyassets/storage/.
EXPECTED_RELEASE_DIRECTORY_COUNT=5

if [[ "${PRINT_MANIFEST}" == "1" ]]; then
    printf '%s\n' deploy/install-host-uptime-services.sh
    for unit in "${UNIT_FILES[@]}"; do
        printf 'deploy/%s\n' "${unit}"
    done
    printf '%s\n' "${RUNTIME_FILES[@]}"
    exit 0
fi

log() {
    printf '[host-uptime-install] %s\n' "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

for command in \
    awk chmod cmp date find flock grep install ln mktemp mv readlink realpath \
    rm sha256sum sleep stat wc
do
    command -v "${command}" >/dev/null 2>&1 || fail "missing command: ${command}"
done
[[ -x "${SYSTEMCTL_BIN}" ]] || fail "systemctl is not executable: ${SYSTEMCTL_BIN}"
[[ -x "${VISUDO_BIN}" ]] || fail "visudo is not executable: ${VISUDO_BIN}"
[[ "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]] || fail "TINYASSETS_SOURCE_SHA must be a full lowercase commit SHA"
[[ "${ACTIVE_WAIT_SECONDS}" =~ ^[0-9]+$ ]] || fail "TINYASSETS_ACTIVE_WAIT_SECONDS must be a non-negative integer"
[[ "${LOCK_WAIT_SECONDS}" =~ ^[0-9]+$ ]] || fail "TINYASSETS_LOCK_WAIT_SECONDS must be a non-negative integer"

for path in "${SOURCE_ROOT}" "${RUNTIME_ROOT}" "${SYSTEMD_DIR}" "${SUDOERS_DIR}" "${LOCK_DIR}"; do
    [[ "${path}" == /* ]] || fail "all roots must be absolute: ${path}"
done

SOURCE_ROOT="$(realpath -e "${SOURCE_ROOT}")"
RUNTIME_ROOT="$(realpath -m "${RUNTIME_ROOT}")"
SYSTEMD_DIR="$(realpath -m "${SYSTEMD_DIR}")"
SUDOERS_DIR="$(realpath -m "${SUDOERS_DIR}")"
LOCK_DIR="$(realpath -m "${LOCK_DIR}")"

if [[ "${ALLOW_TEST_ROOTS}" != "1" ]]; then
    [[ "${EUID}" -eq 0 ]] || fail "production installation must run as root"
    [[ "${RUNTIME_ROOT}" == "/opt/tinyassets-host-uptime" ]] || fail "unsafe production runtime root"
    [[ "${SYSTEMD_DIR}" == "/etc/systemd/system" ]] || fail "unsafe production systemd root"
    [[ "${SUDOERS_DIR}" == "/etc/sudoers.d" ]] || fail "unsafe production sudoers root"
    [[ "${LOCK_DIR}" == "/run/lock" ]] || fail "unsafe production lock root"
else
    [[ "${SYSTEMCTL_BIN}" != "/usr/bin/systemctl" && "${SYSTEMCTL_BIN}" != "systemctl" ]] \
        || fail "test roots require a non-live systemctl binary"
fi

for unit in "${UNIT_FILES[@]}"; do
    source_file="${SOURCE_ROOT}/deploy/${unit}"
    [[ -f "${source_file}" && ! -L "${source_file}" ]] \
        || fail "missing or unsafe unit source: ${source_file}"
done
for relative in "${RUNTIME_FILES[@]}"; do
    source_file="${SOURCE_ROOT}/${relative}"
    [[ -f "${source_file}" && ! -L "${source_file}" ]] \
        || fail "missing or unsafe runtime source: ${source_file}"
done

mkdir -p "${LOCK_DIR}"
lock_key="$(printf '%s' "${RUNTIME_ROOT}" | sha256sum | awk '{print $1}')"
LOCK_FILE="${LOCK_DIR}/tinyassets-host-uptime-${lock_key}.lock"
exec 9> "${LOCK_FILE}"
flock -w "${LOCK_WAIT_SECONDS}" 9 \
    || fail "timed out waiting for installer lock on ${RUNTIME_ROOT}"

mkdir -p "${RUNTIME_ROOT}/releases" "${SYSTEMD_DIR}" "${SUDOERS_DIR}"
TRANSACTION_DIR="$(mktemp -d "${RUNTIME_ROOT}/.install.XXXXXX")"
UNITS_MUTATED=0
POINTER_SWITCHED=0
RELEASE_BACKED_UP=0
TIMERS_PAUSED=0
SUCCESS=0
PREVIOUS_CURRENT=""
RELEASE_BACKUP=""
SUDOERS_TEMP=""
ABSENT_UNITS="${TRANSACTION_DIR}/absent-units"
mkdir -p "${TRANSACTION_DIR}/units" "${TRANSACTION_DIR}/unit-backup"
: > "${ABSENT_UNITS}"

restore_timers() {
    "${SYSTEMCTL_BIN}" enable --now "${TIMERS[@]}" >/dev/null 2>&1 || true
}

rollback() {
    local unit
    if [[ "${POINTER_SWITCHED}" -eq 1 ]]; then
        if [[ -n "${PREVIOUS_CURRENT}" ]]; then
            ln -s "${PREVIOUS_CURRENT}" "${RUNTIME_ROOT}/.current.rollback.$$"
            mv -Tf "${RUNTIME_ROOT}/.current.rollback.$$" "${RUNTIME_ROOT}/current"
        else
            rm -f "${RUNTIME_ROOT}/current"
        fi
    fi
    if [[ "${UNITS_MUTATED}" -eq 1 ]]; then
        for unit in "${UNIT_FILES[@]}"; do
            if [[ -f "${TRANSACTION_DIR}/unit-backup/${unit}" ]]; then
                install -m 0644 "${TRANSACTION_DIR}/unit-backup/${unit}" \
                    "${SYSTEMD_DIR}/.${unit}.rollback.$$"
                mv -f "${SYSTEMD_DIR}/.${unit}.rollback.$$" "${SYSTEMD_DIR}/${unit}"
            elif grep -qxF "${unit}" "${ABSENT_UNITS}"; then
                rm -f "${SYSTEMD_DIR}/${unit}"
            fi
        done
    fi
    if [[ "${RELEASE_BACKED_UP}" -eq 1 ]]; then
        rm -rf -- "${RELEASE_DIR}"
        mv -- "${RELEASE_BACKUP}" "${RELEASE_DIR}"
    fi
    "${SYSTEMCTL_BIN}" daemon-reload >/dev/null 2>&1 || true
    [[ "${TIMERS_PAUSED}" -eq 0 ]] || restore_timers
}

on_exit() {
    local rc=$?
    local unit
    trap - EXIT
    if [[ "${SUCCESS}" -ne 1 ]]; then
        rollback
    fi
    for unit in "${UNIT_FILES[@]}"; do
        rm -f -- \
            "${SYSTEMD_DIR}/.${unit}.new.$$" \
            "${SYSTEMD_DIR}/.${unit}.rollback.$$"
    done
    rm -f -- \
        "${RUNTIME_ROOT}/.current.new.$$" \
        "${RUNTIME_ROOT}/.current.rollback.$$"
    [[ -z "${SUDOERS_TEMP}" ]] || rm -f -- "${SUDOERS_TEMP}"
    rm -rf -- "${TRANSACTION_DIR}"
    exit "${rc}"
}
trap on_exit EXIT

TIMERS_PAUSED=1
for timer in "${TIMERS[@]}"; do
    load_state="$(
        "${SYSTEMCTL_BIN}" show --property=LoadState --value "${timer}"
    )" || fail "cannot inspect timer load state: ${timer}"
    case "${load_state}" in
        loaded|masked)
            "${SYSTEMCTL_BIN}" stop "${timer}"
            ;;
        not-found)
            ;;
        *)
            fail "unsafe timer load state for ${timer}: ${load_state}"
            ;;
    esac
done
wait_started="$(date +%s)"
while true; do
    active=0
    for service in "${SERVICES[@]}"; do
        active_state="$(
            "${SYSTEMCTL_BIN}" show --property=ActiveState --value "${service}"
        )" || fail "cannot inspect service active state: ${service}"
        case "${active_state}" in
            active|activating|reloading|deactivating)
                active=1
                ;;
            inactive|failed)
                ;;
            *)
                fail "unsafe service active state for ${service}: ${active_state}"
                ;;
        esac
    done
    [[ "${active}" -eq 0 ]] && break
    now="$(date +%s)"
    (( now - wait_started < ACTIVE_WAIT_SECONDS )) \
        || fail "active uptime service did not quiesce within ${ACTIVE_WAIT_SECONDS}s"
    sleep 1
done

manifest_hash="$(
    cd "${SOURCE_ROOT}"
    sha256sum "${RUNTIME_FILES[@]}" | sha256sum | awk '{print $1}'
)"
RELEASE_ID="${SOURCE_SHA}-${manifest_hash:0:16}"
RELEASE_DIR="${RUNTIME_ROOT}/releases/${RELEASE_ID}"
if [[ -d "${RELEASE_DIR}" ]]; then
    release_valid=1
    for relative in "${RUNTIME_FILES[@]}"; do
        mode=644
        [[ "${relative}" == *.sh ]] && mode=755
        installed_file="${RELEASE_DIR}/${relative}"
        if [[ ! -f "${installed_file}" || -L "${installed_file}" ]] \
            || ! cmp -s "${SOURCE_ROOT}/${relative}" "${installed_file}" \
            || [[ "$(stat -c %a "${installed_file}")" != "${mode}" ]]; then
            release_valid=0
            break
        fi
    done
    installed_file_count="$(
        find "${RELEASE_DIR}" -type f -print | wc -l
    )"
    [[ "${installed_file_count}" -eq "${#RUNTIME_FILES[@]}" ]] \
        || release_valid=0
    installed_dir_count="$(
        find "${RELEASE_DIR}" -type d -print | wc -l
    )"
    [[ "${installed_dir_count}" -eq "${EXPECTED_RELEASE_DIRECTORY_COUNT}" ]] \
        || release_valid=0
    if find "${RELEASE_DIR}" ! -type f ! -type d -print -quit | grep -q .; then
        release_valid=0
    fi
    if [[ "${release_valid}" -ne 1 ]]; then
        RELEASE_BACKUP="${TRANSACTION_DIR}/release-backup"
        mv -- "${RELEASE_DIR}" "${RELEASE_BACKUP}"
        RELEASE_BACKED_UP=1
    fi
fi
if [[ ! -d "${RELEASE_DIR}" ]]; then
    RELEASE_STAGE="${TRANSACTION_DIR}/release"
    for relative in "${RUNTIME_FILES[@]}"; do
        mode=0644
        [[ "${relative}" == *.sh ]] && mode=0755
        install -D -m "${mode}" "${SOURCE_ROOT}/${relative}" "${RELEASE_STAGE}/${relative}"
    done
    mv -- "${RELEASE_STAGE}" "${RELEASE_DIR}"
    RELEASE_BACKED_UP=0
fi

for unit in "${UNIT_FILES[@]}"; do
    install -m 0644 "${SOURCE_ROOT}/deploy/${unit}" "${TRANSACTION_DIR}/units/${unit}"
    if [[ -f "${SYSTEMD_DIR}/${unit}" ]]; then
        install -m 0644 "${SYSTEMD_DIR}/${unit}" "${TRANSACTION_DIR}/unit-backup/${unit}"
    else
        printf '%s\n' "${unit}" >> "${ABSENT_UNITS}"
    fi
done

SUDOERS_CANDIDATE="${TRANSACTION_DIR}/tinyassets-watchdog.sudoers"
printf '%s ALL=(root) NOPASSWD:/usr/bin/systemctl restart tinyassets-daemon.service\n' \
    "${TINYASSETS_USER}" > "${SUDOERS_CANDIDATE}"
chmod 0440 "${SUDOERS_CANDIDATE}"
"${VISUDO_BIN}" -cf "${SUDOERS_CANDIDATE}" >/dev/null

for unit in "${UNIT_FILES[@]}"; do
    install -m 0644 "${TRANSACTION_DIR}/units/${unit}" "${SYSTEMD_DIR}/.${unit}.new.$$"
    mv -f "${SYSTEMD_DIR}/.${unit}.new.$$" "${SYSTEMD_DIR}/${unit}"
    UNITS_MUTATED=1
done

SUDOERS_TEMP="$(mktemp "${SUDOERS_DIR}/.tinyassets-watchdog.XXXXXX")"
install -m 0440 "${SUDOERS_CANDIDATE}" "${SUDOERS_TEMP}"
"${VISUDO_BIN}" -cf "${SUDOERS_TEMP}" >/dev/null
mv -f "${SUDOERS_TEMP}" "${SUDOERS_DIR}/tinyassets-watchdog"

if [[ -L "${RUNTIME_ROOT}/current" ]]; then
    PREVIOUS_CURRENT="$(readlink "${RUNTIME_ROOT}/current")"
elif [[ -e "${RUNTIME_ROOT}/current" ]]; then
    fail "runtime current path exists but is not a symlink"
fi
ln -s "releases/${RELEASE_ID}" "${RUNTIME_ROOT}/.current.new.$$"
mv -Tf "${RUNTIME_ROOT}/.current.new.$$" "${RUNTIME_ROOT}/current"
POINTER_SWITCHED=1

"${SYSTEMCTL_BIN}" daemon-reload
"${SYSTEMCTL_BIN}" enable --now "${TIMERS[@]}"
for timer in "${TIMERS[@]}"; do
    "${SYSTEMCTL_BIN}" is-enabled "${timer}" >/dev/null
    "${SYSTEMCTL_BIN}" is-active "${timer}" >/dev/null
done

TIMERS_PAUSED=0
SUCCESS=1
log "converged ${#TIMERS[@]} timers at ${RELEASE_ID}"
