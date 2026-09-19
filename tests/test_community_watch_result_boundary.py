"""Execute the actual workflow parser without GitHub calls or credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/community-loop-watch.yml"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _execute_parser(tmp_path, raw, code):
    step = next(s for s in _workflow()["jobs"]["watch"]["steps"] if s.get("id") == "watch")
    source = step["run"].split("python - <<'PY'\n", 1)[1].split("\nPY", 1)[0]
    (tmp_path / "community-loop-status.json").write_text(raw, encoding="utf-8")
    output = tmp_path / "actions-output.txt"
    result = subprocess.run(
        [sys.executable, "-c", source], cwd=tmp_path, capture_output=True,
        text=True, timeout=10,
        env={**os.environ, "WATCH_EXIT_CODE": str(code), "GITHUB_OUTPUT": str(output)},
    )
    return result, output.read_text(encoding="utf-8") if output.exists() else ""


@pytest.mark.parametrize("raw,code", [
    ("", 1), ("Traceback: watcher crashed", 1), ("{}", 0), ("[]", 0), ("null", 0),
    ('{"overall":"green"}', 0),
    (json.dumps({"version": 2, "overall": "green", "exit_code": 0, "stages": []}), 1),
    (json.dumps({"version": 2, "overall": "red", "exit_code": 0, "stages": []}), 0),
    (json.dumps({"version": 2, "overall": "unexpected", "exit_code": 0, "stages": []}), 0),
    (json.dumps({"version": 2, "overall": "green", "exit_code": False, "stages": []}), 0),
])
def test_unavailable_watcher_never_manufactures_health(tmp_path, raw, code):
    result, outputs = _execute_parser(tmp_path, raw, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unknown"
    assert "monitor_status=unavailable" in outputs


@pytest.mark.parametrize("overall,code", [
    ("green", 0), ("yellow", 0), ("unknown", 0), ("red", 2), ("red", 3),
])
def test_available_typed_watcher_result_is_preserved(tmp_path, overall, code):
    raw = json.dumps({"version": 2, "overall": overall, "exit_code": code, "stages": []})
    result, outputs = _execute_parser(tmp_path, raw, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == overall
    assert "monitor_status=available" in outputs


def test_missing_or_invalid_watcher_output_fails_distinctly_from_platform_red():
    steps = _workflow()["jobs"]["watch"]["steps"]
    gate = next((s for s in steps if s.get("name") == "Fail when monitor is unavailable"), None)
    assert gate is not None
    assert "always()" in gate["if"]
    assert "steps.watch.outputs.monitor_status != 'available'" in gate["if"]
    assert "steps.watch.outputs.overall == ''" in gate["if"]
    assert "exit 3" in gate["run"]
    assert not gate.get("continue-on-error")
