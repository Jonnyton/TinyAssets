"""Tests for deploy/tinyassets-prune.service and tinyassets-prune.timer.

Coverage:
  - Service file: Type=oneshot, shared bounded daemon-only retention entrypoint
  - No broad Docker prune or age-only safety policy; activation stays operator-owned
  - Timer file: weekly OnCalendar, Persistent=true
  - Bootstrap delegates both units and activation to the shared installer
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVICE = REPO / "deploy" / "tinyassets-prune.service"
TIMER = REPO / "deploy" / "tinyassets-prune.timer"
BOOTSTRAP = REPO / "deploy" / "hetzner-bootstrap.sh"
INSTALLER = REPO / "deploy" / "install-host-uptime-services.sh"


def _svc() -> str:
    return SERVICE.read_text(encoding="utf-8")


def _tmr() -> str:
    return TIMER.read_text(encoding="utf-8")


def _boot() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


def _installer() -> str:
    return INSTALLER.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# service file shape
# ---------------------------------------------------------------------------

def test_service_file_exists():
    assert SERVICE.exists(), f"Missing: {SERVICE}"


def test_service_type_oneshot():
    assert "Type=oneshot" in _svc()


def test_service_uses_shared_bounded_retention_entrypoint():
    assert "WorkingDirectory=/opt/tinyassets-host-uptime/current" in _svc()
    assert (
        "ExecStart=/usr/bin/python3 "
        "/opt/tinyassets-host-uptime/current/scripts/disk_autoprune.py --apply"
    ) in _svc()
    hourly = (REPO / "deploy" / "tinyassets-disk-watch.service").read_text(encoding="utf-8")
    assert "scripts/disk_autoprune.py --apply" in hourly


def test_service_has_no_broad_prune_or_age_only_deletion():
    for forbidden in (
        "docker image prune", "docker builder prune", "docker system prune",
        "docker volume prune", "until=168h",
    ):
        assert forbidden not in _svc()


def test_service_does_not_opt_itself_into_destructive_retention():
    # --apply alone is read-only; the tested helper requires a separate exact
    # operator opt-in. A timer must not hardcode that authority in the unit.
    assert "EnvironmentFile=/etc/tinyassets/env" in _svc()
    assert "TINYASSETS_DAEMON_IMAGE_RETENTION_APPLY" not in _svc()
    assert "SuccessExitStatus=1" in _svc()


def test_service_after_docker():
    assert "After=docker.service" in _svc()


# ---------------------------------------------------------------------------
# timer file shape
# ---------------------------------------------------------------------------

def test_timer_file_exists():
    assert TIMER.exists(), f"Missing: {TIMER}"


def test_timer_weekly():
    assert "OnCalendar=" in _tmr()
    # Must be weekly cadence (Sun or weekly keyword)
    tmr = _tmr()
    assert "Sun" in tmr or "weekly" in tmr.lower(), (
        "Timer must run weekly (e.g. 'Sun 04:00 UTC')"
    )


def test_timer_persistent():
    assert "Persistent=true" in _tmr()


def test_timer_requires_service():
    assert "tinyassets-prune.service" in _tmr()


def test_timer_wantedby_timers_target():
    assert "WantedBy=timers.target" in _tmr()


# ---------------------------------------------------------------------------
# bootstrap delegates the units
# ---------------------------------------------------------------------------

def test_bootstrap_installs_prune_service():
    assert _boot().count("install-host-uptime-services.sh") == 1
    assert "tinyassets-prune.service" in _installer()


def test_bootstrap_installs_prune_timer():
    assert "tinyassets-prune.timer" in _installer()


def test_bootstrap_enables_prune_timer():
    installer = _installer()
    assert "tinyassets-prune.timer" in installer
    assert '"${SYSTEMCTL_BIN}" enable --now "${TIMERS[@]}"' in installer
