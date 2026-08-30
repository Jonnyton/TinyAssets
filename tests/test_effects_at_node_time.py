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


# --- Codex round 2 (2026-08-30): the six P0s, each pinned ---------------------


def test_resume_carries_the_runs_authority_so_foreign_code_cannot_fail_open(tmp_path):
    """R2 P0: the resume path compiled without an execution context, so a
    public-foreign branch's code ran after an interrupt. The context is built
    from the persisted run row for both paths."""
    import inspect

    from tinyassets import runs

    runs.initialize_runs_db(tmp_path)
    branch = _fetch_edit_write_branch()
    branch.author = "alice"
    ctx = runs._execution_context_for_run(tmp_path, "nope", branch, fallback_actor="alice")
    assert ctx.caller_provenance == "own" and ctx.actor == "alice"
    ctx = runs._execution_context_for_run(tmp_path, "nope", branch, fallback_actor="mallory")
    assert ctx.caller_provenance == "public-foreign"
    # the resume site passes it to compile_branch (structural pin)
    src = inspect.getsource(runs._invoke_graph_resume)
    assert "execution_context=resume_context" in src
    assert "_execution_context_for_run(base_path, run_id, branch)" in src


def test_rpc_runs_the_invoker_inside_the_requests_context(monkeypatch):
    """R2 P0: the sandbox answers RPCs from a drain thread, which carries no
    ContextVars, so an invoker resolved the daemon's env identity instead of
    the run's actor. The node thread's context is copied into the call."""
    import contextvars

    from tinyassets import graph_compiler as gc

    who = contextvars.ContextVar("who", default="daemon-env")

    def fake_invoker(node, **_kw):
        return lambda action, **kwargs: {"actor": who.get(), "action": action}

    monkeypatch.setattr(gc, "_build_node_mcp_invoker", fake_invoker)
    who.set("alice")
    node = NodeDefinition(
        node_id="who", display_name="who", input_keys=[], output_keys=["r"],
        source_code="def run(state):\n    return {'r': invoke_mcp_action('probe', x=1)}\n",
    )
    branch = _linear(node)
    branch.state_schema = [{"name": "r", "type": "dict"}]
    chain = EffectChain(run_id="r8")
    compiled = compile_branch(branch, provider_call=None, effect_chain=chain)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    out = app.invoke({}, config={"configurable": {"thread_id": "r8"}})
    assert out["r"] == {"actor": "alice", "action": "probe"}
    assert chain.rpc_calls == 1


def test_rpc_cap_is_per_run_not_per_node():
    chain = EffectChain(run_id="r9")
    for _ in range(32):
        chain.rpc_permit()
    with pytest.raises(RuntimeError, match="too many"):
        chain.rpc_permit()


def test_a_bad_reducer_delta_fails_before_any_effect_fires(monkeypatch):
    """R2 P0: `_delta_view` overwrote an append field with a non-list, the PUT
    fired, then LangGraph raised on the reducer. Validate first, fire never."""
    adapter = _Adapter({"write": _OK_PUT})
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    node = NodeDefinition(
        node_id="write", display_name="write", input_keys=[], output_keys=["log", "write_packet"],
        source_code=(
            "def run(state):\n"
            "    return {'log': 'not-a-list', 'write_packet': %r}\n" % _packet("PUT")
        ),
        effects=[SINK],
    )
    branch = _linear(node)
    branch.state_schema = [
        {"name": "log", "type": "list", "reducer": "append"},
        {"name": "write_packet", "type": "str"},
    ]
    chain = EffectChain(run_id="r10")
    compiled = compile_branch(branch, provider_call=None, effect_chain=chain)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(Exception, match="reducer is append"):
        app.invoke({"log": []}, config={"configurable": {"thread_id": "r10"}})
    assert adapter.calls == []


def test_the_merge_writer_guard_runs_before_effects(monkeypatch):
    """R2 P0: the guard wrapped the effect wrapper, so a PUT fired before the
    guard refused an undeclared merge writer. Now guard -> effects."""
    adapter = _Adapter({"write": _OK_PUT})
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    declared = NodeDefinition(
        node_id="declared", display_name="declared", input_keys=[], output_keys=["meta"],
        source_code="def run(state):\n    return {'meta': {'a': 1}}\n",
    )
    sneaky = NodeDefinition(
        node_id="write", display_name="write", input_keys=[], output_keys=["write_packet"],
        source_code=(
            "def run(state):\n"
            "    return {'meta': {'b': 2}, 'write_packet': %r}\n" % _packet("PUT")
        ),
        effects=[SINK],
    )
    branch = _linear(declared, sneaky)
    branch.state_schema = [
        {"name": "meta", "type": "dict", "reducer": "merge"},
        {"name": "write_packet", "type": "str"},
    ]
    chain = EffectChain(run_id="r11")
    compiled = compile_branch(branch, provider_call=None, effect_chain=chain)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(Exception, match="without declaring it"):
        app.invoke({}, config={"configurable": {"thread_id": "r11"}})
    assert adapter.calls == []


