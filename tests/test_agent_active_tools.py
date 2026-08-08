"""The per-turn tool grant: what the agent may reach, and what it may not.

Two failures these pin, both of which happened while writing this:

1. A grant list maintained by hand drifted from the server's real tool names
   (``workspace_read_file`` for ``workspace_read``). Nothing errors — the tool
   just is not there, so the agent silently loses its file tools.
2. ``record_approval`` was reachable in the same turn as the refusal that
   created the pending request, letting the consent gate answer its own
   question. Only a docstring said not to.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from tinyassets.storage.action_approvals import ActionApprovalStore
from tinyassets.universe_intelligence import (
    _TOOL_REQUIRES_PENDING_APPROVAL,
    _active_tools,
    _engine_tool_names,
)

UNIVERSE = "u-probe"


@pytest.fixture
def universe(tmp_path, monkeypatch):
    """A data root laid out the way production is.

    The approval store lives at the DATA ROOT keyed by universe id — not inside
    the universe directory. An earlier version of this fixture handed the store
    a path of its own choosing, so test and code agreed with each other and both
    disagreed with production: a real pending approval read as none, and the
    founder's "yes" stalled on a permission prompt nobody could answer.

    So this points the canonical resolver at a temp root and writes through it,
    exactly as the action layer does.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    (tmp_path / UNIVERSE).mkdir()
    return tmp_path


def _store():
    """The store the way the ACTION layer opens it — via the shared resolver."""
    from tinyassets.universe_agent_actions import _base_path_for_scopes

    return ActionApprovalStore(_base_path_for_scopes())


def _granted_names(_universe=None) -> set[str]:
    return {name.split("__")[-1] for name in _active_tools(UNIVERSE)}


def test_tool_names_matches_registry():
    """The sync read is pinned to FastMCP's public async API.

    ``tool_names()`` reads a private registry for a sync answer. If that moves,
    this goes red — rather than every grant silently becoming empty.
    """
    import tinyassets.universe_agent_server as server

    assert set(server.tool_names()) == {
        tool.name for tool in asyncio.run(server.mcp.list_tools())
    }


def test_every_granted_name_is_a_real_tool(universe):
    """A grant that matches no tool grants nothing, silently."""
    assert _granted_names(universe) <= set(_engine_tool_names())


def test_the_agents_file_tools_are_granted(universe):
    """Editing its own project folder is the point; do not strip it by typo."""
    assert {
        "workspace_read",
        "workspace_write",
        "workspace_list",
        "workspace_delete",
    } <= _granted_names(universe)


def test_cannot_answer_its_own_approval(universe):
    """With nothing pending from an earlier turn, the yes-recording tool is gone."""
    assert _TOOL_REQUIRES_PENDING_APPROVAL not in _granted_names(universe)


def test_can_record_an_answer_to_an_earlier_ask(universe):
    """A pending ask means the founder is replying — recording it is legitimate."""
    _store().request(universe_id=UNIVERSE, action_key="branch.run:demo")
    assert _TOOL_REQUIRES_PENDING_APPROVAL in _granted_names(universe)


def test_only_the_approval_tool_is_ever_withheld(universe):
    """A turn creates the automations it then runs; narrowing more breaks that."""
    withheld = set(_engine_tool_names()) - _granted_names(universe)
    assert withheld == {_TOOL_REQUIRES_PENDING_APPROVAL}


def test_withholds_when_the_store_cannot_be_read(universe, monkeypatch):
    """Fails closed: an unreadable store must not hand out the grant tool.

    Breaks the store for real rather than stubbing the function under test —
    stubbing it would only assert that the stub returns what it was told to.
    """
    _store().request(universe_id=UNIVERSE, action_key="branch.run:demo")
    assert _TOOL_REQUIRES_PENDING_APPROVAL in _granted_names(universe), (
        "precondition: the tool IS granted while the store is readable"
    )

    import tinyassets.storage.action_approvals as approvals

    def explode(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(approvals.ActionApprovalStore, "pending_for", explode)
    assert _TOOL_REQUIRES_PENDING_APPROVAL not in _granted_names(universe)


def test_finish_tool_is_available():
    """The explicit completion signal must exist to be callable."""
    assert "finish" in _engine_tool_names()


def test_no_pending_brief_when_nothing_is_waiting(universe):
    """Silence when there is nothing to answer — no phantom question."""
    from tinyassets.universe_intelligence import _pending_approval_brief

    assert _pending_approval_brief(UNIVERSE) == ""


def test_pending_brief_carries_the_key_and_what_it_was_for(universe):
    """A turn has no memory of the previous one, so the record supplies it.

    Without this the founder's "yes" met "I don't have context for what you're
    approving" — them answering a question the agent could no longer see.
    """
    from tinyassets.universe_intelligence import _pending_approval_brief

    _store().request(
        universe_id=UNIVERSE,
        action_key="scheduled_work.run_now:work_123",
        detail="scheduled_work.run_now on work_123",
    )
    brief = _pending_approval_brief(UNIVERSE)
    assert "scheduled_work.run_now:work_123" in brief, "the exact key to record"
    assert "work_123" in brief, "what it was for"
    assert "record_approval" in brief, "how to answer it"


def test_pending_brief_is_scoped_to_this_universe(universe):
    """Another universe's pending ask must never appear in this one's prompt."""
    from tinyassets.universe_intelligence import _pending_approval_brief

    _store().request(universe_id="u-somebody-else", action_key="branch.run:theirs")
    assert _pending_approval_brief(UNIVERSE) == ""


def test_pending_brief_carries_the_planned_inputs(universe):
    """The founder must not be asked twice for a value they already gave.

    A turn cannot see the message that supplied the inputs, so a founder who
    provided a brief and then said "yes" was asked for the brief again and the
    run blocked on it. The pending record carries them forward.
    """
    from tinyassets.universe_intelligence import _pending_approval_brief

    _store().request(
        universe_id=UNIVERSE,
        action_key="branch.run:abc123",
        detail='branch.run on abc123 with inputs {"brief": "shipped the agent"}',
    )
    brief = _pending_approval_brief(UNIVERSE)
    assert "shipped the agent" in brief, "the planned inputs must survive the turn"
    assert "reuse them exactly" in brief, "and it must be told to reuse them"
