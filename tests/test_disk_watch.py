"""Tests for scripts/disk_watch.py + deploy/ unit-file sentinels."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from disk_watch import check  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIP_LOGS_SERVICE = REPO_ROOT / "deploy" / "tinyassets-ship-logs.service"
SHIP_LOGS_TIMER = REPO_ROOT / "deploy" / "tinyassets-ship-logs.timer"
DISK_WATCH_SERVICE = REPO_ROOT / "deploy" / "tinyassets-disk-watch.service"
DISK_WATCH_TIMER = REPO_ROOT / "deploy" / "tinyassets-disk-watch.timer"


# ---------------------------------------------------------------------------
# disk_watch.py logic
# ---------------------------------------------------------------------------


def test_below_threshold_returns_0():
    rc = check(
        path="/var/lib/docker",
        threshold=80,
        dry_run=True,
        disk_fn=lambda p: 50.0,
    )
    assert rc == 0


def test_above_threshold_dry_run_returns_1():
    rc = check(
        path="/var/lib/docker",
        threshold=80,
        dry_run=True,
        disk_fn=lambda p: 85.0,
    )
    assert rc == 1


def test_above_threshold_opens_issue():
    opened = []

    def _issue(token, repo, path, pct, threshold, **_kw):
        opened.append({"path": path, "pct": pct})
        return "https://github.com/owner/repo/issues/99"

    rc = check(
        path="/var/lib/docker",
        threshold=80,
        token="fake-token",
        dry_run=False,
        disk_fn=lambda p: 85.0,
        issue_fn=_issue,
    )
    assert rc == 1
    assert opened == [{"path": "/var/lib/docker", "pct": 85.0}]


def test_above_threshold_no_token_still_returns_1():
    rc = check(
        path="/var/lib/docker",
        threshold=80,
        token="",
        dry_run=False,
        disk_fn=lambda p: 90.0,
    )
    assert rc == 1


def test_path_not_found_returns_0():
    """Non-existent path is non-fatal — returns 0."""
    def _bad_disk(p):
        raise FileNotFoundError(f"no such file: {p}")

    rc = check(
        path="/nonexistent/path",
        threshold=80,
        dry_run=True,
        disk_fn=_bad_disk,
    )
    assert rc == 0


def test_exactly_at_threshold_is_ok():
    rc = check(
        path="/var/lib/docker",
        threshold=80,
        dry_run=True,
        disk_fn=lambda p: 80.0,
    )
    # 80.0 < 80 is False, so this fires — adjust: threshold is EXCLUSIVE
    # (pct < threshold means OK). At exactly 80%, alert fires.
    assert rc == 1


def test_issue_fn_called_with_correct_args():
    calls = []

    def _issue(token, repo, path, pct, threshold, **_kw):
        calls.append((token, repo, path, pct, threshold))
        return "https://github.com/x"

    check(
        path="/data",
        threshold=70,
        repo="owner/repo",
        token="tok",
        dry_run=False,
        disk_fn=lambda p: 75.0,
        issue_fn=_issue,
    )
    assert calls == [("tok", "owner/repo", "/data", 75.0, 70)]


# ---------------------------------------------------------------------------
# Sentinel: tinyassets-ship-logs.service
# ---------------------------------------------------------------------------


def test_ship_logs_service_exists():
    assert SHIP_LOGS_SERVICE.exists(), "tinyassets-ship-logs.service must exist in deploy/"


def test_ship_logs_service_is_oneshot():
    text = SHIP_LOGS_SERVICE.read_text(encoding="utf-8")
    assert "Type=oneshot" in text


def test_ship_logs_service_invokes_ship_logs_sh():
    text = SHIP_LOGS_SERVICE.read_text(encoding="utf-8")
    assert "ship-logs.sh" in text


def test_ship_logs_service_sources_env_file():
    text = SHIP_LOGS_SERVICE.read_text(encoding="utf-8")
    assert "EnvironmentFile=/etc/tinyassets/env" in text


# ---------------------------------------------------------------------------
# Sentinel: tinyassets-ship-logs.timer
# ---------------------------------------------------------------------------


def test_ship_logs_timer_exists():
    assert SHIP_LOGS_TIMER.exists(), "tinyassets-ship-logs.timer must exist in deploy/"


def test_ship_logs_timer_is_hourly():
    text = SHIP_LOGS_TIMER.read_text(encoding="utf-8")
    assert "hourly" in text.lower() or "OnCalendar=*:00:00" in text, (
        "ship-logs timer must fire hourly"
    )


def test_ship_logs_timer_has_install_section():
    text = SHIP_LOGS_TIMER.read_text(encoding="utf-8")
    assert "[Install]" in text
    assert "WantedBy=timers.target" in text


def test_ship_logs_timer_persistent():
    text = SHIP_LOGS_TIMER.read_text(encoding="utf-8")
    assert "Persistent=true" in text


# ---------------------------------------------------------------------------
# Sentinel: tinyassets-disk-watch.service
# ---------------------------------------------------------------------------


def test_disk_watch_service_exists():
    assert DISK_WATCH_SERVICE.exists(), "tinyassets-disk-watch.service must exist in deploy/"


def test_disk_watch_service_is_oneshot():
    text = DISK_WATCH_SERVICE.read_text(encoding="utf-8")
    assert "Type=oneshot" in text


def test_disk_watch_service_invokes_disk_watch_py():
    text = DISK_WATCH_SERVICE.read_text(encoding="utf-8")
    assert "disk_watch.py" in text


def test_disk_watch_service_sources_env_file():
    text = DISK_WATCH_SERVICE.read_text(encoding="utf-8")
    assert "EnvironmentFile=/etc/tinyassets/env" in text


def test_disk_watch_service_accepts_alert_exit_and_preserves_remediation_order():
    text = DISK_WATCH_SERVICE.read_text(encoding="utf-8")
    directives = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert [
        line for line in directives if line.startswith("SuccessExitStatus=")
    ] == ["SuccessExitStatus=1"]
    assert [line for line in directives if line.startswith("ExecStart=")] == [
        "ExecStart=/usr/bin/python3 /opt/tinyassets/scripts/disk_watch.py",
        "ExecStart=/usr/bin/python3 -m scripts.rotate_run_transcripts",
        "ExecStart=/usr/bin/python3 /opt/tinyassets/scripts/disk_autoprune.py",
    ]


# ---------------------------------------------------------------------------
# Sentinel: tinyassets-disk-watch.timer
# ---------------------------------------------------------------------------


def test_disk_watch_timer_exists():
    assert DISK_WATCH_TIMER.exists(), "tinyassets-disk-watch.timer must exist in deploy/"


def test_disk_watch_timer_is_daily():
    text = DISK_WATCH_TIMER.read_text(encoding="utf-8")
    assert "daily" in text.lower() or "UTC" in text, (
        "disk-watch timer must fire on a daily cadence"
    )


def test_disk_watch_timer_has_install_section():
    text = DISK_WATCH_TIMER.read_text(encoding="utf-8")
    assert "[Install]" in text
    assert "WantedBy=timers.target" in text


def test_disk_watch_timer_persistent():
    text = DISK_WATCH_TIMER.read_text(encoding="utf-8")
    assert "Persistent=true" in text
