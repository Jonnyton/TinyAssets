"""A naive model's first `write_graph target=branch operation=create` must land.

LIVE EVIDENCE (2026-09-30T01:07Z, prod, free account
``u-01ky3zh1arr8qth8jee7zx63pq``, turn ``c7d6279d4af74d798375d3f13780140e``,
model ``nvidia/nemotron-3-ultra-550b-a55b:free``). The user asked, naively:
*"can you set something up that runs on its own every morning? like a short note
of what i should focus on today"*. The universe spent **16 of 21 rounds** failing
branch create and never produced a branch or an automation.

Every payload in this module is one of those rounds, replayed verbatim. The
contract asserted is the one the live loop needed and did not get: the first
reasonable attempt succeeds, and where it cannot, the error names the exact
field to change.

The rounds, and what each one was told:

* rounds 5-9, 12 -- ``{"error": "payload_json must be valid JSON."}`` with no
  decoder message, line, column or excerpt. The model's ``prompt_template``
  carried ``\\n`` escapes and an emoji; it could not see which.
* round 13 -- a spec whose one node HAD ``node_id`` was told "node spec missing
  node_id or display_name" (``display_name`` was the missing one), plus a FALSE
  cascade "Branch must have at least one node." for a spec that supplied one.
  The only suggestion was "Review this error and reshape the spec."
* round 17 -- the ``node_defs`` + ``graph_nodes`` shape the previous suggestion
  ("Add at least one node_def + graph_node entry") invited. The staging code
  never reads ``spec["graph_nodes"]``, so that advertisement was for a shape the
  validator does not accept.
* round 18 -- ``display_name`` added, and now "Entry point is required when
  branch has nodes." for a SINGLE node, whose entry point is inferable.
* round 19 -- ``entry_point`` set, no edges, and "Nodes in cycle without exit
  condition: n1." A single node with no outgoing edges is not a cycle.
* round 20 -- ``edges: [{"source": "n1", "target": "END"}]`` was told "edge spec
  missing 'from' or 'to'" without naming the keys it does accept.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from tests.engine_authority_helpers import mock_engine_admission

# ---------------------------------------------------------------------------
# The live payloads, verbatim
# ---------------------------------------------------------------------------

#: rounds 5-9, 12. A `prompt_template` with a raw newline and a bare control
#: character: what an LLM emits when it writes JSON containing `\n` by hand.
ROUND_5_MALFORMED = (
    '{"name": "Morning Focus", "node_defs": [{"node_id": "n1", '
    '"prompt_template": "Write a short note\non what to focus on \x01 today"}]}'
)

#: round 13. `node_id` present, `display_name` absent.
ROUND_13_NO_DISPLAY_NAME = {
    "name": "Morning Focus",
    "node_defs": [{
        "node_id": "n1",
        "type": "prompt",
        "prompt_template": "Hello",
    }],
}

#: round 17. The `node_defs` + `graph_nodes` shape the round-13 suggestion invited.
ROUND_17_NODE_DEFS_AND_GRAPH_NODES = {
    "name": "Morning Focus",
    "node_defs": [{
        "node_id": "n1",
        "type": "prompt",
        "prompt_template": "Hello",
    }],
    "graph_nodes": [{"id": "n1", "node_def_id": "n1", "position": 0}],
}

#: round 18. `display_name` added; no `entry_point`.
ROUND_18_NO_ENTRY_POINT = {
    "name": "Morning Focus",
    "node_defs": [{
        "node_id": "n1",
        "display_name": "Morning note",
        "prompt_template": "Write a short note on what to focus on today",
    }],
}

#: round 19. `entry_point` set, one node, no edges.
ROUND_19_NO_EDGES = {
    "name": "Morning Focus",
    "entry_point": "n1",
    "node_defs": [{
        "node_id": "n1",
        "display_name": "Morning note",
        "prompt_template": "Write a short note on what to focus on today",
    }],
}

#: round 20. LangGraph's own edge vocabulary: `source`/`target`.
ROUND_20_SOURCE_TARGET_EDGES = {
    "name": "Morning Focus",
    "entry_point": "n1",
    "node_defs": [{
        "node_id": "n1",
        "display_name": "Morning note",
        "prompt_template": "Write a short note on what to focus on today",
    }],
    "edges": [{"source": "n1", "target": "END"}],
}


# ---------------------------------------------------------------------------
# Harness -- the REAL served create path, end to end into storage
# ---------------------------------------------------------------------------


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, authenticate_request):
    """`write_graph` bound to a real data dir, with the real build_branch behind it.

    Deliberately NOT a mocked `_extensions_impl`: every claim here is about what
    the validator does with a payload, so a double would assert the harness. The
    only mock is the separately integration-tested admission query.
    """
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    authenticate_request("tester")
    # Production's auth mode (WorkOS): resolve-always, so an authenticated
    # founder's coarse `write` grant carries `extensions.build_branch`. The
    # served handler rebinds `_current_identity` to `_REMIX_CAPABILITIES`, so a
    # legacy exact-scope provider would refuse a call production accepts —
    # i.e. the suite would assert the harness's auth mode, not the validator.
    from tinyassets.auth import middleware as mw

    provider = mw._get_provider()
    monkeypatch.setattr(provider, "is_auth_required", lambda: False)
    monkeypatch.setattr(provider, "resolve_always_writes", lambda: True)
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", "tester")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-morning")
    mock_engine_admission(monkeypatch, {"u-morning"})
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: True)
    yield s


def _create(served, payload) -> dict:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return json.loads(served.write_graph(
        target="branch", operation="create", payload_json=raw,
    ))


def _errors(out: dict) -> list[str]:
    """Every error string a rejection carries, whatever field it landed in."""
    if out.get("errors"):
        return [str(e) for e in out["errors"]]
    return [str(out["error"])] if out.get("error") else []


def _fixes(out: dict) -> list[str]:
    return [str(s.get("proposed_fix", "")) for s in (out.get("suggestions") or [])]


def _landed(out: dict) -> bool:
    """Did a branch actually get built? A rejection carries `status: rejected`."""
    return out.get("status") != "rejected" and not out.get("error")


# ---------------------------------------------------------------------------
# Item 1 -- a JSON parse failure names the position
# ---------------------------------------------------------------------------


def test_rounds_5_to_12_a_json_parse_error_names_line_column_and_excerpt():
    """The live refusal was six words with no position. Six rounds died on it.

    Asserted on the handler's own refusal rather than through a branch build:
    the payload never parses, so no spec exists to validate.
    """
    from tinyassets import engine_mcp_server as s

    detail = s._payload_json_error(ROUND_5_MALFORMED)
    # The decoder's own message, and where.
    assert "line" in detail and "column" in detail, detail
    # An excerpt of the offending region, so the model can see the character.
    assert "near:" in detail, detail
    # And the actual bad byte is shown (escaped -- a raw control character in a
    # tool result is not readable).
    assert "\\n" in detail or "\\x01" in detail or "\\u0001" in detail, detail


def test_the_parse_error_reaches_the_agent_through_write_graph(served):
    out = _create(served, ROUND_5_MALFORMED)
    detail = out["error"]
    assert "payload_json" in detail
    assert "line" in detail and "column" in detail, detail
    assert "near:" in detail, detail


def test_the_parse_error_excerpt_is_bounded(served):
    """A 200kB payload must not return 200kB of excerpt."""
    huge = '{"name": "' + ("x" * 50_000) + '" "description": "unclosed"}'
    out = _create(served, huge)
    assert "line" in out["error"]
    assert len(out["error"]) < 1_000, len(out["error"])


def test_a_parse_error_still_refuses(served):
    """Precision is not permissiveness: the malformed payload is still rejected."""
    assert not _landed(_create(served, ROUND_5_MALFORMED))


# ---------------------------------------------------------------------------
# Item 2 -- display_name, the false cascade, and honest suggestions
# ---------------------------------------------------------------------------


def test_round_13_display_name_defaults_to_node_id_and_the_branch_lands(served):
    """The round-13 payload was a reasonable first attempt. It must succeed.

    `display_name` is a label for a human; a node that has an id has a usable
    one. Refusing the whole build over it cost the live turn four more rounds.
    """
    out = _create(served, ROUND_13_NO_DISPLAY_NAME)
    assert _landed(out), out
    assert out.get("branch_def_id") or "Built branch" in str(out.get("text", "")), out


def test_round_13_the_built_node_carries_node_id_as_its_display_name(served):
    out = _create(served, ROUND_13_NO_DISPLAY_NAME)
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import get_branch_definition

    stored = get_branch_definition(_base_path(), branch_def_id=out["branch_def_id"])
    assert [n["display_name"] for n in stored["node_defs"]] == ["n1"]


def test_a_node_with_no_node_id_names_node_id_specifically(served):
    """The missing field is named. The live error named both and meant one."""
    out = _create(served, {
        "name": "Morning Focus",
        "node_defs": [{"display_name": "Morning note", "prompt_template": "Hello"}],
    })
    assert not _landed(out)
    joined = " ".join(_errors(out))
    assert "missing 'node_id'" in joined, joined
    # display_name may be MENTIONED -- saying it defaults is useful -- but never
    # reported as missing, which is what sent round 13 at the wrong field.
    assert "missing node_id or display_name" not in joined, joined
    assert "'display_name' is optional" in joined, joined


def test_no_false_at_least_one_node_cascade_when_nodes_were_given(served):
    """The live spec supplied a node and was told it had none.

    Two errors for one defect is how round 13 became round 17: the model
    believed its `node_defs` key was unrecognized and went looking for another
    shape.
    """
    out = _create(served, {
        "name": "Morning Focus",
        # A node that genuinely cannot be built: no id at all.
        "node_defs": [{"prompt_template": "Hello"}],
    })
    assert not _landed(out)
    joined = " ".join(_errors(out))
    assert "at least one node" not in joined.lower(), joined


def test_an_empty_nodes_list_still_says_at_least_one_node(served):
    """Round 11's answer was correct and must survive: no nodes means no nodes."""
    out = _create(served, {"name": "Morning Focus", "node_defs": []})
    assert not _landed(out)
    assert "at least one node" in " ".join(_errors(out)).lower()


