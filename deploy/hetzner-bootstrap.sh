#!/usr/bin/env bash
# hetzner-bootstrap.sh — idempotent provisioning for a fresh Debian 12 Linux VM.
#
# Provider-neutral despite the file name (name kept for git history).
# Verified on: Hetzner Cloud CX22, DigitalOcean Basic Droplet, Linode 1 GB,
# Vultr Cloud Compute. Any Debian 12 VM with root SSH + outbound-internet
# works. Bootstrap is idempotent; provider-specific install-time dashboards
# (Hetzner Cloud Console vs DO Droplets UI vs etc.) do not change the
# script's execution.
#
# Current production target (2026-04-20): DigitalOcean Basic Droplet.
# Pivoted from Hetzner mid-cutover due to a Hetzner US individual-signup
# form bug; Hetzner remains the documented fallback per exec plan §2.
#
# Self-host migration Row D per
# docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md.
#
# Idempotent: safe to re-run. Skips steps whose end-state is already
# reached. No destructive actions; existing /opt/tinyassets or
# /etc/tinyassets content is preserved.
#
# Usage (on the target box, as root):
#   curl -fsSL https://raw.githubusercontent.com/Jonnyton/TinyAssets/main/deploy/hetzner-bootstrap.sh -o /tmp/bootstrap.sh
#   sudo bash /tmp/bootstrap.sh
#
# OR (local-clone):
#   sudo bash deploy/hetzner-bootstrap.sh
#
# Post-bootstrap host action:
#   1. Fill /etc/tinyassets/env with real secrets (CLOUDFLARE_TUNNEL_TOKEN,
#      SUPABASE_*, GITHUB_OAUTH_*).
#   2. systemctl start tinyassets-daemon
#   3. Verify: python3 /opt/tinyassets/scripts/mcp_public_canary.py
#      --url https://tinyassets.io/mcp --verbose

set -euo pipefail

# Must run as root.
if [[ "${EUID}" -ne 0 ]]; then
    echo "bootstrap: must run as root (try: sudo bash $0)" >&2
    exit 1
fi

TINYASSETS_USER="tinyassets"
TINYASSETS_UID=1001
TINYASSETS_HOME="/opt/tinyassets"
ENV_DIR="/etc/tinyassets"
REPO_URL="https://github.com/Jonnyton/TinyAssets.git"
REPO_REF="main"

log() { echo "[bootstrap] $*"; }

# ----- 1. apt baseline ----------------------------------------------------

# Fresh DO/Hetzner/Linode Droplets run cloud-init + unattended-upgrades
# at first boot. Racing them produces
#   "Could not get lock /var/lib/apt/lists/lock. It is held by process N"
# and the bootstrap exits 100. Wait for both to release before we touch apt.
if command -v cloud-init >/dev/null 2>&1; then
    log "waiting for cloud-init to finish..."
    cloud-init status --wait >/dev/null 2>&1 || true
fi
log "waiting for apt/dpkg locks to clear..."
for i in $(seq 1 180); do
    if ! pgrep -x apt-get >/dev/null 2>&1 \
         && ! pgrep -x dpkg >/dev/null 2>&1 \
         && ! pgrep -x unattended-upgr >/dev/null 2>&1; then
        break
    fi
    if [[ "${i}" -eq 180 ]]; then
        log "WARN: apt/dpkg still running after 180s — proceeding anyway"
    fi
    sleep 1
done

log "apt update + base packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    ca-certificates \
    curl \
    git \
    gnupg \
    python3 \
    python3-pip \
    jq \
    rclone \
    zstd

# ----- 2. Docker CE + compose plugin --------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    log "installing Docker CE..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
    cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian ${codename} stable
EOF
    apt-get update -qq
    apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    log "Docker installed: $(docker --version)"
else
    log "Docker already installed: $(docker --version)"
fi

# ----- 2b. Docker log-rotation --------------------------------------------

# Without log-rotation docker containers write unbounded JSON logs to
# /var/lib/docker/containers/*/. On a 960 MB / 25 GB droplet this fills
# disk within days of normal daemon activity. Matches live prod config
# applied 2026-04-21.
DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
DOCKER_LOG_CONFIG='{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}'
if [[ ! -f "${DOCKER_DAEMON_JSON}" ]] || \
   ! python3 -c "
