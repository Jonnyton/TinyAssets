"""Tests for deploy/tinyassets-prune.service and tinyassets-prune.timer.

Coverage:
  - Service file: Type=oneshot, docker image prune + builder prune present
  - Service file: until=168h filter (prune images >7 days old)
  - Timer file: weekly OnCalendar, Persistent=true
  - Bootstrap wires both into provisioning
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVICE = REPO / "deploy" / "tinyassets-prune.service"
TIMER = REPO / "deploy" / "tinyassets-prune.timer"
BOOTSTRAP = REPO / "deploy" / "hetzner-bootstrap.sh"


def _svc() -> str:
    return SERVICE.read_text(encoding="utf-8")


def _tmr() -> str:
    return TIMER.read_text(encoding="utf-8")


def _boot() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# service file shape
# ---------------------------------------------------------------------------

def test_service_file_exists():
    assert SERVICE.exists(), f"Missing: {SERVICE}"


def test_service_type_oneshot():
    assert "Type=oneshot" in _svc()


def test_service_docker_image_prune():
    assert "docker image prune" in _svc()


def test_service_docker_builder_prune():
    assert "docker builder prune" in _svc()


def test_service_until_168h():
    """Prune filter must be 168h (7 days) to protect the current deploy tag."""
    assert "until=168h" in _svc()


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
# bootstrap wires the units
# ---------------------------------------------------------------------------

def test_bootstrap_installs_prune_service():
    assert "tinyassets-prune.service" in _boot()


def test_bootstrap_installs_prune_timer():
    assert "tinyassets-prune.timer" in _boot()


def test_bootstrap_enables_prune_timer():
    assert "tinyassets-prune.timer" in _boot()
    # systemctl enable --now must reference the timer
    import re
    assert re.search(r'systemctl enable.*tinyassets-prune\.timer', _boot()), (
        "bootstrap must enable --now tinyassets-prune.timer"
    )