def test_no_suggestion_ever_says_to_reshape_the_spec(served):
    """"Review this error and reshape the spec" is the absence of a suggestion.

    Driven through a spec whose error takes the fallback branch, so this asserts
    the fallback itself rather than a mapped case.
    """
    out = _create(served, {
        "name": "Morning Focus",
        "entry_point": "n1",
        "node_defs": [{
            "node_id": "n1",
            "prompt_template": "Hello",
            "source_code": "def run(state, effects):\n    return {}\n",
        }],
    })
    assert not _landed(out)
    fixes = " ".join(_fixes(out))
    assert "reshape the spec" not in fixes.lower(), fixes
    # And the fallback still names concrete fields from the error it explains.
    assert "source_code" in fixes and "prompt_template" in fixes, fixes


def test_the_empty_nodes_suggestion_does_not_advertise_graph_nodes(served):
    """Round 17 followed a suggestion into a shape staging never reads.

    `_staged_branch_from_spec` reads `node_defs` / `nodes` and synthesizes the
    graph node itself; `spec["graph_nodes"]` has no reader on the create path.
    """
    out = _create(served, {"name": "Morning Focus", "node_defs": []})
    fixes = " ".join(_fixes(out))
    assert "node_defs" in fixes, fixes
    # It may only MENTION graph_nodes to say they are not passed. What it must
    # never do is instruct the caller to add one, which is what round 17 did.
    assert "do not pass graph_nodes" in fixes, fixes
    assert "add" not in fixes.lower().split("graph_node")[-1], fixes


