"""Effects fire at node time (change `sandboxed-code-node`, design D1).

Live 2026-08-30, runs 6cb4d9f48a9949be / 7a7a91c14b0d4b8b: `write_readme`
was refused before the wire and `open_pr` still fired into a GitHub 422,
leaving dangling branches - because every effect fired after the whole
graph, in storage order, with no way to stop. Now a node's effects fire the
moment it returns; a refused packet fails the node and later nodes never run;
a later node reads an ancestor's FULL response, never the 4 KiB preview.
"""

from __future__ import annotations

import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from tinyassets import effectors
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.effectors import (
    EffectChain,
    EffectFailedError,
    dispatch_node_effects,
    forget_effect_chain,
    register_effect_chain,
)
from tinyassets.graph_compiler import _delta_view, _graph_ancestors, compile_branch

SINK = "authenticated_external_call"


def _packet(verb="GET", **extra):
    packet = {
        "sink": SINK, "connection_id": "c1", "grant_id": "g1", "verb": verb,
        "request": {"method": verb, "url": "https://api.example.test/x"},
    }
    packet.update(extra)
    return json.dumps(packet)


def _effect_node(node_id, verb="GET", input_keys=(), **extra):
    return NodeDefinition(
        node_id=node_id, display_name=node_id,
        prompt_template=f"packet:{node_id}",
        output_keys=[f"{node_id}_packet"],
        input_keys=list(input_keys),
        effects=[SINK],
    )


def _linear(*nodes):
    b = BranchDefinition(name="chain", entry_point=nodes[0].node_id)
    b.node_defs = list(nodes)
    b.graph_nodes = [GraphNodeRef(id=n.node_id, node_def_id=n.node_id) for n in nodes]
    edges = [EdgeDefinition(from_node="START", to_node=nodes[0].node_id)]
    for a, c in zip(nodes, nodes[1:]):
        edges.append(EdgeDefinition(from_node=a.node_id, to_node=c.node_id))
    edges.append(EdgeDefinition(from_node=nodes[-1].node_id, to_node="END"))
    b.edges = edges
    b.state_schema = [{"name": f"{n.node_id}_packet", "type": "str"} for n in nodes]
    return b


def _provider_for(packets):
    def fake(prompt, system="", *, role="writer", fallback_response=None):
        node_id = prompt.split("packet:", 1)[1].strip()
        return packets[node_id]
    return fake


class _Adapter:
    """A stand-in for the authenticated-call effector: records what it was
    handed and answers from a script."""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def __call__(self, *, node_id, output_keys, run_state, base_path, run_id, dry_run,
                 allowed_state_keys=None, prior_effects=None):
        self.calls.append({
            "node_id": node_id,
            "prior": {k: v for k, v in (prior_effects or {}).items()},
            "packet": run_state.get(output_keys[0]),
            "state": {k: run_state.get(k) for k in ("content", "sha")},
        })
        return json.loads(json.dumps(self.script[node_id]))


def _run(branch, packets, adapter, monkeypatch, run_id="r1"):
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    chain = EffectChain(run_id=run_id, base_path=None)
    compiled = compile_branch(branch, provider_call=_provider_for(packets), effect_chain=chain)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    app.invoke({}, config={"configurable": {"thread_id": run_id}})
    return chain


_OK_GET = {"delivered": True, "verb": "GET",
           "response": {"status": 200, "body": '{"content": "aGVsbG8=", "sha": "s1"}',
                        "headers": {"set-cookie": "secret=1"}}}
_OK_PUT = {"delivered": True, "verb": "PUT", "response": {"status": 201, "body": "{}"}}


def test_effects_fire_in_graph_order_and_a_later_node_sees_the_full_body(monkeypatch):
    adapter = _Adapter({"fetch": _OK_GET, "write": _OK_PUT})
    chain = _run(
        _linear(_effect_node("fetch"), _effect_node("write", "PUT")),
        {"fetch": _packet("GET"), "write": _packet("PUT")},
        adapter, monkeypatch,
    )
    assert [c["node_id"] for c in adapter.calls] == ["fetch", "write"]
    # write's packet rendered against the chain: the FULL fetch result, headers and all
    assert adapter.calls[1]["prior"]["fetch"]["response"]["body"] == _OK_GET["response"]["body"]
    assert adapter.calls[0]["prior"] == {}
    assert set(chain.evidence) == {"fetch", "write"}
    assert chain.fired == [(SINK, "GET"), (SINK, "PUT")]
    assert chain.delivered_nodes() == ["fetch", "write"]