def test_at_most_once_holds_under_concurrent_visits(monkeypatch):
    """R2 P0: the evidence check and the reservation were separated by the
    adapter call, so two synchronized visits both fired."""
    import threading

    started = threading.Barrier(2, timeout=5)
    release = threading.Event()

    class _Slow(_Adapter):
        def __call__(self, **kw):
            release.wait(5)
            return super().__call__(**kw)

    adapter = _Slow({"fetch": _OK_GET})
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    chain = EffectChain(run_id="r12")
    node = _effect_node("fetch")
    state = {"fetch_packet": _packet()}
    errors: list[str] = []

    def visit():
        started.wait()
        try:
            dispatch_node_effects(chain, node, state)
        except EffectFailedError as exc:
            errors.append(exc.error_kind)

    threads = [threading.Thread(target=visit) for _ in range(2)]
    for t in threads:
        t.start()
    release.set()
    for t in threads:
        t.join(10)
    assert len(adapter.calls) == 1
    assert errors == ["effect_already_fired"]


def test_settlement_waits_for_an_in_flight_dispatch_and_closes_the_chain(monkeypatch):
    """R2 P0: a terminal status settled `[]` while an adapter was still
    running; the late PUT then landed on a forgotten chain as a read."""
    import threading

    inside = threading.Event()
    release = threading.Event()

    class _Blocking(_Adapter):
        def __call__(self, **kw):
            inside.set()
            release.wait(5)
            return super().__call__(**kw)

    adapter = _Blocking({"write": _OK_PUT})
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    settled: list[list] = []
    monkeypatch.setattr(
        effectors, "settle_engine_admission",
        lambda rid, fired: settled.append(list(fired)),
    )
    chain = EffectChain(run_id="r13")
    node = _effect_node("write", "PUT")
    worker = threading.Thread(
        target=dispatch_node_effects, args=(chain, node, {"write_packet": _packet("PUT")}),
    )
    worker.start()
    assert inside.wait(5)
    settler = threading.Thread(target=chain.settle)
    settler.start()
    settler.join(0.3)
    assert settler.is_alive()                      # settle is waiting for the dispatch
    assert settled == []
    release.set()
    worker.join(5)
    settler.join(5)
    assert settled == [[(SINK, "PUT")]]           # the late write was counted
    assert chain.closed is True
    with pytest.raises(EffectFailedError, match="terminal"):
        dispatch_node_effects(chain, _effect_node("late"), {"late_packet": _packet()})


def test_an_accepted_status_is_not_re_reported_at_completion(monkeypatch):
    from tinyassets.runs import _collect_external_write_errors

    miss = {"delivered": True, "verb": "GET",
            "response": {"status": 404, "body": '{"message": "Not Found"}'}}
    adapter = _Adapter({"probe": miss})
    chain = _run(_linear(_effect_node("probe")), {"probe": _packet(accept_statuses=[404])},
                 adapter, monkeypatch, run_id="r14")
    assert chain.evidence["probe"][SINK]["accepted_status"] is True
    assert _collect_external_write_errors(dict(chain.evidence)) == []


def test_two_graph_nodes_sharing_a_definition_have_their_own_ancestry():
    """R2 P1: ancestry and effect identity were keyed by node_def id, so two
    graph nodes over one definition received the union of both."""
    shared = _effect_node("shared")
    fetch = _effect_node("fetch")
    branch = BranchDefinition(name="reuse", entry_point="first")
    branch.node_defs = [shared, fetch]
    branch.graph_nodes = [
        GraphNodeRef(id="first", node_def_id="shared"),
        GraphNodeRef(id="fetch", node_def_id="fetch"),
        GraphNodeRef(id="second", node_def_id="shared"),
    ]
    branch.edges = [
        EdgeDefinition(from_node="START", to_node="first"),
        EdgeDefinition(from_node="first", to_node="fetch"),
        EdgeDefinition(from_node="fetch", to_node="second"),
        EdgeDefinition(from_node="second", to_node="END"),
    ]
    anc = _graph_ancestors(branch)
    assert anc["first"] == set()
    assert anc["second"] == {"first", "fetch"}


def test_evidence_merges_into_a_callers_terminal_output(monkeypatch, tmp_path):
    """R2 P1: INTERRUPTED with a caller-supplied output dropped the chain's
    evidence; now it is merged in, never clobbering the caller's keys."""
    from tinyassets import runs

    monkeypatch.setattr(effectors, "settle_engine_admission", lambda rid, fired: None)
    runs.initialize_runs_db(tmp_path)
    created = runs.create_run(
        tmp_path, branch_def_id="b", thread_id="t15", inputs={}, run_name="x",
    )
    run_id = created if isinstance(created, str) else getattr(created, "run_id", "")
    chain = EffectChain(run_id=run_id)
    chain.fired.append((SINK, "PUT"))
    chain.evidence["write"] = {SINK: {"delivered": True, "verb": "PUT",
                                      "response": {"status": 201, "body": "{}"}}}
    register_effect_chain(chain)
    runs.update_run_status(
        tmp_path, run_id, status=runs.RUN_STATUS_INTERRUPTED, error="paused",
        output={"child_invocation_receipt_gate": {"status": "receipt_waiting"}},
    )
    rec = runs.get_run(tmp_path, run_id)
    assert rec["output"]["child_invocation_receipt_gate"]["status"] == "receipt_waiting"
    assert "write" in rec["output"]["external_write_results"]
    assert rec["output"]["failed_after_effects"] == ["write"]


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