def test_round_17_the_shape_it_was_sent_to_also_lands(served):
    """Belt and braces: the spec round 17 actually sent must not be refused.

    A suggestion no longer names `graph_nodes`, but a model that already learned
    the shape (or copied it from `read_graph target="branches"` output, which
    RETURNS `graph_nodes`) must not be punished for it.
    """
    out = _create(served, ROUND_17_NODE_DEFS_AND_GRAPH_NODES)
    assert _landed(out), out


# ---------------------------------------------------------------------------
# Item 3 -- entry_point defaults
# ---------------------------------------------------------------------------


def test_round_18_entry_point_defaults_to_the_first_node(served):
    out = _create(served, ROUND_18_NO_ENTRY_POINT)
    assert _landed(out), out
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import get_branch_definition

    stored = get_branch_definition(_base_path(), branch_def_id=out["branch_def_id"])
    assert stored["entry_point"] == "n1"


def test_the_default_entry_point_is_the_node_nothing_points_at(served):
    """Multi-node: the head of the chain, not merely index 0."""
    out = _create(served, {
        "name": "Two step",
        "node_defs": [
            {"node_id": "second", "prompt_template": "b"},
            {"node_id": "first", "prompt_template": "a"},
        ],
        "edges": [{"from": "first", "to": "second"}, {"from": "second", "to": "END"}],
    })
    assert _landed(out), out
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import get_branch_definition

    stored = get_branch_definition(_base_path(), branch_def_id=out["branch_def_id"])
    assert stored["entry_point"] == "first"


