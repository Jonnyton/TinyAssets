from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/diagnose-prod-startup.yml")


def _load() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_diagnostic_workflow_is_manual_read_only_and_bounded():
    workflow = _load()
    dispatch = workflow[True]["workflow_dispatch"]["inputs"]
    steps = workflow["jobs"]["diagnose"]["steps"]
    verification = next(
        step for step in steps if step.get("name") == "Verify secrets and bounded past window"
    )["run"]
    diagnosis = next(
        step for step in steps if step.get("name") == "Classify bounded historical unit journal"
    )["run"]

    assert set(dispatch) == {"since_utc", "until_utc"}
    assert workflow["permissions"] == {"contents": "read"}
    assert "--validate-window" in verification
    assert "scripts/sanitize_systemd_startup_diagnostics.py" in verification
    assert "journalctl -u tinyassets-daemon" in diagnosis
    assert "limit = 262143" in diagnosis
    assert "len(data) > limit" in diagnosis
    assert "data[-limit:]" in diagnosis
    assert "collections.deque" in diagnosis
    assert "read(65536)" in diagnosis
    assert "maxlen=5" in diagnosis
    assert "--lines=" not in diagnosis
    assert "--framed-input" in diagnosis
    assert "tail -c" not in diagnosis
    assert "timeout 35s ssh" in diagnosis
    assert "timeout 25s sudo journalctl" in diagnosis
    assert "2>/dev/null" in diagnosis
    assert "cat \"${diagnosis}\"" in diagnosis
    assert '${statuses[0]}' in diagnosis
    assert '${statuses[1]}' in diagnosis
    assert '${statuses[2]}' not in diagnosis


def test_diagnostic_workflow_cannot_mutate_or_publish_raw_journal():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    forbidden = (
        "systemctl restart",
        "systemctl start",
        "systemctl stop",
        "docker restart",
        "docker rm",
        "docker compose up",
        "upload-artifact",
        "gh issue",
        "journalctl >",
        "echo \"$raw",
        "GITHUB_OUTPUT",
        "GITHUB_STEP_SUMMARY",
        "tee ",
    )
    for marker in forbidden:
        assert marker not in text
