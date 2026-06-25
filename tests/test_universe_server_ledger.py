"""Tests for the public action ledger contract.

PLAN.md Design Decision: "Private chats, public actions." Every universe-
affecting write must land in the per-universe ledger with author + action
+ target + timestamp + summary.

The enforcement point is `_dispatch_with_ledger` in `workflow/universe_server.py`:
a shared write-wrapper funnels every action listed in `WRITE_ACTIONS` through
a ledger append on success. These tests exercise the wrapper via the internal
dispatch shape, not the per-handler functions directly, because bypassing the
dispatcher would bypass the ledger — which is exactly the failure mode we're
preventing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import workflow.api.universe as us


def _call(action: str, **kwargs) -> dict:
    """Invoke an action through the same dispatch path the MCP tool uses."""
    base_kwargs = {
        "universe_id": "",
        "text": "",
        "path": "",
        "category": "direction",
        "target": "",
        "query_type": "facts",
        "filter_text": "",
        "request_type": "scene_direction",
        "branch_id": "",
        "filename": "",
        "provenance_tag": "",
        "anchor_json": "",
        "limit": 20,
    }
    base_kwargs.update(kwargs)

    dispatch = {
        "list": us._action_list_universes,
        "inspect": us._action_inspect_universe,
        "read_output": us._action_read_output,
        "query_world": us._action_query_world,
        "get_activity": us._action_get_activity,
        "get_ledger": us._action_get_ledger,
        "submit_request": us._action_submit_request,
        "give_direction": us._action_give_direction,
        "read_premise": us._action_read_premise,
        "set_premise": us._action_set_premise,
        "set_persona_name": us._action_set_persona_name,
        "add_canon": us._action_add_canon,
        "list_canon": us._action_list_canon,
        "read_canon": us._action_read_canon,
        "control_daemon": us._action_control_daemon,
        "switch_universe": us._action_switch_universe,
        "create_universe": us._action_create_universe,
    }
    handler = dispatch[action]
    return json.loads(us._dispatch_with_ledger(action, handler, base_kwargs))


@pytest.fixture
def universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Spin up an isolated base directory with one empty universe."""
    base = tmp_path / "output"
    uid = "test-uni"
    (base / uid).mkdir(parents=True)
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", uid)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "test-user")
    return uid


