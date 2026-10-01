"""``owner_unread``: how many of the owner's messages the universe has not read.

Founder, 2026-10-01: the background self should have an indicator of how many
messages were sent since it looked last. Driven through the real conversation
store, the real served ``read_graph`` handler and the real middleware stack
(``mcp.call_tool``); the substitutes are the serving-admission query
(``mock_engine_admission``) and ``require_founder_home``'s home lookup, both
tested where they live.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tests.engine_authority_helpers import mock_engine_admission
from tinyassets import conversation_store as store
from tinyassets.conversation_unread import (
    UNREAD_EPOCH,
    delivered_ids,
    mark_delivered,
    owner_unread,
)

ALICE = "acct_alice"
BOB = "acct_bob"
UNIVERSE = "u-alice"
BOB_UNIVERSE = "u-bob"


def _session(actor: str) -> str:
    return f"principal:{actor}"


@pytest.fixture
def base(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    (tmp_path / UNIVERSE).mkdir()
    (tmp_path / BOB_UNIVERSE).mkdir()
    return tmp_path


def _say(base: Path, actor: str, text: str, *, universe: str = UNIVERSE,
         ts: float | None = None) -> int:
    """The owner's message and the universe's reply; returns the owner row's id."""
    assert store.record_exchange(base / universe, _session(actor), text, "reply", ts=ts)
    return _owner_ids(base, actor, universe=universe)[-1]


def _owner_ids(base: Path, actor: str, *, universe: str = UNIVERSE) -> list[int]:
    import sqlite3

    with sqlite3.connect(base / universe / ".conversation_memory.db") as conn:
        return [row[0] for row in conn.execute(
            "SELECT id FROM conversation_turns WHERE session_id = ? AND speaker = 'founder' "
            "ORDER BY id", (_session(actor),),
        )]


def _unread(base: Path, actor: str = ALICE, *, universe: str = UNIVERSE) -> int | None:
    return owner_unread(base / universe, _session(actor))


@pytest.fixture
def engine(base: Path, monkeypatch):
    """The served engine server pinned to Alice's universe."""
    import tinyassets.shared_self as shared_self
    from tinyassets import engine_mcp_server as s

    def pin(actor: str, universe: str):
        monkeypatch.setattr(s, "_ACTOR_ID", actor)
        monkeypatch.setattr(s, "_GRAPH_ID", universe)
        mock_engine_admission(monkeypatch, {universe})

    def home(base_path, universe_id, principal_id):
        if (principal_id, universe_id) not in {(ALICE, UNIVERSE), (BOB, BOB_UNIVERSE)}:
            raise PermissionError("shared_self_requires_current_founder")
        return Path(base_path) / universe_id

    monkeypatch.setattr(shared_self, "require_founder_home", home)
    pin(ALICE, UNIVERSE)
    s.pin = pin
    return s


def _read(engine, **kw) -> dict:
    return json.loads(engine.read_graph(target="conversation", **kw))["content"]


# -- the count ----------------------------------------------------------------


def test_the_count_is_the_owners_messages_in_the_owners_own_thread(base: Path) -> None:
    assert _unread(base) == 0  # no conversation yet: nothing was sent
    _say(base, ALICE, "one")
    assert _unread(base) == 1  # the universe's reply is not a message to it
    _say(base, ALICE, "two")
    assert _unread(base) == 2

    # Bob's thread in Alice's universe, and Bob's own universe, are never hers.
    _say(base, BOB, "bob in alice's store")
    _say(base, BOB, "bob at home", universe=BOB_UNIVERSE)
    assert _unread(base) == 2
    assert _unread(base, BOB) == 1
    assert _unread(base, BOB, universe=BOB_UNIVERSE) == 1
    assert _unread(base, ALICE, universe=BOB_UNIVERSE) == 0


def test_history_from_before_the_counter_is_not_news(base: Path) -> None:
    _say(base, ALICE, "last month", ts=UNREAD_EPOCH - 1)
    assert _unread(base) == 0
    _say(base, ALICE, "today")
    assert _unread(base) == 1


# -- what marks a message read -------------------------------------------------


def test_a_catalogue_page_delivers_no_text_and_marks_nothing(base: Path, engine) -> None:
    _say(base, ALICE, "one")
    _say(base, ALICE, "two")
    page = _read(engine)
    assert len(page["messages"]) == 4
    assert _unread(base) == 2


def test_reading_the_newest_message_leaves_the_older_one_unread(base: Path, engine) -> None:
    older = _say(base, ALICE, "older")
    newest = _say(base, ALICE, "newest")
    assert _read(engine, field_name=str(newest))["chunk"] == "newest"
    assert _unread(base) == 1
    assert _read(engine, field_name=str(older))["chunk"] == "older"
    assert _unread(base) == 0