import json, sys
d = json.load(open('${DOCKER_DAEMON_JSON}'))
lo = d.get('log-opts', {})
assert d.get('log-driver') == 'json-file'
assert lo.get('max-size') == '10m'
assert lo.get('max-file') == '3'
" 2>/dev/null; then
    log "writing ${DOCKER_DAEMON_JSON} (log-rotation: 10m × 3)..."
    echo "${DOCKER_LOG_CONFIG}" > "${DOCKER_DAEMON_JSON}"
    # Reload Docker to pick up the new log config. Skip if daemon not yet
    # running (first-boot before `systemctl enable --now docker` above).
    if systemctl is-active --quiet docker; then
        systemctl reload-or-restart docker
    fi
else
    log "${DOCKER_DAEMON_JSON} already configured correctly"
fi

# ----- 3. tinyassets user ---------------------------------------------------

if ! id -u "${TINYASSETS_USER}" >/dev/null 2>&1; then
    log "creating ${TINYASSETS_USER} user (uid ${TINYASSETS_UID})..."
    useradd --system \
            --uid "${TINYASSETS_UID}" \
            --home "${TINYASSETS_HOME}" \
            --create-home \
            --shell /usr/sbin/nologin \
            --comment "TinyAssets daemon service account" \
            "${TINYASSETS_USER}"
else
    log "${TINYASSETS_USER} user already exists"
fi

# Add tinyassets user to docker group so it can issue docker compose
# commands via the systemd unit.
if ! id -nG "${TINYASSETS_USER}" | grep -qw docker; then
    log "adding ${TINYASSETS_USER} to docker group..."
    usermod -aG docker "${TINYASSETS_USER}"
fi

# ----- 4a. ensure deploy dir exists before any SCP / git-clone step --------
# DR drill SCPs backup-restore.sh into /opt/tinyassets/deploy/ before git-clone
# runs; the target must exist independently of the clone completing first.
mkdir -p "${TINYASSETS_HOME}/deploy"

# ----- 4. repo checkout at /opt/tinyassets ----------------------------------

if [[ ! -d "${TINYASSETS_HOME}/.git" ]]; then
    log "cloning repo into ${TINYASSETS_HOME}..."
    # Wipe any pre-existing non-git content (e.g. useradd created
    # /opt/tinyassets as home, leaving it empty). Safe because the
    # directory only exists if we just created it.
    rm -rf "${TINYASSETS_HOME}"
    git clone --branch "${REPO_REF}" --depth 1 "${REPO_URL}" "${TINYASSETS_HOME}"
else
    log "repo already present at ${TINYASSETS_HOME}; fetching latest..."
    git -C "${TINYASSETS_HOME}" fetch --depth 1 origin "${REPO_REF}"
    git -C "${TINYASSETS_HOME}" reset --hard "origin/${REPO_REF}"
fi
chown -R "${TINYASSETS_USER}:${TINYASSETS_USER}" "${TINYASSETS_HOME}"

# Make the compose.yml reachable at the path the systemd unit expects.
if [[ ! -f "${TINYASSETS_HOME}/compose.yml" ]]; then
    ln -sf "${TINYASSETS_HOME}/deploy/compose.yml" "${TINYASSETS_HOME}/compose.yml"
fi

# ----- 5. /etc/tinyassets env directory -------------------------------------

mkdir -p "${ENV_DIR}"
chown "root:${TINYASSETS_USER}" "${ENV_DIR}"
chmod 750 "${ENV_DIR}"

if [[ ! -f "${ENV_DIR}/env" ]]; then
    log "creating ${ENV_DIR}/env from template (DO NOT FORGET TO FILL IN)..."
    cp "${TINYASSETS_HOME}/deploy/tinyassets-env.template" "${ENV_DIR}/env"
    chown "root:${TINYASSETS_USER}" "${ENV_DIR}/env"
    chmod 640 "${ENV_DIR}/env"
    log "  → edit ${ENV_DIR}/env and fill in CLOUDFLARE_TUNNEL_TOKEN + SUPABASE_* + GITHUB_OAUTH_* before starting the service"
else
    log "${ENV_DIR}/env already present; leaving contents alone"
fi

# ----- 6. systemd unit install --------------------------------------------

