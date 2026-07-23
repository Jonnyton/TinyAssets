"""Tests for the out-of-GitHub release reconcile dead-man."""

from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

deadman = importlib.import_module("release_reconcile_deadman")


NOW = dt.datetime(2026, 7, 22, 4, 0, tzinfo=dt.timezone.utc)


def _run(created_at: str, *, event: str = "schedule", conclusion: str = "success") -> dict:
    return {
        "created_at": created_at,
        "event": event,
        "conclusion": conclusion,
        "html_url": "https://github.com/Jonnyton/TinyAssets/actions/runs/123",
    }


class _Response:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


def test_classify_accepts_successful_schedule_at_threshold():
    payload = {"workflow_runs": [_run("2026-07-22T03:30:00Z")]}
    code, message = deadman.classify_runs(payload, now=NOW, threshold_min=30)
    assert code == 0
    assert "FRESH" in message
    assert "age=30.0min" in message


def test_classify_rejects_stale_schedule():
    payload = {"workflow_runs": [_run("2026-07-22T03:29:59Z")]}
    code, message = deadman.classify_runs(payload, now=NOW, threshold_min=30)
    assert code == deadman.STALE_EXIT_CODE
    assert "STALE" in message
    assert "> threshold=30min" in message


def test_classify_rejects_no_successful_scheduled_run():
    payload = {
        "workflow_runs": [
            _run("2026-07-22T03:59:00Z", event="workflow_dispatch"),
            _run("2026-07-22T03:45:00Z", conclusion="failure"),
        ],
    }
    code, message = deadman.classify_runs(payload, now=NOW, threshold_min=30)
    assert code == deadman.STALE_EXIT_CODE
    assert "no successful event=schedule run" in message


def test_classify_is_stateless_under_concurrent_load():
    payload = {"workflow_runs": [_run("2026-07-22T03:45:00Z")]}
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(
            pool.map(
                lambda _index: deadman.classify_runs(
                    payload,
                    now=NOW,
                    threshold_min=30,
                ),
                range(1_000),
            ),
        )
    assert {code for code, _message in results} == {0}


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"workflow_runs": "not-a-list"}, {"workflow_runs": [{}]}],
)
def test_classify_fails_closed_on_malformed_payload(payload):
    with pytest.raises(deadman.DeadmanError) as exc_info:
        deadman.classify_runs(payload, now=NOW, threshold_min=30)
    assert exc_info.value.code == deadman.API_EXIT_CODE


def test_run_check_pings_success_for_fresh_run():
    calls: list[str] = []

    def opener(request, timeout):
        calls.append(request.full_url)
        if request.full_url == deadman.DEFAULT_RUNS_URL:
            return _Response({"workflow_runs": [_run("2026-07-22T03:45:00Z")]})
        return _Response({"ok": True})

    code, message = deadman.run_check(
        deadman.DEFAULT_RUNS_URL,
        "https://hc-ping.com/example",
        threshold_min=30,
        timeout=5,
        now=NOW,
        opener=opener,
    )
    assert code == 0
    assert "FRESH" in message
    assert calls == [deadman.DEFAULT_RUNS_URL, "https://hc-ping.com/example"]


def test_run_check_forced_stale_pings_failure_and_exits_nonzero():
    calls: list[str] = []

    def opener(request, timeout):
        calls.append(request.full_url)
        if request.full_url == deadman.DEFAULT_RUNS_URL:
            return _Response({"workflow_runs": []})
        return _Response({"ok": True})

    code, message = deadman.run_check(
        deadman.DEFAULT_RUNS_URL,
        "https://hc-ping.com/example/",
        threshold_min=30,
        timeout=5,
        now=NOW,
        opener=opener,
    )
    assert code == deadman.STALE_EXIT_CODE
    assert "no successful event=schedule run" in message
    assert calls == [deadman.DEFAULT_RUNS_URL, "https://hc-ping.com/example/fail"]