def test_a_message_is_delivered_only_by_the_chunk_that_reaches_its_end(
    base: Path, engine,
) -> None:
    message = _say(base, ALICE, "abcdefghij")
    first = _read(engine, field_name=str(message), output_max_chars=4)
    assert first["chunk"] == "abcd" and first["next_offset"] == 4
    assert _unread(base) == 1
    _read(engine, field_name=str(message), output_offset=4, output_max_chars=32)
    assert _unread(base) == 0


def test_a_message_arriving_during_the_read_stays_unread(base: Path, engine, monkeypatch) -> None:
    """Only what the returned payload carried is marked: never "everything so far"."""
    import tinyassets.conversation_retrieval as retrieval

    read = _say(base, ALICE, "read me")
    real = retrieval.read_conversation_page

    def read_while_the_owner_types(*args, **kwargs):
        payload = real(*args, **kwargs)
        _say(base, ALICE, "sent while you were reading")
        return payload

    monkeypatch.setattr(retrieval, "read_conversation_page", read_while_the_owner_types)
    assert _read(engine, field_name=str(read))["chunk"] == "read me"
    assert _unread(base) == 1
    monkeypatch.setattr(retrieval, "read_conversation_page", real)
    [_, arrived] = _owner_ids(base, ALICE)
    assert _read(engine, field_name=str(arrived))["chunk"] == "sent while you were reading"
    assert _unread(base) == 0


def test_a_read_cannot_mark_another_threads_message(base: Path) -> None:
    bobs = _say(base, BOB, "bob's own words")
    _say(base, ALICE, "alice")
    mark_delivered(base / UNIVERSE, _session(ALICE), [bobs])
    assert _unread(base, BOB) == 1
    assert _unread(base) == 1


def test_the_universes_own_reply_is_never_a_delivered_owner_message() -> None:
    reply = {"field_name": "7", "speaker": "universe", "chunk": "x", "next_offset": None}
    assert delivered_ids(reply) == []
    assert delivered_ids({**reply, "speaker": "founder"}) == [7]
    assert delivered_ids({"messages": [{"id": 7, "speaker": "founder"}]}) == []


def test_compaction_keeps_the_count_exact(base: Path, engine) -> None:
    ids = [_say(base, ALICE, f"m{i}") for i in range(5)]
    for message in (ids[0], ids[1], ids[3]):
        _read(engine, field_name=str(message))
    assert _unread(base) == 2
    _read(engine, field_name=str(ids[2]))
    _read(engine, field_name=str(ids[4]))
    assert _unread(base) == 0
    _say(base, ALICE, "after compaction")
    assert _unread(base) == 1


# -- the field on served results -----------------------------------------------


def _call(engine, tool: str, args: dict):
    return asyncio.run(engine.mcp.call_tool(tool, args))


def test_every_json_result_carries_the_count(base: Path, engine, monkeypatch) -> None:
    import tinyassets.universe_server as us

    monkeypatch.setattr(us, "read_graph", lambda **kw: json.dumps({"graph": "g"}))
    first = _call(engine, "read_graph", {"target": "graph"})
    assert json.loads(first.content[0].text) == {"owner_unread": 0, "graph": "g"}

    message = _say(base, ALICE, "are you there?")
    assert json.loads(
        _call(engine, "read_graph", {"target": "graph"}).content[0].text
    )["owner_unread"] == 1

    # The read that delivers it reports the count AFTER that read.
    read = _call(engine, "read_graph", {"target": "conversation", "field_name": str(message)})
    assert json.loads(read.content[0].text)["owner_unread"] == 0


def test_a_refusal_carries_the_count_too(base: Path, engine) -> None:
    from fastmcp.exceptions import ToolError

    _say(base, ALICE, "hello")
    with pytest.raises(ToolError) as refused:
        _call(engine, "read_graph", {"target": "no-such-target"})
    document = json.loads(str(refused.value))
    assert document["owner_unread"] == 1 and document["error"]


def test_another_users_engine_sees_only_its_own_count(base: Path, engine, monkeypatch) -> None:
    import tinyassets.universe_server as us

    monkeypatch.setattr(us, "read_graph", lambda **kw: json.dumps({"graph": "g"}))
    _say(base, ALICE, "private to alice")
    _say(base, ALICE, "also hers")
    _say(base, BOB, "a visitor's message in alice's store")
    engine.pin(BOB, BOB_UNIVERSE)
    result = json.loads(_call(engine, "read_graph", {"target": "graph"}).content[0].text)
    assert result["owner_unread"] == 0


def test_no_count_without_current_serving_authority(base: Path, engine, monkeypatch) -> None:
    import tinyassets.universe_server as us

    monkeypatch.setattr(us, "read_graph", lambda **kw: json.dumps({"graph": "g"}))
    _say(base, ALICE, "hello")
    mock_engine_admission(monkeypatch, set())
    with pytest.raises(Exception) as refused:
        _call(engine, "read_graph", {"target": "graph"})
    assert "owner_unread" not in str(refused.value)