def test_an_explicit_entry_point_is_never_overridden(served):
    out = _create(served, {
        "name": "Two step",
        "entry_point": "second",
        "node_defs": [
            {"node_id": "second", "prompt_template": "b"},
            {"node_id": "first", "prompt_template": "a"},
        ],
        "edges": [{"from": "second", "to": "first"}, {"from": "first", "to": "END"}],
    })
    assert _landed(out), out
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import get_branch_definition

    stored = get_branch_definition(_base_path(), branch_def_id=out["branch_def_id"])
    assert stored["entry_point"] == "second"


def test_a_wrong_explicit_entry_point_is_still_an_error(served):
    """The default fills an ABSENCE. It must not paper over a typo."""
    out = _create(served, {
        "name": "Morning Focus",
        "entry_point": "nope",
        "node_defs": [{"node_id": "n1", "prompt_template": "Hello"}],
    })
    assert not _landed(out)
    assert "nope" in " ".join(_errors(out))


# ---------------------------------------------------------------------------
# Item 4 -- a terminal node is not a cycle
# ---------------------------------------------------------------------------


def test_round_19_one_node_with_no_edges_is_not_a_cycle(served):
    out = _create(served, ROUND_19_NO_EDGES)
    assert _landed(out), out
    assert "cycle" not in json.dumps(out).lower()


def test_a_chain_whose_last_node_has_no_outgoing_edge_is_not_a_cycle(served):
    """LangGraph semantics: a node with no outgoing edge terminates."""
    out = _create(served, {
        "name": "Two step",
        "entry_point": "first",
        "node_defs": [
            {"node_id": "first", "prompt_template": "a"},
            {"node_id": "second", "prompt_template": "b"},
        ],
        "edges": [{"from": "first", "to": "second"}],
    })
    assert _landed(out), out


def test_a_real_cycle_with_no_exit_is_still_refused(served):
    """The check earns its place: two nodes pointing at each other, no END."""
    out = _create(served, {
        "name": "Loop",
        "entry_point": "a",
        "node_defs": [
            {"node_id": "a", "prompt_template": "a"},
            {"node_id": "b", "prompt_template": "b"},
        ],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
    })
    assert not _landed(out)
    joined = " ".join(_errors(out)).lower()
    assert "cycle" in joined
    assert "a" in joined and "b" in joined


def test_a_cycle_that_can_reach_end_is_accepted(served):
    out = _create(served, {
        "name": "Loop with exit",
        "entry_point": "a",
        "node_defs": [
            {"node_id": "a", "prompt_template": "a"},
            {"node_id": "b", "prompt_template": "b"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "a"},
            {"from": "b", "to": "END"},
        ],
    })
    assert _landed(out), out