def test_a_refused_write_fails_the_node_and_later_nodes_never_fire(monkeypatch):
    refused = {"delivered": False, "error": "body transform refused: $ta.replace: old text "
               "not found in the input", "error_kind": "invalid_body_transform"}
    adapter = _Adapter({"fetch": _OK_GET, "write": refused, "open_pr": _OK_PUT})
    branch = _linear(_effect_node("fetch"), _effect_node("write", "PUT"),
                     _effect_node("open_pr", "POST"))
    with pytest.raises(Exception) as excinfo:
        _run(branch, {"fetch": _packet(), "write": _packet("PUT"), "open_pr": _packet("POST")},
             adapter, monkeypatch)
    from tinyassets.runs import _find_effect_failed_exception

    failure = _find_effect_failed_exception(excinfo.value)
    assert isinstance(failure, EffectFailedError)
    assert failure.node_id == "write" and failure.error_kind == "invalid_body_transform"
    assert str(failure).startswith("external write failed - write/authenticated_external_call: ")
    assert [c["node_id"] for c in adapter.calls] == ["fetch", "write"]   # open_pr never fired


def test_a_far_side_4xx_fails_the_node_unless_the_packet_declared_it(monkeypatch):
    miss = {"delivered": True, "verb": "GET",
            "response": {"status": 404, "body": '{"message": "Not Found"}'}}
    adapter = _Adapter({"probe": miss})
    with pytest.raises(Exception) as excinfo:
        _run(_linear(_effect_node("probe")), {"probe": _packet()}, adapter, monkeypatch)
    from tinyassets.runs import _find_effect_failed_exception

    failure = _find_effect_failed_exception(excinfo.value)
    assert failure is not None and failure.error_kind == "far_side_error"
    assert "HTTP 404" in failure.error
    # declared: the 404 is data
    chain = _run(_linear(_effect_node("probe")), {"probe": _packet(accept_statuses=[404])},
                 _Adapter({"probe": miss}), monkeypatch, run_id="r2")
    assert chain.evidence["probe"][SINK]["response"]["status"] == 404


def test_a_node_fires_its_effects_at_most_once_per_run(monkeypatch):
    adapter = _Adapter({"fetch": _OK_GET})
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    chain = EffectChain(run_id="r3")
    node = _effect_node("fetch")
    state = {"fetch_packet": _packet()}
    dispatch_node_effects(chain, node, state)
    with pytest.raises(EffectFailedError, match="already fired"):
        dispatch_node_effects(chain, node, state)
    assert len(adapter.calls) == 1


def test_references_follow_graph_ancestry_not_completion_order():
    a, b, c, d = (_effect_node(n) for n in ("a", "b", "c", "d"))
    branch = BranchDefinition(name="fan", entry_point="a")
    branch.node_defs = [a, b, c, d]
    branch.graph_nodes = [GraphNodeRef(id=n, node_def_id=n) for n in "abcd"]
    branch.edges = [
        EdgeDefinition(from_node="START", to_node="a"),
        EdgeDefinition(from_node="a", to_node="b"),
        EdgeDefinition(from_node="a", to_node="c"),
        EdgeDefinition(from_node="b", to_node="d"),
        EdgeDefinition(from_node="c", to_node="d"),
        EdgeDefinition(from_node="d", to_node="END"),
    ]
    anc = _graph_ancestors(branch)
    assert anc["b"] == {"a"} and anc["c"] == {"a"} and anc["d"] == {"a", "b", "c"}
    assert "c" not in anc["b"]          # siblings are never referencable
    chain = EffectChain(run_id="r4")
    chain.results = {"a": _OK_GET, "c": _OK_GET}
    assert set(chain.prior_effects(anc["b"])) == {"a"}
    assert set(chain.prior_effects(anc["d"])) == {"a", "c"}


def test_code_nodes_see_status_and_body_but_never_headers():
    chain = EffectChain(run_id="r5")
    chain.results = {"fetch": _OK_GET}
    view = chain.effects_view({"fetch"})
    assert view["fetch"]["status"] == 200
    assert view["fetch"]["body"] == {"content": "aGVsbG8=", "sha": "s1"}   # parsed
    assert "headers" not in view["fetch"]
    assert chain.effects_view(set()) == {}