SYSTEMD_UNIT="/etc/systemd/system/tinyassets-daemon.service"
if [[ ! -f "${SYSTEMD_UNIT}" ]] \
   || ! cmp -s "${TINYASSETS_HOME}/deploy/tinyassets-daemon.service" "${SYSTEMD_UNIT}"; then
    log "installing tinyassets-daemon.service..."
    cp "${TINYASSETS_HOME}/deploy/tinyassets-daemon.service" "${SYSTEMD_UNIT}"
    systemctl daemon-reload
    systemctl enable tinyassets-daemon
    log "  daemon unit installed + enabled (NOT started — fill env first)"
else
    log "tinyassets-daemon.service already current"
fi

# Row L — watchdog unit + timer. Enabled immediately because it's
# idempotent even before the main daemon starts — it just records
# reds + waits to cross threshold.
WATCHDOG_UNIT="/etc/systemd/system/tinyassets-watchdog.service"
WATCHDOG_TIMER="/etc/systemd/system/tinyassets-watchdog.timer"
watchdog_changed=0
if [[ ! -f "${WATCHDOG_UNIT}" ]] \
   || ! cmp -s "${TINYASSETS_HOME}/deploy/tinyassets-watchdog.service" "${WATCHDOG_UNIT}"; then
    cp "${TINYASSETS_HOME}/deploy/tinyassets-watchdog.service" "${WATCHDOG_UNIT}"
    watchdog_changed=1
fi
if [[ ! -f "${WATCHDOG_TIMER}" ]] \
   || ! cmp -s "${TINYASSETS_HOME}/deploy/tinyassets-watchdog.timer" "${WATCHDOG_TIMER}"; then
    cp "${TINYASSETS_HOME}/deploy/tinyassets-watchdog.timer" "${WATCHDOG_TIMER}"
    watchdog_changed=1
fi
if [[ "${watchdog_changed}" -eq 1 ]]; then
    log "installed tinyassets-watchdog service + timer"
    systemctl daemon-reload
    systemctl enable --now tinyassets-watchdog.timer
else
    log "tinyassets-watchdog service + timer already current"
fi

# Scoped sudoers rule — tinyassets user gets NOPASSWD ONLY for
# `systemctl restart tinyassets-daemon.service`. Watchdog needs this when
# threshold is crossed. No other sudo privileges granted.
SUDOERS_FILE="/etc/sudoers.d/tinyassets-watchdog"
SUDOERS_RULE="${TINYASSETS_USER} ALL=(root) NOPASSWD:/usr/bin/systemctl restart tinyassets-daemon.service"
if [[ ! -f "${SUDOERS_FILE}" ]] || ! grep -qF "${SUDOERS_RULE}" "${SUDOERS_FILE}"; then
    log "installing scoped sudoers rule for watchdog restart..."
    echo "${SUDOERS_RULE}" > "${SUDOERS_FILE}"
    chmod 0440 "${SUDOERS_FILE}"
    if ! visudo -c -q; then
        log "ERROR: sudoers syntax check failed; removing the rule"
        rm -f "${SUDOERS_FILE}"
        exit 1
    fi
else
    log "sudoers rule already present"
fi

# Row J — backup service + timer. Enabled unconditionally — if
# STORAGEBOX_* env is blank, backup.sh exits 1 with a clear message.
# Enable-on-install gives ops a one-step "fill the creds and it
# backs up tonight" flow instead of a forgotten-enable trap.
BACKUP_UNIT="/etc/systemd/system/tinyassets-backup.service"
BACKUP_TIMER="/etc/systemd/system/tinyassets-backup.timer"
backup_changed=0
if [[ ! -f "${BACKUP_UNIT}" ]] \
   || ! cmp -s "${TINYASSETS_HOME}/deploy/tinyassets-backup.service" "${BACKUP_UNIT}"; then
    cp "${TINYASSETS_HOME}/deploy/tinyassets-backup.service" "${BACKUP_UNIT}"
    backup_changed=1
fi
if [[ ! -f "${BACKUP_TIMER}" ]] \
   || ! cmp -s "${TINYASSETS_HOME}/deploy/tinyassets-backup.timer" "${BACKUP_TIMER}"; then
    cp "${TINYASSETS_HOME}/deploy/tinyassets-backup.timer" "${BACKUP_TIMER}"
    backup_changed=1
fi
if [[ "${backup_changed}" -eq 1 ]]; then
    log "installed tinyassets-backup service + timer"
    systemctl daemon-reload
    systemctl enable --now tinyassets-backup.timer
