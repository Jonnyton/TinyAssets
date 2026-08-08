"""A validator rejection carries its own fix — make sure it reaches the model."""

from __future__ import annotations

import json

from tinyassets.universe_agent_server import _with_repair_guidance


def test_a_rejection_becomes_a_correction():
    raw = json.dumps({
        "status": "rejected",
        "errors": ["Entry point is required when branch has nodes."],
        "suggestions": [{"issue": "Entry point is required.",
                         "proposed_fix": "Set entry_point to 'draft'."}],
    })
    out = _with_repair_guidance(raw)
    assert "THIS IS FIXABLE" in out
    assert "Set entry_point to 'draft'." in out
    assert "retry" in out


def test_multiple_fixes_are_all_surfaced():
    raw = json.dumps({
        "status": "rejected",
        "suggestions": [
            {"proposed_fix": "Set entry_point to 'draft'."},
            {"proposed_fix": "Add an edge to END."},
        ],
    })
    out = _with_repair_guidance(raw)
    assert "Set entry_point to 'draft'." in out
    assert "Add an edge to END." in out


def test_a_successful_build_is_untouched():
    raw = json.dumps({"status": "built", "branch_def_id": "abc123"})
    assert _with_repair_guidance(raw) == raw


def test_a_rejection_with_no_fix_is_untouched():
    """Do not promise a correction we do not have."""
    raw = json.dumps({"status": "rejected", "errors": ["something opaque"]})
    assert _with_repair_guidance(raw) == raw


def test_non_json_passes_through():
    assert _with_repair_guidance("refused: 403") == "refused: 403"


def test_blank_proposed_fixes_are_ignored():
    raw = json.dumps({
        "status": "rejected",
        "suggestions": [{"proposed_fix": "   "}, {"issue": "no fix key"}],
    })
    assert _with_repair_guidance(raw) == raw


def test_a_looping_turn_is_stopped(monkeypatch):
    """No bound on tool calls meant 12 identical failing builds in one turn.

    The AI SDK defaults isStepCount(20) for exactly this. Ours refuses rather
    than crashing, so the turn can still explain itself.
    """
    import tinyassets.universe_agent_server as srv

    monkeypatch.setattr(srv, "MAX_PLATFORM_CALLS_PER_TURN", 3)
    monkeypatch.setattr(srv, "_calls_this_turn", 0)
    monkeypatch.setenv(srv.ACTION_TOKEN_ENV, "")

    results = [srv._platform_action("branch", "list_versions") for _ in range(5)]
    # The first few refuse for lack of a token; the later ones refuse for
    # LOOPING, which is the guard firing.
    assert any("looping rather than progressing" in r for r in results)


def test_the_ceiling_message_tells_the_agent_what_to_do(monkeypatch):
    import tinyassets.universe_agent_server as srv

    monkeypatch.setattr(srv, "MAX_PLATFORM_CALLS_PER_TURN", 0)
    monkeypatch.setattr(srv, "_calls_this_turn", 0)
    out = srv._platform_action("branch", "list_versions")
    assert "tell my founder what is actually blocking" in out
