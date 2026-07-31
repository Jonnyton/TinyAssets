from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/diagnose-prod-startup.yml")


def _load() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_diagnostic_workflow_is_manual_read_only_and_bounded():
    workflow = _load()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    dispatch = workflow[True]["workflow_dispatch"]["inputs"]

    assert set(dispatch) == {"since_utc", "until_utc"}
    assert workflow["permissions"] == {"contents": "read"}
    assert "journalctl -u tinyassets-daemon" in text
    assert "scripts/sanitize_systemd_startup_diagnostics.py" in text
    assert "tail -c 262145" in text
    assert "timeout 35s ssh" in text
    assert "timeout 25s sudo journalctl" in text
    assert "2>/dev/null" in text
    assert "cat \"${diagnosis}\"" in text
    assert '${statuses[1]}' in text


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
    )
    for marker in forbidden:
        assert marker not in text
    assert "maximum diagnostic window is 10 minutes" in text
    assert "diagnostic window must be in the past" in text