else
    log "tinyassets-backup service + timer already current"
fi

# Weekly docker image prune — prevents disk fill from accumulated image
# tags (each deploy pulls ~1.78 GB; without pruning 20 deploys fills
# a 25 GB Droplet).
PRUNE_UNIT="/etc/systemd/system/tinyassets-prune.service"
PRUNE_TIMER="/etc/systemd/system/tinyassets-prune.timer"
prune_changed=0
if [[ ! -f "${PRUNE_UNIT}" ]] \
   || ! cmp -s "${TINYASSETS_HOME}/deploy/tinyassets-prune.service" "${PRUNE_UNIT}"; then
    cp "${TINYASSETS_HOME}/deploy/tinyassets-prune.service" "${PRUNE_UNIT}"
    prune_changed=1
fi
if [[ ! -f "${PRUNE_TIMER}" ]] \
   || ! cmp -s "${TINYASSETS_HOME}/deploy/tinyassets-prune.timer" "${PRUNE_TIMER}"; then
    cp "${TINYASSETS_HOME}/deploy/tinyassets-prune.timer" "${PRUNE_TIMER}"
    prune_changed=1
fi
if [[ "${prune_changed}" -eq 1 ]]; then
    log "installed tinyassets-prune service + timer"
    systemctl daemon-reload
    systemctl enable --now tinyassets-prune.timer
else
    log "tinyassets-prune service + timer already current"
fi

# ----- 7. swap file -------------------------------------------------------

# 960 MB RAM droplets OOM-kill under peak load without swap. 2 GB swapfile
# at /swapfile with vm.swappiness=10 matches live prod config applied
# 2026-04-21. Idempotent: skips each step whose end-state is already reached.
SWAPFILE="/swapfile"
SWAP_SIZE_MB=2048

if [[ ! -f "${SWAPFILE}" ]]; then
    log "creating ${SWAPFILE} (${SWAP_SIZE_MB} MB)..."
    fallocate -l "${SWAP_SIZE_MB}M" "${SWAPFILE}" || \
        dd if=/dev/zero of="${SWAPFILE}" bs=1M count="${SWAP_SIZE_MB}" status=none
    chmod 600 "${SWAPFILE}"
    mkswap "${SWAPFILE}"
    swapon "${SWAPFILE}"
    log "  swap active: $(free -h | grep Swap)"
else
    log "swapfile already exists ($(du -sh "${SWAPFILE}" | cut -f1))"
    # Activate if not already on (e.g. if box rebooted without fstab entry).
    if ! swapon --show | grep -q "${SWAPFILE}"; then
        swapon "${SWAPFILE}"
        log "  swapon ${SWAPFILE} (was off)"
    fi
fi

# Persist in /etc/fstab — idempotent guard prevents duplicate lines.
FSTAB_ENTRY="${SWAPFILE} none swap sw 0 0"
if ! grep -qF "${FSTAB_ENTRY}" /etc/fstab; then
    log "adding swap entry to /etc/fstab..."
    echo "${FSTAB_ENTRY}" >> /etc/fstab
else
    log "/etc/fstab swap entry already present"
fi

# Reduce swappiness so RAM is preferred. Write to sysctl.d for persistence.
SYSCTL_SWAP="/etc/sysctl.d/99-workflow-swap.conf"
if [[ ! -f "${SYSCTL_SWAP}" ]]; then
    echo "vm.swappiness=10" > "${SYSCTL_SWAP}"
    sysctl -p "${SYSCTL_SWAP}" >/dev/null
    log "vm.swappiness=10 set + persisted"
else
    log "vm.swappiness already configured"
fi

log "bootstrap complete."
cat <<EOF

Next steps (host action required):

  1. Fill in secrets:
       sudo nano ${ENV_DIR}/env
     (See deploy/HETZNER-DEPLOY.md for which values go where.)

  2. Start the service:
       sudo systemctl start tinyassets-daemon

  3. Tail logs:
       sudo journalctl -u tinyassets-daemon -f

  4. Verify canary green:
       python3 ${TINYASSETS_HOME}/scripts/mcp_public_canary.py \\
           --url https://tinyassets.io/mcp --verbose

  If the canary comes back exit 0 with [canary] OK, the self-host
  deploy is live. Host machine can now power off + tinyassets.io/mcp
  stays up.

EOF