def test_a_cycle_reached_from_a_terminal_free_node_is_still_refused(served):
    """The narrowing is exact: only a node with NO outgoing edge terminates.

    `a -> b -> c -> b`: `a` terminates through nothing, but `b` and `c` are a
    genuine closed loop and must still be named.
    """
    out = _create(served, {
        "name": "Tail loop",
        "entry_point": "a",
        "node_defs": [
            {"node_id": "a", "prompt_template": "a"},
            {"node_id": "b", "prompt_template": "b"},
            {"node_id": "c", "prompt_template": "c"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
            {"from": "c", "to": "b"},
        ],
    })
    assert not _landed(out)
    joined = " ".join(_errors(out))
    assert "cycle" in joined.lower()
    assert "b" in joined and "c" in joined


# ---------------------------------------------------------------------------
# Item 5 -- source/target as aliases of from/to
# ---------------------------------------------------------------------------


def test_round_20_source_and_target_are_accepted_edge_keys(served):
    out = _create(served, ROUND_20_SOURCE_TARGET_EDGES)
    assert _landed(out), out
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import get_branch_definition

    stored = get_branch_definition(_base_path(), branch_def_id=out["branch_def_id"])
    # `source`/`target` land as the canonical stored edge, so the alias is an
    # input spelling and never a second persisted shape.
    assert stored["graph"]["edges"] == [{"from": "n1", "to": "END"}]


def test_a_conditional_edge_accepts_source_too(served):
    out = _create(served, {
        "name": "Router",
        "entry_point": "route",
        "node_defs": [
            {"node_id": "route", "prompt_template": "pick"},
            {"node_id": "left", "prompt_template": "l"},
        ],
        "conditional_edges": [{
            "source": "route",
            "conditions": {"yes": "left", "no": "END"},
        }],
        "edges": [{"source": "left", "target": "END"}],
    })
    assert _landed(out), out


def test_an_edge_missing_both_keys_names_every_accepted_spelling(served):
    out = _create(served, {
        "name": "Morning Focus",
        "entry_point": "n1",
        "node_defs": [{"node_id": "n1", "prompt_template": "Hello"}],
        "edges": [{"frm": "n1", "twoo": "END"}],
    })
    assert not _landed(out)
    joined = " ".join(_errors(out))
    for accepted in ("'from'", "'to'", "'source'", "'target'"):
        assert accepted in joined, (accepted, joined)


def test_an_edge_missing_only_its_origin_names_only_origin_keys(served):
    """Precision cuts both ways: do not send the caller at a key that IS set."""
    out = _create(served, {
        "name": "Morning Focus",
        "entry_point": "n1",
        "node_defs": [{"node_id": "n1", "prompt_template": "Hello"}],
        "edges": [{"frm": "n1", "to": "END"}],
    })
    assert not _landed(out)
    joined = " ".join(_errors(out))
    assert "'source'" in joined, joined
    assert "'target'" not in joined, joined


def test_a_conditional_edge_missing_its_source_names_both_spellings(served):
    out = _create(served, {
        "name": "Morning Focus",
        "entry_point": "n1",
        "node_defs": [{"node_id": "n1", "prompt_template": "Hello"}],
        "conditional_edges": [{"conditions": {"yes": "END"}}],
    })
    assert not _landed(out)
    joined = " ".join(_errors(out))
    assert "from" in joined and "source" in joined, joined


# ---------------------------------------------------------------------------
# Item 6 -- the handbook chapter's examples are real
# ---------------------------------------------------------------------------


def _chapter_specs() -> list[dict]:
    """Every JSON object in the `branches` chapter's `payload_json=` examples.

    Parsed out of the served text rather than duplicated here: a copy would let
    the chapter drift from the thing this test proves works.
    """
    from tinyassets import engine_mcp_server as s

    text = s.SERVED_TOOL_CHAPTERS["write_graph"]["branches"]
    specs: list[dict] = []
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth = 0
        for end in range(start, len(text)):
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        blob = json.loads(text[start:end + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(blob, dict) and blob.get("node_defs"):
                        specs.append(blob)
                    break
    return specs


def test_the_branches_chapter_exists_and_is_reachable():
    from tinyassets import engine_mcp_server as s

    payload = json.loads(s._handbook_read("write_graph.branches"))
    assert payload["chapter"] == "branches"
    assert len(payload["text"]) > 500


def test_the_branches_chapter_carries_a_one_node_and_a_two_node_example():
    specs = _chapter_specs()
    assert len(specs) >= 2, [s.get("name") for s in specs]
    sizes = {len(spec["node_defs"]) for spec in specs}
    assert 1 in sizes and 2 in sizes, sizes


def test_every_branches_chapter_example_round_trips_through_the_real_create(served):
    """The example is verified against the validator, not against my memory.

    This is the assertion item 6 asks for: each documented spec is submitted to
    the SAME served create path the agent calls, and must land.
    """
    specs = _chapter_specs()
    assert specs
    for spec in specs:
        out = _create(served, spec)
        assert _landed(out), (spec.get("name"), out)


def test_the_chapter_shows_how_to_schedule_the_branch():
    from tinyassets import engine_mcp_server as s

    text = s.SERVED_TOOL_CHAPTERS["write_graph"]["branches"]
    assert 'target="automation"' in text
    assert "cron" in text or "schedule" in text


def test_the_chapter_is_named_in_the_resident_index():
    """A chapter the description does not point at is one nobody fetches."""
    import asyncio

    from tinyassets import engine_mcp_server as s

    async def _desc():
        for tool in await s.mcp.list_tools():
            if tool.name == "write_graph":
                return tool.description or ""
        raise AssertionError("write_graph is not served")

    assert "branches" in asyncio.run(_desc())


def test_the_chapter_is_not_resident():
    """Served on demand: the text must not ride every model round-trip."""
    import asyncio

    from tinyassets import engine_mcp_server as s

    async def _desc():
        for tool in await s.mcp.list_tools():
            if tool.name == "write_graph":
                return tool.description or ""
        raise AssertionError("write_graph is not served")

    description = asyncio.run(_desc())
    chapter = s.SERVED_TOOL_CHAPTERS["write_graph"]["branches"]
    probe = max((line.strip() for line in chapter.splitlines()), key=len)
    assert len(probe) > 40
    assert probe not in description


# ---------------------------------------------------------------------------
# The whole live loop, as one assertion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,payload", [
    ("round_13", ROUND_13_NO_DISPLAY_NAME),
    ("round_17", ROUND_17_NODE_DEFS_AND_GRAPH_NODES),
    ("round_18", ROUND_18_NO_ENTRY_POINT),
    ("round_19", ROUND_19_NO_EDGES),
    ("round_20", ROUND_20_SOURCE_TARGET_EDGES),
])
def test_every_well_formed_live_round_now_lands(served, label, payload):
    """Rounds 13-20 each sent a reasonable spec. Every one of them now builds.

    Separately parametrized so a partial fix reports WHICH round still fails.
    """
    out = _create(served, payload)
    assert _landed(out), (label, out)


def test_the_first_reasonable_attempt_needs_exactly_one_round(served):
    """The shortest spec a naive model would write: name + one prompt node."""
    out = _create(served, {
        "name": "Morning Focus",
        "node_defs": [{
            "node_id": "note",
            "prompt_template": "Write a short note on what to focus on today",
        }],
    })
    assert _landed(out), out


def test_importing_the_module_twice_does_not_change_the_contract():
    """Guard against a chapter registered at import time under a reload."""
    from tinyassets import engine_mcp_server as s

    before = sorted(s.SERVED_TOOL_CHAPTERS["write_graph"])
    importlib.reload(s)
    assert sorted(s.SERVED_TOOL_CHAPTERS["write_graph"]) == before