def test_delta_view_applies_the_reducers():
    view = _delta_view(
        {"log": ["a"], "meta": {"x": 1}, "n": 1},
        {"log": ["b"], "meta": {"y": 2}, "n": 2},
        append_fields={"log"}, merge_fields={"meta"},
    )
    assert view == {"log": ["a", "b"], "meta": {"x": 1, "y": 2}, "n": 2}


_EDIT_SOURCE = (
    "import base64\n"
    "def run(state, effects):\n"
    "    got = effects['fetch']['body']\n"
    "    text = base64.b64decode(got['content']).decode()\n"
    "    text = text.replace('hello', 'hello world', 1)\n"
    "    return {'content': base64.b64encode(text.encode()).decode(), 'sha': got['sha']}\n"
)


def _fetch_edit_write_branch(edit_source=_EDIT_SOURCE):
    fetch = _effect_node("fetch")
    edit = NodeDefinition(
        node_id="edit", display_name="edit", source_code=edit_source,
        input_keys=[], output_keys=["content", "sha"],
    )
    write = _effect_node("write", "PUT", input_keys=("content", "sha"))
    b = _linear(fetch, edit, write)
    b.state_schema += [{"name": "content", "type": "str"}, {"name": "sha", "type": "str"}]
    return b


def test_fetch_code_write_in_one_run_without_any_operator(monkeypatch):
    """The shape the whole change exists for (live 2026-08-30: four deploys of
    `$ta.*` operators to change one line). A code node reads the fetch's full
    parsed body, edits it deterministically, and the write node's packet reads
    the result from state - the model never carries the bytes."""
    adapter = _Adapter({"fetch": _OK_GET, "write": _OK_PUT})
    chain = _run(
        _fetch_edit_write_branch(),
        {"fetch": _packet(), "write": _packet("PUT")}, adapter, monkeypatch, run_id="r7",
    )
    assert [c["node_id"] for c in adapter.calls] == ["fetch", "write"]
    # aGVsbG8= is "hello"; the code node produced "hello world", and the write
    # node's packet renders against state that carries it (its input_keys)
    import base64

    write_call = adapter.calls[1]
    assert base64.b64decode(write_call["state"]["content"]) == b"hello world"
    assert write_call["state"]["sha"] == "s1"
    assert chain.evidence["write"][SINK]["delivered"] is True
    assert set(chain.evidence) == {"fetch", "write"}       # the code node has no effect row


def test_a_code_node_that_raises_fails_the_run_as_code_node_failed(monkeypatch, tmp_path):
    from tinyassets.runs import _classify_failure, execute_branch, get_run

    adapter = _Adapter({"fetch": _OK_GET, "write": _OK_PUT})
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    bad = _EDIT_SOURCE.replace("got['sha']", "got['missing']")
    branch = _fetch_edit_write_branch(bad)
    packets = {"fetch": _packet(), "write": _packet("PUT")}
    outcome = execute_branch(
        tmp_path, branch=branch, inputs={}, provider_call=_provider_for(packets),
    )
    assert outcome.status == "failed"
    assert "code node 'edit' failed" in outcome.error and "KeyError" in outcome.error
    assert _classify_failure(get_run(tmp_path, outcome.run_id)) == "code_node_failed"
    assert [c["node_id"] for c in adapter.calls] == ["fetch"]      # write never fired


def test_a_terminal_status_settles_from_the_chain_and_forgets_it(monkeypatch, tmp_path):
    """A write that fired before the failure settles as a write - the old
    `settle(run_id, [])` read-shortcut must not run when a chain exists."""
    from tinyassets import runs

    settled = []
    monkeypatch.setattr(
        effectors, "settle_engine_admission",
        lambda rid, fired: settled.append((rid, list(fired))),
    )
    chain = EffectChain(run_id="r6")
    chain.fired.append((SINK, "POST"))
    chain.evidence["create_branch"] = {SINK: {"delivered": True, "verb": "POST",
                                             "response": {"status": 201, "body": "{}"}}}
    register_effect_chain(chain)
    runs.initialize_runs_db(tmp_path)
    runs.update_run_status(tmp_path, "r6", status=runs.RUN_STATUS_FAILED, error="x")
    assert settled == [("r6", [(SINK, "POST")])]
    assert forget_effect_chain("r6") is None            # forgotten at terminal status
    assert chain.delivered_nodes() == ["create_branch"]