def test_run_check_api_failure_still_pings_failure():
    calls: list[str] = []

    def opener(request, timeout):
        calls.append(request.full_url)
        if request.full_url == deadman.DEFAULT_RUNS_URL:
            raise urllib.error.URLError("offline")
        return _Response({"ok": True})

    code, message = deadman.run_check(
        deadman.DEFAULT_RUNS_URL,
        "https://hc-ping.com/example",
        threshold_min=30,
        timeout=5,
        now=NOW,
        opener=opener,
    )
    assert code == deadman.API_EXIT_CODE
    assert "GitHub runs API failed" in message
    assert calls[-1] == "https://hc-ping.com/example/fail"


def test_run_check_heartbeat_failure_is_loud():
    def opener(request, timeout):
        if request.full_url == deadman.DEFAULT_RUNS_URL:
            return _Response({"workflow_runs": [_run("2026-07-22T03:45:00Z")]})
        raise urllib.error.URLError("heartbeat offline")

    code, message = deadman.run_check(
        deadman.DEFAULT_RUNS_URL,
        "https://hc-ping.com/example",
        threshold_min=30,
        timeout=5,
        now=NOW,
        opener=opener,
    )
    assert code == deadman.HEARTBEAT_EXIT_CODE
    assert "heartbeat delivery failed" in message


def test_run_check_invalid_runs_url_still_pings_failure():
    calls: list[str] = []

    def opener(request, timeout):
        calls.append(request.full_url)
        return _Response({"ok": True})

    code, message = deadman.run_check(
        "not-a-url",
        "https://hc-ping.com/example",
        threshold_min=30,
        timeout=5,
        now=NOW,
        opener=opener,
    )
    assert code == deadman.API_EXIT_CODE
    assert "runs URL must be absolute HTTP(S)" in message
    assert calls == ["https://hc-ping.com/example/fail"]


def test_run_check_invalid_heartbeat_url_is_controlled_failure():
    def opener(request, timeout):
        return _Response({"workflow_runs": [_run("2026-07-22T03:45:00Z")]})

    code, message = deadman.run_check(
        deadman.DEFAULT_RUNS_URL,
        "not-a-url",
        threshold_min=30,
        timeout=5,
        now=NOW,
        opener=opener,
    )
    assert code == deadman.HEARTBEAT_EXIT_CODE
    assert "heartbeat URL must be absolute HTTP(S)" in message


def test_main_requires_heartbeat_url(monkeypatch, capsys):
    monkeypatch.delenv("TINYASSETS_RELEASE_DEADMAN_HEARTBEAT_URL", raising=False)
    code = deadman.main([])
    assert code == deadman.CONFIG_EXIT_CODE
    assert "heartbeat URL is required" in capsys.readouterr().err


def test_systemd_timer_runs_outside_github_scheduler():
    root = Path(__file__).resolve().parent.parent
    timer = (root / "deploy" / "tinyassets-release-deadman.timer").read_text(
        encoding="utf-8",
    )
    service = (root / "deploy" / "tinyassets-release-deadman.service").read_text(
        encoding="utf-8",
    )
    assert "OnCalendar=*:0/5" in timer
    assert "Persistent=true" in timer
    assert "EnvironmentFile=/etc/tinyassets/env" in service
    assert "/opt/tinyassets/scripts/release_reconcile_deadman.py" in service
    assert "Type=oneshot" in service


def test_host_service_workflow_installs_and_enables_deadman():
    root = Path(__file__).resolve().parent.parent
    workflow = (root / ".github" / "workflows" / "install-host-services.yml").read_text(
        encoding="utf-8",
    )
    assert "scripts/release_reconcile_deadman.py" in workflow
    assert "deploy/tinyassets-release-deadman.service" in workflow
    assert "deploy/tinyassets-release-deadman.timer" in workflow
    assert "systemctl enable --now tinyassets-release-deadman.timer" in workflow
