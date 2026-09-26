"""Long-form served-agent guidance is REACHABLE, not resident — and nothing was lost.

Measured 2026-09-25 (`tests/test_converse_turn_cost.py`): the engine
tool-definition block is re-sent on every model round-trip of every served
founder turn, it was 63,383 B, and `write_graph`'s manual was 38,513 chars of it
— 61% of the block for one handle. Production confirmed the loop shape on
2026-09-26 UTC: two recall turns on the free universe ran 3 rounds each.

So the manual moved into handbook chapters served by
``read_graph target="handbook"``. These tests hold the two halves of that claim
together: the description really got smaller, AND not one line of guidance is
gone — pinned against a digest taken before the split.

Change: `openspec/changes/engine-tool-manual-on-demand/`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from tinyassets import engine_mcp_server as engine
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS

#: The digest of `write_graph`'s guidance BEFORE the 2026-09-26 split, over the
#: normalised form (each line stripped, trailing blanks dropped) because leading
#: indentation is presentation and the relocation legitimately changes it — the
#: chapters keep their original indent while the shorter description now dedents.
#: Taken from `git show <pre-split>:tinyassets/engine_mcp_server.py`.
GUIDANCE_BEFORE_SPLIT_SHA256 = (
    "d3ce3eba699692c263ab1d7731d90ba5d2a5a4850b9e1c66ac645cace5ca3fa9"
)
GUIDANCE_BEFORE_SPLIT_LINES = 622

#: How to put the chapters back where they were: the resident index sits exactly
#: where they used to start, and the tail resumes at this line. This pair IS the
#: documented reconstruction order — the test is the place that records it.
INDEX_ANCHOR = "THE HANDBOOK."
TAIL_ANCHOR = "A branch is a stored graph SHAPE"

#: Chapter order as the resident index names them.
CHAPTER_ORDER = ("connections", "code_nodes", "workspaces")


def _normalized(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines()).rstrip("\n")


def _description(handle: str) -> str:
    async def _read() -> str:
        for tool in await engine.mcp.list_tools():
            if tool.name == handle:
                return tool.description or ""
        raise AssertionError(f"no served handle named {handle!r}")

    return asyncio.run(_read())


# ---------------------------------------------------------------------------
# Nothing was lost
# ---------------------------------------------------------------------------


def test_putting_the_chapters_back_reproduces_the_original_guidance():
    """The whole safety claim in one assertion: relocation, not deletion."""
    description = _description("write_graph")
    at = description.index(INDEX_ANCHOR)
    head, rest = description[:at], description[at:]
    tail = TAIL_ANCHOR + rest.split(TAIL_ANCHOR, 1)[1]
    chapters = engine.SERVED_TOOL_CHAPTERS["write_graph"]
    recomposed = head + "".join(chapters[name] for name in CHAPTER_ORDER) + tail
    normalized = _normalized(recomposed)
    assert len(normalized.splitlines()) == GUIDANCE_BEFORE_SPLIT_LINES
    assert hashlib.sha256(normalized.encode()).hexdigest() == GUIDANCE_BEFORE_SPLIT_SHA256


def test_served_tool_guidance_answers_for_every_served_handle():
    """One call answers "is the agent told this?" — for all 14, not just the split one."""
    for handle in SERVED_ENGINE_MCP_TOOLS:
        guidance = engine.served_tool_guidance(handle)
        assert _description(handle) in guidance
    with_chapters = engine.served_tool_guidance("write_graph")
    for name in CHAPTER_ORDER:
        assert engine.SERVED_TOOL_CHAPTERS["write_graph"][name] in with_chapters


def test_an_unknown_handle_raises_instead_of_returning_empty():
    """A silent "" would let a test assert reachability for a name that is absent."""
    with pytest.raises(KeyError, match="no served handle"):
        engine.served_tool_guidance("write_graphh")


# ---------------------------------------------------------------------------
# The description really got smaller, and the split is a partition
# ---------------------------------------------------------------------------


def test_moved_chapters_are_gone_from_the_per_round_description():
    """The saving is real: chapter text is not also resident."""
    description = _description("write_graph")
    chapters = engine.SERVED_TOOL_CHAPTERS["write_graph"]
    for name, text in chapters.items():
        # Compare on a distinctive interior line, so this cannot pass merely
        # because indentation differs.
        probe = max(
            (line.strip() for line in text.splitlines()), key=len,
        )
        assert len(probe) > 40
        assert probe not in description, f"{name} is still resident"
    assert len(description) < 12_000, len(description)


def test_the_resident_index_names_every_chapter_and_how_to_fetch_it():
    """A chapter the description does not point at is a chapter nobody fetches."""
    description = _description("write_graph")
    assert INDEX_ANCHOR in description
    for name in engine.SERVED_TOOL_CHAPTERS["write_graph"]:
        assert name in description
    assert 'read_graph target="handbook"' in description


def test_guidance_that_prevents_a_wrong_first_call_stays_resident():
    """The split rule, asserted: absence must cost a fetch, never a bad call."""
    description = _description("write_graph")
    # The manifest key shape: a wrong key is only refused AFTER the attempt.
    assert "io_manifest" in description
    assert "file_bundle" in description
    # The operation catalogue and the no-effect guarantee.
    assert 'operation="create"' in description
    assert "fires NO effect" in description or "NO effect" in description
    # Parameter documentation.
    assert "Args:" in description


# ---------------------------------------------------------------------------
# The handbook read contract
# ---------------------------------------------------------------------------


def test_the_index_lists_every_chapter_that_exists():
    payload = json.loads(engine._handbook_read(""))
    assert payload["handbook"] == {
        handle: sorted(chapters)
        for handle, chapters in engine.SERVED_TOOL_CHAPTERS.items()
    }
    assert 'query="<handle>.<chapter>"' in payload["read_one"]


def test_a_chapter_comes_back_verbatim_and_untruncated():
    for name in CHAPTER_ORDER:
        payload = json.loads(engine._handbook_read(f"write_graph.{name}"))
        assert payload["handle"] == "write_graph"
        assert payload["chapter"] == name
        assert payload["text"] == engine.SERVED_TOOL_CHAPTERS["write_graph"][name]


def test_an_unknown_name_is_refused_and_names_what_is_available():
    unknown_handle = json.loads(engine._handbook_read("read_graph.connections"))
    assert "no handbook for 'read_graph'" in unknown_handle["error"]
    assert "write_graph" in unknown_handle["handbook"]
    unknown_chapter = json.loads(engine._handbook_read("write_graph.secrets"))
    assert "no chapter 'secrets'" in unknown_chapter["error"]
    assert sorted(CHAPTER_ORDER) == unknown_chapter["chapters"]


def test_the_handbook_carries_no_universe_state_and_no_secret():
    """Static text: it cannot leak, and there is nothing to write."""
    for query in ("", "write_graph.connections", "write_graph.code_nodes"):
        payload = engine._handbook_read(query)
        assert "vault://" not in payload
        assert "Bearer " not in payload
    assert "handbook" in engine._PINNED_READ_TARGETS
    # Read-only by construction: the write handle has no handbook target, so the
    # refusal names the targets it does support rather than writing anything.
    answer = engine.write_graph(target="handbook", operation="create")
    assert json.loads(answer)["error"]
    for text in engine.SERVED_TOOL_CHAPTERS["write_graph"].values():
        probe = max((line.strip() for line in text.splitlines()), key=len)
        assert probe not in answer


# ---------------------------------------------------------------------------
# One path for every account, and the public surface is untouched
# ---------------------------------------------------------------------------


def test_the_resident_block_does_not_vary_by_anything():
    """Founder rule: all accounts behave the same. Assembly reads no context."""
    first = [_description(name) for name in SERVED_ENGINE_MCP_TOOLS]
    second = [_description(name) for name in SERVED_ENGINE_MCP_TOOLS]
    assert first == second
    assert engine._handbook_read("") == engine._handbook_read("")


def test_the_public_connector_description_is_untouched_and_uncoupled():
    """Chatbot clients read the public surface; an engine split must not reach it."""
    from tinyassets import universe_server

    public = universe_server.write_graph.__doc__ or ""
    served = engine.write_graph.__doc__ or ""
    # Independent docstrings on independent functions, not derived from each other.
    assert public != served
    assert INDEX_ANCHOR not in public
    assert "handbook" not in public
    # The public manual is still whole: it never carried the engine's chapters,
    # and the relocation did not shrink it (measured 16,623 chars on 2026-09-25).
    assert len(public) > 16_000
