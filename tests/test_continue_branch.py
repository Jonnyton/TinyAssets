"""Regression guards for the retired standalone continue_branch action."""

from __future__ import annotations

import json


def test_continue_branch_is_not_a_branch_action() -> None:
    from tinyassets.api.branches import _BRANCH_ACTIONS

    assert "continue_branch" not in _BRANCH_ACTIONS


def test_continue_branch_extensions_call_is_unknown(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.universe_server import extensions

    result = json.loads(
        extensions(action="continue_branch", branch_def_id="branch-1")
    )

    assert result["error"] == "Unknown action 'continue_branch'."
    assert "continue_branch" not in result["available_actions"]
    assert "run_branch" in result["available_actions"]


def test_control_station_routes_continue_intent_to_run_branch_resume_from() -> None:
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT

    assert "resume_from=<run_id>" in _CONTROL_STATION_PROMPT
    assert "action=run_branch" in _CONTROL_STATION_PROMPT
    assert "action=continue_branch" not in _CONTROL_STATION_PROMPT
