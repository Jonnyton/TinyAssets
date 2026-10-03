"""``owner_unread`` on served engine results, through the real middleware stack.

Driven through ``mcp.call_tool`` (every middleware included), the real served
``read_graph`` conversation handler and the real conversation store. The
substitutes are the serving-admission query (``mock_engine_admission``) and the
founder-home lookup, both tested where they live.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tests.engine_authority_helpers import mock_engine_admission
from tinyassets import conversation_store as store

ALICE = "acct_alice"
BOB = "acct_bob"
UNIVERSE = "u-alice"
BOB_UNIVERSE = "u-bob"


@pytest.fixture
def base(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    (tmp_path / UNIVERSE).mkdir()
    (tmp_path / BOB_UNIVERSE).mkdir()
    return tmp_path


@pytest.fixture
def engine(base: Path, monkeypatch):
    import tinyassets.shared_self as shared_self
    import tinyassets.universe_server as us
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
    monkeypatch.setattr(us, "read_graph", lambda **kw: json.dumps({"graph": "g"}))
    pin(ALICE, UNIVERSE)
    s.pin = pin
    return s


def say(base: Path, actor: str, text: str, universe: str = UNIVERSE) -> int:
    import sqlite3
    from contextlib import closing

    session = f"principal:{actor}"
    assert store.record_exchange(base / universe, session, text, "reply")
    with closing(sqlite3.connect(base / universe / ".conversation_memory.db")) as conn:
        return conn.execute(
            "SELECT max(id) FROM conversation_turns WHERE session_id=? AND speaker='founder'",
            (session,),
        ).fetchone()[0]


def call(engine, tool: str, args: dict) -> dict:
    result = asyncio.run(engine.mcp.call_tool(tool, args))
    assert len(result.content) == 1, "one result is one block; a second breaks node callers"
    return json.loads(result.content[0].text)


def graph(engine) -> dict:
    return call(engine, "read_graph", {"target": "graph"})


def read(engine, message: int, **kw) -> dict:
    return call(engine, "read_graph", {"target": "conversation", "field_name": str(message), **kw})


def test_every_json_result_carries_one_generic_field(base: Path, engine) -> None:
    assert graph(engine) == {"owner_unread": 0, "graph": "g"}
    say(base, ALICE, "are you there?")
    assert graph(engine)["owner_unread"] == 1


def test_only_a_fully_returned_message_is_read(base: Path, engine) -> None:
    older = say(base, ALICE, "older")
    newest = say(base, ALICE, "newest text")
    assert call(engine, "read_graph", {"target": "conversation"})["owner_unread"] == 2
    partial = read(engine, newest, output_max_chars=4)
    assert partial["content"]["next_offset"] == 4 and partial["owner_unread"] == 2
    # The read that finishes it reports the count AFTER that read.
    assert read(engine, newest, output_offset=4)["owner_unread"] == 1
    assert read(engine, older)["owner_unread"] == 0


def test_a_message_arriving_during_the_read_stays_unread(base: Path, engine, monkeypatch) -> None:
    import tinyassets.conversation_retrieval as retrieval

    first = say(base, ALICE, "read me")
    real = retrieval.read_conversation_page

    def read_while_the_owner_types(*args, **kwargs):
        payload = real(*args, **kwargs)
        say(base, ALICE, "sent while you were reading")
        return payload

    monkeypatch.setattr(retrieval, "read_conversation_page", read_while_the_owner_types)
    assert read(engine, first)["owner_unread"] == 1


def test_a_refusal_carries_the_count_too(base: Path, engine) -> None:
    from fastmcp.exceptions import ToolError

    say(base, ALICE, "hello")
    with pytest.raises(ToolError) as refused:
        asyncio.run(engine.mcp.call_tool("read_graph", {"target": "no-such-target"}))
    document = json.loads(str(refused.value))
    assert document["owner_unread"] == 1 and document["error"]


def test_another_users_engine_sees_only_its_own_thread(base: Path, engine) -> None:
    say(base, ALICE, "private to alice")
    say(base, BOB, "bob's message in alice's store")
    engine.pin(BOB, BOB_UNIVERSE)
    assert graph(engine)["owner_unread"] == 0
    say(base, BOB, "bob at home", universe=BOB_UNIVERSE)
    assert graph(engine)["owner_unread"] == 1


def test_no_count_without_current_serving_authority(base: Path, engine, monkeypatch) -> None:
    say(base, ALICE, "hello")
    mock_engine_admission(monkeypatch, set())
    with pytest.raises(Exception) as refused:
        asyncio.run(engine.mcp.call_tool("read_graph", {"target": "graph"}))
    assert "owner_unread" not in str(refused.value)


def test_an_unreadable_count_is_left_off_not_zero(base: Path, engine, monkeypatch) -> None:
    import tinyassets.conversation_attention as attention

    def broken(*a, **k):
        raise OSError("disk")

    monkeypatch.setattr(attention, "unread_count", broken)
    assert graph(engine) == {"graph": "g"}