def _ledger(uid: str) -> list[dict]:
    data = json.loads((us._base_path() / uid / "ledger.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data


def test_write_actions_table_is_exhaustive() -> None:
    """Regression guard: if someone adds a new write action, they must
    declare it in WRITE_ACTIONS — otherwise the wrapper passes the result
    through without ledger attribution, which is exactly the bug we're
    preventing. This test pins the expected set so drift is caught.
    """
    expected = {
        "submit_request", "give_direction", "set_premise",
        "set_persona_name",
        "add_canon", "add_canon_from_path",
        "control_daemon", "switch_universe", "create_universe",
        "queue_cancel",
        "subscribe_goal", "unsubscribe_goal", "post_to_goal_pool",
        "submit_node_bid",  # Phase G
        "set_tier_config",  # Phase H
        "daemon_create", "daemon_summon", "daemon_banish",
        "daemon_pause", "daemon_resume", "daemon_restart",
        "daemon_update_behavior",
        "daemon_memory_capture", "daemon_memory_review",
        "daemon_memory_promote",
    }
    assert set(us.WRITE_ACTIONS.keys()) == expected


def test_set_premise_appends_ledger(universe: str) -> None:
    out = _call("set_premise", text="A tower of bones.")
    assert out["status"] == "updated"

    entries = _ledger(universe)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == "set_premise"
    assert entry["actor"] == "test-user"
    assert entry["target"] == "soul.md"
    assert entry["summary"] == "A tower of bones."
    assert "timestamp" in entry
    assert entry["payload"]["bytes"] == len("A tower of bones.".encode("utf-8"))
    assert entry["payload"]["legacy_program_mirror"] == "PROGRAM.md"


def test_set_persona_name_appends_ledger(universe: str) -> None:
    """Naming the persona is a public write — it lands in the ledger with the
    soul as its target (the founder named the universe's mind)."""
    out = _call("set_persona_name", text="Tiny")
    assert out["status"] == "updated"
    assert out["persona"]["name"] == "Tiny"

    entries = _ledger(universe)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == "set_persona_name"
    assert entry["actor"] == "test-user"
    assert entry["target"] == us.SOUL_FILENAME
    assert entry["summary"] == "persona name: Tiny"
    assert "timestamp" in entry
    assert entry["payload"]["persona_name"] == "Tiny"


def test_set_premise_empty_does_not_append(universe: str) -> None:
    out = _call("set_premise", text="  ")
    assert "error" in out
    ledger_path = us._base_path() / universe / "ledger.json"
    assert not ledger_path.exists()


def test_give_direction_appends_ledger(universe: str) -> None:
    out = _call("give_direction", text="Tighten the opening.", category="direction")
    assert out["status"] == "written"

    entries = _ledger(universe)
    assert len(entries) == 1
    assert entries[0]["action"] == "give_direction"
    assert entries[0]["summary"] == "Tighten the opening."
    assert entries[0]["payload"]["category"] == "direction"
    assert entries[0]["payload"]["note_id"] == out["note_id"]


def test_give_direction_accepts_line_anchor(universe: str) -> None:
    anchor = {"start_line": 3, "end_line": 4, "start_column": 2, "end_column": 17}
    out = _call(
        "give_direction",
        text="Keep this span, but sharpen the verb.",
        target="output/chapter-1.md",
        anchor_json=json.dumps(anchor),
    )
    assert out["status"] == "written"
    assert out["target"] == "output/chapter-1.md"
    assert out["anchor"] == anchor

    entries = _ledger(universe)
    assert entries[0]["payload"]["anchor"] == anchor


def test_submit_request_appends_ledger(universe: str) -> None:
    out = _call("submit_request", text="Please add a dragon.", request_type="scene_direction")
    assert out["status"] == "pending"

    entries = _ledger(universe)
    assert len(entries) == 1
    assert entries[0]["action"] == "submit_request"
    assert entries[0]["target"] == out["request_id"]
    assert entries[0]["payload"]["request_type"] == "scene_direction"
    assert entries[0]["payload"]["loop_dispatch"]["source"] == "legacy_no_soul_compat"


def test_add_canon_appends_ledger(universe: str) -> None:
    out = _call(
        "add_canon", filename="ref.md", text="# Reference\n",
        provenance_tag="rough notes",
    )
    assert out["status"] == "written"

    entries = _ledger(universe)
    assert len(entries) == 1
    assert entries[0]["action"] == "add_canon"
    assert entries[0]["target"] == "canon/ref.md"
    assert entries[0]["payload"]["provenance"] == "rough notes"


def test_control_daemon_pause_and_resume_append_ledger(universe: str) -> None:
    _call("control_daemon", text="pause")
    _call("control_daemon", text="resume")

    entries = _ledger(universe)
    summaries = [e["summary"] for e in entries]
    assert summaries == ["pause", "resume"]
    assert all(e["action"] == "control_daemon" for e in entries)


def test_control_daemon_status_does_not_append(universe: str) -> None:
    _call("control_daemon", text="status")
    ledger_path = us._base_path() / universe / "ledger.json"
    assert not ledger_path.exists()


def test_switch_universe_appends_ledger(universe: str) -> None:
    other = "other-uni"
    (us._base_path() / other).mkdir(parents=True)

    out = _call("switch_universe", universe_id=other)
    assert out["status"] == "switching"

    entries = _ledger(other)
    assert len(entries) == 1
    assert entries[0]["action"] == "switch_universe"
    assert entries[0]["target"] == other


def test_create_universe_appends_ledger_to_new_universe(universe: str) -> None:
    out = _call("create_universe", universe_id="fresh-uni", text="A seedling kingdom.")
    assert out["status"] == "created"

    entries = _ledger("fresh-uni")
    assert len(entries) == 1
    assert entries[0]["action"] == "create_universe"
    assert entries[0]["summary"] == "A seedling kingdom."
    assert entries[0]["payload"]["has_premise"] is True
    assert entries[0]["payload"]["has_soul"] is True


def test_create_universe_surfaces_synthesis_first_run_checklist(
    universe: str,
) -> None:
    out = _call("create_universe", universe_id="checklist-uni", text="A seed.")

    checklist = out["first_run_checklist"]
    assert checklist["synthesis_signal_meaning"] == (
        "synthesis_signal_emitted only means an uploaded source was queued; "
        "it is meaningful after a premise exists, at least one canon source "
        "has been uploaded, and the daemon has processed the synthesize_source "
        "signal."
    )
    assert [step["id"] for step in checklist["steps"]] == [
        "premise",
        "canon_source",
        "synthesis_signal",
        "daemon_worldbuild",
    ]
    assert checklist["steps"][0]["complete"] is True
    assert checklist["steps"][1]["complete"] is False
    assert checklist["next_action"] == (
        "Upload canon with add_canon or add_canon_from_path, then wait for "
        "the daemon to process the synthesize_source signal."
    )


def test_get_ledger_returns_appended_entries(universe: str) -> None:
    _call("set_premise", text="First.")
    _call("set_premise", text="Second.")

    out = _call("get_ledger")
    assert out["count"] == 2
    # get_ledger returns newest-first
    assert out["entries"][0]["summary"] == "Second."
    assert out["entries"][1]["summary"] == "First."


def test_ledger_survives_across_mixed_writes(universe: str) -> None:
    _call("set_premise", text="Premise.")
    _call("give_direction", text="Direction.")
    us.ensure_universe_soul(
        us._base_path() / universe,
        loop_branch_def_id="fantasy_author:universe_cycle_wrapper",
    )
    _call("submit_request", text="Request.")
    _call("add_canon", filename="a.md", text="x", provenance_tag="test")

    entries = _ledger(universe)
    actions = [e["action"] for e in entries]
    assert actions == ["set_premise", "give_direction", "submit_request", "add_canon"]
    for entry in entries:
        assert entry["actor"] == "test-user"
        assert entry["timestamp"]


def test_actor_defaults_to_anonymous_without_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = tmp_path / "output"
    (base / "u").mkdir(parents=True)
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "u")
    monkeypatch.delenv("UNIVERSE_SERVER_USER", raising=False)

    _call("set_premise", text="x")
    entries = json.loads((base / "u" / "ledger.json").read_text(encoding="utf-8"))
    assert entries[0]["actor"] == "anonymous"


def test_truncate_caps_long_summaries(universe: str) -> None:
    long_text = "x" * 500
    _call("set_premise", text=long_text)
    entries = _ledger(universe)
    assert len(entries[0]["summary"]) <= 140


def test_read_actions_do_not_touch_ledger(universe: str) -> None:
    """Sanity: reads pass through the wrapper without appending."""
    _call("list")
    _call("inspect")
    _call("read_premise")
    _call("list_canon")
    _call("query_world")
    _call("get_activity")
    _call("get_ledger")

    ledger_path = us._base_path() / universe / "ledger.json"
    assert not ledger_path.exists()


def test_handler_error_result_does_not_append(universe: str) -> None:
    """If a handler returns `{'error': ...}`, the ledger stays untouched."""
    out = _call("add_canon", filename="", text="x")
    assert "error" in out

    ledger_path = us._base_path() / universe / "ledger.json"
    assert not ledger_path.exists()


def test_bypass_path_is_documented_only(universe: str) -> None:
    """Calling a handler directly (bypassing the wrapper) does NOT write.

    This test isn't a feature claim — it documents the known bypass path.
    Callers must go through `universe` tool dispatch, which funnels through
    `_dispatch_with_ledger`. If a future refactor exposes handlers to
    callers that skip the wrapper, this test will fail and flag it.
    """
    us._action_set_premise(universe_id=universe, text="direct call bypass")
    ledger_path = us._base_path() / universe / "ledger.json"
    assert not ledger_path.exists()
