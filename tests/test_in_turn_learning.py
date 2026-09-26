"""A turn that records its own lesson does not pay for a second pass.

Measured 2026-09-25 (`tests/test_converse_turn_cost.py`): `converse` produced the
reply, then spent a THIRD model round-trip on learning extraction, then returned —
on the founder's clock, every turn. Production 2026-09-26 UTC on the free universe:
two recall turns at 3 rounds each, 1-2 minutes each.

The turn is now told it has not recorded what it was taught, records it in-turn with
`write_brain` inside the round-trips it is already paying for, and then the
extraction call is skipped. If it did NOT record, that call still runs synchronously
exactly as before — so no lesson is ever lost and no turn is slower than it was
(lead, 2026-09-26, overruling a first draft that deferred recording to the NEXT
turn: a founder who never sends another message would have lost the fact).

Change: `openspec/changes/deferred-learning-never-blocks-the-reply/`.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from tests import test_interactive_http_agent as integration
from tinyassets import (
    conversation_store,
    daemon_server,
    engine_tool_client,
    universe_intelligence,
)
from tinyassets.providers.api_key_http_provider import ApiKeyHttpProvider
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS

#: Captured at import, before `rig` replaces it with a raising guard.
_GET_FOUNDER_HOME = daemon_server.get_founder_home

rig = integration.rig
reader = integration.reader
served = integration.served
agent = integration.agent

SESSION = "principal:owner"
FINAL_REPLY = "Cobalt it is."


@pytest.fixture
def turn(agent, monkeypatch, signed_in):
    """The real served-turn rig, with a wire that can be told to write the brain."""
    uid = agent.served.context.universe_dir.name
    monkeypatch.setattr(daemon_server, "get_founder_home", _GET_FOUNDER_HOME)
    signed_in("owner")
    state = SimpleNamespace(
        calls=[],
        # Which tool the writer turn asks for on its first round; None = answer at once.
        tool="write_brain",
        # What the engine handle RETURNS. The default is the real success shape from
        # `engine_mcp_server.write_brain`. The rig's own stub returns plain text for
        # every tool, which is why a refused write was indistinguishable from a
        # written one until PR #4001's review proved it: a returned refusal skipped
        # the extraction and reported the lesson settled.
        tool_result=json.dumps({"ok": True, "written": {"updated_files": ["founder.md"]}}),
        tool_is_error=False,
        universe_dir=agent.served.context.universe_dir,
        uid=uid,
    )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def is_connected(self):
            return True

        async def list_tools_mcp(self, *, cursor=None):
            return ListToolsResult(tools=[
                Tool(name=name, inputSchema={"type": "object"})
                for name in SERVED_ENGINE_MCP_TOOLS
            ])

        async def call_tool_mcp(self, name, arguments):
            return CallToolResult(
                content=[TextContent(type="text", text=state.tool_result)],
                isError=state.tool_is_error,
            )

    monkeypatch.setattr(engine_tool_client, "_make_client", lambda *_: Client())

    class Proxy:
        def close(self):
            pass

        def request(self, verb, document):
            body = document["body"]
            messages = body.get("messages", [])
            system = "".join(
                str(m.get("content") or "") for m in messages if m.get("role") == "system"
            )
            learning = "now doing one narrow job" in system
            writers = sum(1 for c in state.calls if c["kind"] != "extract_learning")
            state.calls.append({
                "kind": "extract_learning" if learning else f"writer_{writers + 1}",
                "system": system,
                "at": time.perf_counter(),
            })
            if learning:
                message = {"role": "assistant", "content": "{}"}
            elif state.tool is not None and writers == 0:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": state.tool,
                            "arguments": json.dumps({"founder": "Favourite colour: cobalt."}),
                        },
                    }],
                }
            else:
                message = {"role": "assistant", "content": FINAL_REPLY}
            wants_tool = message.get("content") is None
            return {
                "status": 200,
                "body": json.dumps({
                    "model": "free-model",
                    "choices": [{
                        "message": message,
                        "finish_reason": "tool_calls" if wants_tool else "stop",
                    }],
                }),
            }

    monkeypatch.setattr(ApiKeyHttpProxy := ApiKeyHttpProvider, "_resolve_proxy",
                        lambda *a, **k: Proxy())
    return state


def _converse(turn, message="my favourite colour is cobalt", settled=None):
    return universe_intelligence.converse(
        turn.uid,
        message,
        actor_id="owner",
        input_method="typed",
        **({} if settled is None else {"learning_observer": settled.append}),
    )


def _kinds(turn):
    return [call["kind"] for call in turn.calls]


# ---------------------------------------------------------------------------
# The turn is told, and recording skips the extra round-trip
# ---------------------------------------------------------------------------


def test_the_turn_is_told_it_has_not_recorded_the_lesson(turn):
    """No extra model round-trip is spent telling it — it rides on the prompt."""
    _converse(turn)
    first = turn.calls[0]
    assert first["kind"] == "writer_1"
    assert "NOT YET RECORDED" in first["system"]
    assert "write_brain" in first["system"]
    # It must not read as an instruction to invent something to save.
    assert "I write NOTHING and simply answer" in first["system"]


def test_recording_in_turn_skips_the_extraction_round_trip(turn):
    """The whole deliverable: two round-trips instead of three."""
    settled: list[bool] = []
    assert _converse(turn, settled=settled) == FINAL_REPLY
    assert _kinds(turn) == ["writer_1", "writer_2"]
    assert "extract_learning" not in _kinds(turn)
    assert settled == [True]


def test_a_turn_that_records_nothing_keeps_the_guaranteed_pass(turn):
    """No lesson is ever lost: the synchronous call still runs, as before."""
    turn.tool = None  # answers at once, writes no brain
    settled: list[bool] = []
    assert _converse(turn, settled=settled) == FINAL_REPLY
    assert _kinds(turn) == ["writer_1", "extract_learning"]
    assert settled == [True]  # extraction ran and found nothing durable


def test_a_refused_write_brain_is_not_evidence_and_still_extracts(turn):
    """PR #4001 blocking review, probe 1: the refusal the handler RETURNS.

    Every refusal in `write_brain` -- no binding, a size cap, a name cap, nothing to
    write, an admission refusal, `commit_learning` returning None -- is a returned
    error JSON, not a raise, and the journal marks any returned result "completed".
    At the reviewed head this skipped the extraction and reported settled=True, so
    the lesson was recorded NOWHERE and nothing would retry it.
    """
    turn.tool_result = json.dumps({
        "error": ("nothing was persisted — the edit was empty, ungrounded, or "
                  "rejected (e.g. a section that is not governed-editable)."),
    })
    settled: list[bool] = []
    assert _converse(turn, settled=settled) == FINAL_REPLY
    assert _kinds(turn) == ["writer_1", "writer_2", "extract_learning"]
    assert settled == [True]  # settled by the EXTRACTION, not by the refused write


def test_an_is_error_write_brain_is_not_evidence_either(turn):
    """Probe 2: the same text with isError set. Also 'completed' in the journal."""
    turn.tool_result = json.dumps({"error": "engine MCP is not bound to a founder"})
    turn.tool_is_error = True
    settled: list[bool] = []
    assert _converse(turn, settled=settled) == FINAL_REPLY
    assert _kinds(turn) == ["writer_1", "writer_2", "extract_learning"]


@pytest.mark.parametrize("result", [
    '{"ok": true}',                       # no `written` at all
    '{"ok": true, "written": {}}',         # an EMPTY written
    '{"ok": true, "written": []}',
    '{"written": {"updated_files": ["founder.md"]}}',   # no `ok`
    '{"ok": "true", "written": {"updated_files": ["x"]}}',  # a STRING, not true
    'not json at all',
    '',
])
def test_only_the_handlers_exact_success_shape_counts(turn, result):
    """Anything short of the success shape leaves the lesson owed."""
    turn.tool_result = result
    assert _converse(turn) == FINAL_REPLY
    assert "extract_learning" in _kinds(turn)


def test_a_real_written_result_is_evidence(turn):
    """The other half: the shape the handler actually returns DOES skip the pass."""
    turn.tool_result = json.dumps({"ok": True, "written": {"updated_files": ["founder.md"]}})
    settled: list[bool] = []
    assert _converse(turn, settled=settled) == FINAL_REPLY
    assert _kinds(turn) == ["writer_1", "writer_2"]
    assert settled == [True]


def test_an_unrelated_tool_is_not_evidence_of_recording(turn):
    """Only the governed brain-write counts. read_brain is not a write."""
    turn.tool = "read_brain"
    settled: list[bool] = []
    assert _converse(turn, settled=settled) == FINAL_REPLY
    assert _kinds(turn) == ["writer_1", "writer_2", "extract_learning"]
    assert settled == [True]


def test_a_failed_extraction_leaves_the_lesson_owed(turn, monkeypatch):
    """Unsettled is the retry state; it must never report settled."""
    turn.tool = None

    def explode(*_args, **_kwargs):
        raise RuntimeError("synthetic extractor failure")

    monkeypatch.setattr(universe_intelligence, "extract_learning", explode)
    settled: list[bool] = []
    assert _converse(turn, settled=settled) == FINAL_REPLY
    assert settled == [False]


def test_the_reply_survives_a_broken_observer(turn):
    """The reply is already earned when the outcome is reported."""
    def explode(_settled):
        raise RuntimeError("synthetic observer failure")

    reply = universe_intelligence.converse(
        turn.uid, "hello", actor_id="owner", input_method="typed",
        learning_observer=explode,
    )
    assert reply == FINAL_REPLY


# ---------------------------------------------------------------------------
# The cursor: what is owed, and what settling means
# ---------------------------------------------------------------------------


def test_the_cursor_starts_owing_nothing_and_advances_only_on_settle(turn):
    universe_dir = turn.universe_dir
    assert conversation_store.learned_cursor(universe_dir, SESSION) == 0
    conversation_store.record_exchange(universe_dir, SESSION, "taught you a thing", "noted")
    latest = conversation_store.latest_turn_no(universe_dir, SESSION)
    assert latest > 0
    # Owed: turns exist past the cursor.
    assert latest > conversation_store.learned_cursor(universe_dir, SESSION)
    assert conversation_store.settle_learned_cursor(universe_dir, SESSION) == latest
    assert conversation_store.learned_cursor(universe_dir, SESSION) == latest


def test_settling_is_monotonic_and_idempotent(turn):
    universe_dir = turn.universe_dir
    conversation_store.record_exchange(universe_dir, SESSION, "one", "ok")
    conversation_store.record_exchange(universe_dir, SESSION, "two", "ok")
    latest = conversation_store.latest_turn_no(universe_dir, SESSION)
    conversation_store.settle_learned_cursor(universe_dir, SESSION)
    # A second settle for an EARLIER span cannot un-settle the later one.
    assert conversation_store.settle_learned_cursor(
        universe_dir, SESSION, through_turn=1,
    ) == latest
    assert conversation_store.learned_cursor(universe_dir, SESSION) == latest


def test_the_cursor_cannot_jump_past_a_turn_that_is_still_owed(turn):
    """PR #4001 review: a watermark cannot say "N settled, N-1 not".

    Turn N-1's extraction failed, so the cursor stayed behind. Turn N then settles.
    Advancing to the latest row would claim N-1 too, and no drain would ever retry
    it. Refusing costs a redundant extraction later; claiming costs the lesson.
    """
    universe_dir = turn.universe_dir
    conversation_store.record_exchange(universe_dir, SESSION, "taught you X", "noted")
    owed_at = conversation_store.latest_turn_no(universe_dir, SESSION)
    # Turn N-1 is owed: nothing settled it.
    assert conversation_store.learned_cursor(universe_dir, SESSION) == 0
    conversation_store.record_exchange(universe_dir, SESSION, "taught you Y", "noted")
    began_at = owed_at  # where the cursor SHOULD have stood when turn N began
    settled = conversation_store.settle_learned_cursor(
        universe_dir, SESSION, from_turn=began_at,
    )
    assert settled == 0, "turn N claimed the owed turn N-1"
    assert conversation_store.learned_cursor(universe_dir, SESSION) == 0
    # And once the earlier span IS settled, the next one advances normally.
    assert conversation_store.settle_learned_cursor(
        universe_dir, SESSION, through_turn=owed_at, from_turn=0,
    ) == owed_at
    latest = conversation_store.latest_turn_no(universe_dir, SESSION)
    assert conversation_store.settle_learned_cursor(
        universe_dir, SESSION, from_turn=owed_at,
    ) == latest


def test_an_existing_conversation_is_not_re_extracted(turn):
    """Starting the cursor at the latest turn: months of history is not a spend surprise."""
    universe_dir = turn.universe_dir
    for _ in range(3):
        conversation_store.record_exchange(universe_dir, SESSION, "old turn", "old reply")
    latest = conversation_store.latest_turn_no(universe_dir, SESSION)
    assert conversation_store.start_learned_cursor(universe_dir, SESSION) == latest
    assert conversation_store.learned_cursor(universe_dir, SESSION) == latest
    # Called again it is a no-op: a session that already has a cursor is untouched.
    conversation_store.record_exchange(universe_dir, SESSION, "new turn", "new reply")
    assert conversation_store.start_learned_cursor(universe_dir, SESSION) == 0
    assert conversation_store.learned_cursor(universe_dir, SESSION) == latest


def test_an_unreadable_cursor_costs_an_extraction_not_a_lesson(turn, monkeypatch):
    """Fail toward the OLD behaviour, never toward claiming a lesson was learned."""
    universe_dir = turn.universe_dir

    def explode(*_args, **_kwargs):
        raise sqlite_error()

    def sqlite_error():
        import sqlite3

        return sqlite3.OperationalError("synthetic store failure")

    monkeypatch.setattr(conversation_store, "_connect", explode)
    assert conversation_store.learned_cursor(universe_dir, SESSION) == 0
    assert conversation_store.latest_turn_no(universe_dir, SESSION) == 0
    assert conversation_store.settle_learned_cursor(universe_dir, SESSION) == 0


# ---------------------------------------------------------------------------
# One path for every account
# ---------------------------------------------------------------------------


def test_the_prompt_block_does_not_vary_by_anything(turn):
    """Founder rule: all accounts behave the same. The block is a constant."""
    first = universe_intelligence._UNRECORDED_LESSON
    _converse(turn)
    told = [c["system"] for c in turn.calls if c["kind"].startswith("writer")]
    assert all(first in system for system in told)
    for banned in ("plan", "tier", "free", "paid", "premium"):
        assert banned not in first.lower()
