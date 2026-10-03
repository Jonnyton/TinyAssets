"""The thin loop end to end: the real writer, router, broker adapter and journal,
a scripted box and synthetic model wires (``test_interactive_http_agent``'s rig).
"""

from __future__ import annotations

import json
import logging

import pytest

from tests import test_interactive_http_agent as base
from tests.agent_loop_fakes import FakeBox
from tinyassets.agent_loop import served_chat
from tinyassets.engine_tool_client import EngineToolError
from tinyassets.storage.account_agent_loop import set_account_agent_loop

rig = base.rig
reader = base.reader
served = base.served
run = base.run


@pytest.fixture
def agent(base_agent, monkeypatch):
    set_account_agent_loop(
        base_agent.served.context.universe_dir.parent,
        owner_user_id="owner", agent_loop="thin", updated_by="test",
    )
    box = FakeBox(lambda argv, stdin: (b"box says hi", 0))
    monkeypatch.setattr(served_chat, "_box_provider", box)
    base_agent.box = box
    return base_agent


base_agent = base.agent


def _last_tool_text(agent):
    messages = agent.wires[-1][1]["body"]["messages"]
    return json.loads(messages[-1]["content"])["content"][0]["text"]


def test_box_tool_runs_in_the_bound_box_by_journal_op_id(agent):
    agent.tool_call = ("bash", '{"command": "echo hi"}')
    assert run(agent) == "finished exact answer"
    turn = agent.latest()
    assert turn.state == "completed"
    # Bound ONCE at turn start, to this owner and command center and turn.
    assert agent.box.binds == [(agent.served.context.universe_dir.name, "owner", turn.turn_id)]
    assert agent.box.starts == [f"{turn.turn_id}:1:1"]
    assert agent.box.execs[f"{turn.turn_id}:1:1"].argv == ["/bin/bash", "-c", "echo hi"]
    # Never forwarded to the engine route.
    assert agent.tools == []
    assert _last_tool_text(agent) == "box says hi\n[exit code 0]"


def test_unknown_box_outcome_holds_the_turn_and_nothing_replays(agent):
    agent.box.fail_start = 2
    agent.tool_call = ("bash", '{"command": "rm -rf build"}')
    with pytest.raises(EngineToolError, match="unknown"):
        run(agent)
    turn = agent.latest()
    assert turn.state == "held_tool_unknown"
    # One model round, the same op_id asked twice, no second inference.
    assert len(agent.wires) == 1
    assert set(agent.box.starts) == {f"{turn.turn_id}:1:1"}


def test_owner_read_is_answered_by_the_loop_and_never_reaches_the_box(agent):
    agent.tool_call = ("activity", "{}")
    assert run(agent) == "finished exact answer"
    assert agent.box.starts == [] and agent.tools == []
    assert "activity" in json.loads(_last_tool_text(agent))


def test_engine_tools_keep_their_engine_route(agent):
    assert run(agent) == "finished exact answer"
    assert agent.tools == [("read_graph", {"target": "status"})]
    assert agent.box.starts == []


def test_no_box_provider_refuses_before_any_tool_runs(agent, monkeypatch):
    monkeypatch.setattr(served_chat, "_box_provider", None)
    agent.tool_call = ("bash", '{"command": "true"}')
    with pytest.raises(EngineToolError, match="box_unavailable"):
        run(agent)
    assert agent.wires == [] and agent.tools == []


def test_account_on_engine_keeps_todays_path(agent):
    set_account_agent_loop(
        agent.served.context.universe_dir.parent,
        owner_user_id="owner", agent_loop="engine", updated_by="test",
    )
    agent.tool_call = ("bash", '{"command": "true"}')
    assert run(agent) == "finished exact answer"
    assert agent.box.starts == [] and agent.tools == [("bash", {"command": "true"})]


def test_another_accounts_thin_setting_keeps_this_owners_path(base_agent):
    set_account_agent_loop(
        base_agent.served.context.universe_dir.parent,
        owner_user_id="another-owner", agent_loop="thin", updated_by="test",
    )
    base_agent.tool_call = ("bash", '{"command": "true"}')
    assert run(base_agent) == "finished exact answer"
    assert base_agent.tools == [("bash", {"command": "true"})]


def test_unresolved_owner_keeps_todays_path(agent, monkeypatch):
    def refuse(context):
        raise PermissionError("no current served request")

    monkeypatch.setattr(served_chat, "check_served_agent_tool_authority", refuse)
    assert not served_chat.thin_loop_selected(agent.served.context)


def test_an_owner_who_does_not_resolve_is_logged_not_defaulted_silently(
    agent, monkeypatch, caplog,
):
    """The engine path is the safe answer, but it must not be a silent one.

    An owner whose authority check refuses, and an owner who resolves to
    nothing, are both different from an owner who CHOSE engine -- the setting
    here is thin, so a quiet False would be indistinguishable from a real
    choice. Each says so at WARNING.
    """
    def refuse(context):
        raise PermissionError("no current served request")

    monkeypatch.setattr(served_chat, "check_served_agent_tool_authority", refuse)
    with caplog.at_level(logging.WARNING, logger=served_chat.__name__):
        assert not served_chat.thin_loop_selected(agent.served.context)
    refused = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(refused) == 1, caplog.text
    assert "no served-agent tool authority" in refused[0].getMessage()
    assert "PermissionError" in refused[0].getMessage()

    caplog.clear()
    monkeypatch.setattr(served_chat, "check_served_agent_tool_authority", lambda _c: "")
    with caplog.at_level(logging.WARNING, logger=served_chat.__name__):
        assert not served_chat.thin_loop_selected(agent.served.context)
    blank = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(blank) == 1, caplog.text
    assert "did not resolve to an account" in blank[0].getMessage()


def test_a_resolved_owners_choice_is_not_warned_about(agent, caplog):
    """The quiet path stays quiet: a real choice logs nothing at WARNING."""
    with caplog.at_level(logging.WARNING, logger=served_chat.__name__):
        assert served_chat.thin_loop_selected(agent.served.context)
        set_account_agent_loop(
            agent.served.context.universe_dir.parent,
            owner_user_id="owner", agent_loop="engine", updated_by="test",
        )
        assert not served_chat.thin_loop_selected(agent.served.context)
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
