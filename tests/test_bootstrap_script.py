"""Tests for deploy/hetzner-bootstrap.sh provisioning sections.

Coverage:
  - shellcheck lint (skipped if not installed)
  - Docker daemon.json section present with correct log config
  - Swap section present: creates /swapfile, swapon, fstab entry
  - fstab idempotency guard: grep -qF prevents duplicate lines
  - vm.swappiness sysctl.d persistence present
  - Script is idempotent (structural checks, not runtime)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BOOTSTRAP_SH = REPO / "deploy" / "hetzner-bootstrap.sh"

_SHELLCHECK = shutil.which("shellcheck")
_BASH = shutil.which("bash")


def _text() -> str:
    return BOOTSTRAP_SH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# shellcheck
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SHELLCHECK is None, reason="shellcheck not installed")
def test_bootstrap_shellcheck():
    result = subprocess.run(
        [_SHELLCHECK, "--severity=warning", str(BOOTSTRAP_SH)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"shellcheck hetzner-bootstrap.sh:\n{result.stdout}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Docker log-rotation section
# ---------------------------------------------------------------------------

def test_docker_daemon_json_path_present():
    assert "/etc/docker/daemon.json" in _text()


def test_docker_log_max_size_10m():
    assert '"max-size":"10m"' in _text() or '"max-size": "10m"' in _text()


def test_docker_log_max_file_3():
    assert '"max-file":"3"' in _text() or '"max-file": "3"' in _text()


def test_docker_log_driver_json_file():
    assert '"log-driver":"json-file"' in _text() or '"log-driver": "json-file"' in _text()


def test_docker_daemon_json_idempotent_guard():
    """Section must check existing config before writing (idempotency)."""
    text = _text()
    # Should have a guard that reads + validates existing daemon.json
    assert "DOCKER_DAEMON_JSON" in text
    # The section should only write if the file is absent OR misconfigured.
    # Check for a conditional wrapping the write.
    assert re.search(r'if \[\[.*DOCKER_DAEMON_JSON', text, re.MULTILINE), (
        "docker daemon.json write must be inside an idempotency guard"
    )


# ---------------------------------------------------------------------------
# Swap section
# ---------------------------------------------------------------------------

def test_swap_swapfile_path():
    assert 'SWAPFILE="/swapfile"' in _text()


def test_swap_size_2gb():
    assert "SWAP_SIZE_MB=2048" in _text() or "2048" in _text()


def test_swap_fallocate_present():
    assert "fallocate" in _text()


def test_swap_swapon_present():
    assert "swapon" in _text()


def test_swap_fstab_entry_present():
    text = _text()
    assert "/swapfile" in text
    assert "/etc/fstab" in text


def test_swap_fstab_idempotency_guard():
    """fstab append must be guarded by grep -qF to prevent duplicate lines."""
    text = _text()
    # The guard must use grep with -qF (fixed-string quiet match) on /etc/fstab
    assert re.search(r'grep.*-.*q.*F.*fstab|grep.*fstab.*-.*q.*F', text), (
        "fstab append must be guarded by 'grep -qF ... /etc/fstab' to prevent duplicates"
    )


def test_swap_chmod_600():
    """swapfile must be chmod 600 (world-readable swap is a security risk)."""
    assert "chmod 600" in _text()


# ---------------------------------------------------------------------------
# vm.swappiness persistence
# ---------------------------------------------------------------------------

def test_swappiness_sysctl_d_file():
    assert "sysctl.d" in _text()


def test_swappiness_value_10():
    assert "vm.swappiness=10" in _text()


def test_swappiness_idempotent_guard():
    text = _text()
    assert re.search(r'if \[\[.*SYSCTL_SWAP', text, re.MULTILINE), (
        "vm.swappiness write must be inside an idempotency guard"
    )


# ── Task #61 — mkdir -p /opt/tinyassets/deploy pre-git-clone ───────────


def test_deploy_dir_mkdir_present():
    text = _text()
    assert "mkdir -p" in text and "/deploy" in text, (
        "hetzner-bootstrap.sh must mkdir -p the deploy dir before git-clone"
    )


def test_deploy_dir_mkdir_before_git_clone():
    text = _text()
    mkdir_pos = text.find("mkdir -p")
    # Find the position of the actual git clone command.
    clone_pos = text.find("git clone")
    assert mkdir_pos != -1 and clone_pos != -1, "both mkdir and git clone must be present"
    assert mkdir_pos < clone_pos, (
        "mkdir -p deploy dir must appear before the git clone step"
    )


def test_deploy_dir_mkdir_uses_workflow_home_var():
    text = _text()
    # Should use the ${TINYASSETS_HOME} variable, not a hardcoded path.
    assert re.search(r'mkdir -p.*TINYASSETS_HOME.*deploy', text), (
        "deploy dir mkdir should use ${TINYASSETS_HOME}/deploy, not a hardcoded path"
    )


# ── Task #72 — cloud-init / apt-lock wait (DR drill race condition) ───────


def test_bootstrap_waits_for_cloud_init():
    """Bootstrap must call cloud-init status --wait before first apt call.

    Race: fresh Droplet runs cloud-init + unattended-upgrades at boot.
    Without this wait, apt update races the lock and exits 100.
    DR drill run ac4b562 proved this failure mode.
    """
    text = _text()
    assert "cloud-init" in text, (
        "hetzner-bootstrap.sh must call cloud-init to avoid apt-lock race on fresh Droplets"
    )
    assert "status --wait" in text, (
        "cloud-init call must use 'status --wait' to block until cloud-init completes"
    )


def test_bootstrap_cloud_init_is_guarded_by_command_check():
    """cloud-init may not be present on all distros; guard with 'command -v'."""
    text = _text()
    assert re.search(r'command -v cloud-init', text), (
        "cloud-init call must be guarded by 'command -v cloud-init' — "
        "not all Debian variants ship it"
    )


def test_bootstrap_cloud_init_failure_is_non_fatal():
    """cloud-init status --wait must use '|| true' — a non-zero exit (e.g.
    'status: error') must not abort the bootstrap."""
    text = _text()
    cloud_init_line = next(
        (line for line in text.splitlines() if "status --wait" in line), ""
    )
    assert "|| true" in cloud_init_line, (
        "cloud-init status --wait must be followed by '|| true' so bootstrap "
        "continues even when cloud-init reports an error status"
    )


def test_bootstrap_apt_lock_wait_loop_present():
    """A polling loop must wait for apt-get, dpkg, and unattended-upgr to clear
    before the first apt call."""
    text = _text()
    assert "pgrep" in text, (
        "hetzner-bootstrap.sh must use pgrep to poll for running apt/dpkg processes"
    )
    assert "unattended-upgr" in text, (
        "apt-lock wait must also check for 'unattended-upgr' process "
        "(DigitalOcean Droplets run it at first boot)"
    )


def test_bootstrap_apt_lock_wait_appears_before_apt_update():
    """The apt-lock wait block must come before the first 'apt-get update' call."""
    text = _text()
    pgrep_pos = text.find("pgrep")
    apt_update_pos = text.find("apt-get update")
    assert pgrep_pos != -1 and apt_update_pos != -1, (
        "Both pgrep wait and apt-get update must be in the script"
    )
    assert pgrep_pos < apt_update_pos, (
        "apt-lock wait (pgrep loop) must appear before the first 'apt-get update'"
    )


def test_bootstrap_apt_lock_wait_has_timeout():
    """The polling loop must have a bounded timeout to prevent infinite hangs."""
    text = _text()
    # The loop uses seq 1 180 (180 iterations × 1s = 3 min max)
    assert re.search(r'seq 1 1[0-9]{2}', text), (
        "apt-lock wait loop must be bounded (seq 1 N where N >= 100)"
    )
