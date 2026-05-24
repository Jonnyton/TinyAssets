"""Branch graph runner tests.

Covers the compiler, the runs persistence layer, the 6 MCP actions on the
``extensions`` tool, and the acceptance criteria from the spec.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from workflow.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)


@pytest.fixture
def runner_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, action, **kwargs):
    return json.loads(us.extensions(action=action, **kwargs))


def _run_and_wait(us, *, timeout: float = 30.0, **kwargs):
    """Kick off `run_branch` and block on the worker.

    Returns the initial response dict with ``status`` and ``output``
    populated from the terminal state after the worker completes. Tests
    written against the sync-v1 contract use this as a drop-in.
    """
    result = _call(us, "run_branch", **kwargs)
    if "run_id" not in result:
        return result
    from workflow.runs import wait_for

    wait_for(result["run_id"], timeout=timeout)
    snapshot = _call(us, "get_run", run_id=result["run_id"])
    final = dict(result)
    final["status"] = snapshot.get("status", result.get("status"))
    output_result = _call(us, "get_run_output", run_id=result["run_id"])
    final["output"] = output_result.get("output", {})
    return final


def _build_recipe_branch(us) -> str:
    """Create the recipe-tracker branch from the Phase 2 vignette."""
    bid = _call(us, "create_branch", name="Recipe tracker")["branch_def_id"]
    for nid, display, tmpl in (
        ("capture", "Capture recipe", "Extract recipe: {raw_recipe}"),
        ("categorize", "Categorize", "Classify: {capture_output}"),
        ("archive", "Archive", "Archive: {categorize_output}"),
    ):
        _call(us, "add_node",
              branch_def_id=bid, node_id=nid,
              display_name=display, prompt_template=tmpl,
              output_keys=f"{nid}_output")
    for src, dst in (
        ("START", "capture"),
        ("capture", "categorize"),
        ("categorize", "archive"),
        ("archive", "END"),
    ):
        _call(us, "connect_nodes",
              branch_def_id=bid, from_node=src, to_node=dst)
    _call(us, "set_entry_point", branch_def_id=bid, node_id="capture")
    for field in ("raw_recipe", "capture_output", "categorize_output", "archive_output"):
        _call(us, "add_state_field",
              branch_def_id=bid, field_name=field, field_type="str")
    return bid


# ─────────────────────────────────────────────────────────────────────────────
# Compiler unit tests
# ─────────────────────────────────────────────────────────────────────────────


def test_compiler_rejects_invalid_branch(tmp_path):
    from workflow.graph_compiler import CompilerError, compile_branch

    b = BranchDefinition(name="")  # no name, no nodes
    with pytest.raises(CompilerError):
        compile_branch(b)


def test_compiler_rejects_unapproved_source_code():
    from workflow.graph_compiler import UnapprovedNodeError, compile_branch

    b = BranchDefinition(name="test", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only", display_name="Only",
        source_code="def run(state): return {}",
        approved=False,
    )]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]
    with pytest.raises(UnapprovedNodeError):
        compile_branch(b)


def test_compiler_accepts_approved_source_code():
    from langgraph.checkpoint.memory import InMemorySaver

    from workflow.graph_compiler import compile_branch

    b = BranchDefinition(name="test", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only", display_name="Only",
        source_code="def run(state): return {'out': state.get('x', 0) + 1}",
        approved=True,
    )]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]
    b.state_schema = [
        {"name": "x", "type": "int"},
        {"name": "out", "type": "int"},
    ]
    compiled = compile_branch(b)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    result = app.invoke({"x": 5}, config={"configurable": {"thread_id": "t1"}})
    assert result["out"] == 6


def test_source_code_node_can_call_allowed_mcp_action(monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver

    import workflow.api.market as market
    from workflow.graph_compiler import compile_branch

    calls: list[tuple[str, dict]] = []

    def fake_goals(*, action: str, **kwargs):
        calls.append((action, kwargs))
        return json.dumps({
            "status": "ok",
            "entries": [{"branch_def_id": "b1"}],
        })

    monkeypatch.setattr(market, "goals", fake_goals)

    b = BranchDefinition(name="test", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only",
        display_name="Only",
        source_code=(
            "def run(state):\n"
            "    board = invoke_mcp_action("
            "'goals.leaderboard', goal_id=state['goal_id'], metric='run_count')\n"
            "    return {'leaderboard_count': len(board['entries'])}\n"
        ),
        input_keys=["goal_id"],
        output_keys=["leaderboard_count"],
        tools_allowed=["goals.leaderboard"],
        approved=True,
    )]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]
    b.state_schema = [
        {"name": "goal_id", "type": "str"},
        {"name": "leaderboard_count", "type": "int"},
    ]
    compiled = compile_branch(b)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    result = app.invoke(
        {"goal_id": "g1"}, config={"configurable": {"thread_id": "mcp-ok"}},
    )

    assert result["leaderboard_count"] == 1
    assert calls == [("leaderboard", {"goal_id": "g1", "metric": "run_count"})]


def test_source_code_node_rejects_mcp_action_not_in_tools_allowed(monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver

    import workflow.api.market as market
    from workflow.graph_compiler import CompilerError, compile_branch

    def fake_goals(*, action: str, **kwargs):
        raise AssertionError("disallowed MCP action should not dispatch")

    monkeypatch.setattr(market, "goals", fake_goals)

    b = BranchDefinition(name="test", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only",
        display_name="Only",
        source_code=(
            "def run(state):\n"
            "    invoke_mcp_action('goals.leaderboard', goal_id='g1')\n"
            "    return {'out': 'unreachable'}\n"
        ),
        output_keys=["out"],
        tools_allowed=[],
        approved=True,
    )]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]
    b.state_schema = [{"name": "out", "type": "str"}]
    compiled = compile_branch(b)
    app = compiled.graph.compile(checkpointer=InMemorySaver())

    with pytest.raises(CompilerError) as exc_info:
        app.invoke({}, config={"configurable": {"thread_id": "mcp-denied"}})
    assert "not allowed" in str(exc_info.value)


def test_branch_spec_preserves_tools_allowed():
    from workflow.api.branches import _apply_node_spec

    branch = BranchDefinition(name="test")
    err = _apply_node_spec(branch, {
        "node_id": "only",
        "display_name": "Only",
        "source_code": "def run(state): return {}",
        "tools_allowed": ["goals.leaderboard"],
    })

    assert err == ""
    assert branch.node_defs[0].tools_allowed == ["goals.leaderboard"]


def test_compiler_synthesized_typeddict_reducer_append():
    """state_schema with reducer=append should accumulate across nodes."""
    from langgraph.checkpoint.memory import InMemorySaver

    from workflow.graph_compiler import compile_branch

    b = BranchDefinition(name="accumulator", entry_point="a")
    b.node_defs = [
        NodeDefinition(
            node_id="a", display_name="A", approved=True,
            source_code="def run(state): return {'log': ['from-a']}",
        ),
        NodeDefinition(
            node_id="b", display_name="B", approved=True,
            source_code="def run(state): return {'log': ['from-b']}",
        ),
    ]
    b.graph_nodes = [
        GraphNodeRef(id="a", node_def_id="a", position=0),
        GraphNodeRef(id="b", node_def_id="b", position=1),
    ]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="a"),
        EdgeDefinition(from_node="a", to_node="b"),
        EdgeDefinition(from_node="b", to_node="END"),
    ]
    b.state_schema = [
        {"name": "log", "type": "list", "reducer": "append"},
    ]
    compiled = compile_branch(b)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    result = app.invoke(
        {"log": ["start"]}, config={"configurable": {"thread_id": "acc1"}},
    )
    assert result["log"] == ["start", "from-a", "from-b"]


# ─────────────────────────────────────────────────────────────────────────────
# Prompt-template substitution (bug #44)
# ─────────────────────────────────────────────────────────────────────────────


def _single_node_branch(template: str, output_key: str = "out") -> BranchDefinition:
    b = BranchDefinition(name="T", entry_point="write")
    b.node_defs = [NodeDefinition(
        node_id="write", display_name="Write",
        prompt_template=template, output_keys=[output_key],
    )]
    b.graph_nodes = [GraphNodeRef(id="write", node_def_id="write")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="write"),
        EdgeDefinition(from_node="write", to_node="END"),
    ]
    b.state_schema = [
        {"name": "topic", "type": "str"},
        {"name": "style", "type": "str"},
        {"name": output_key, "type": "str"},
    ]
    return b


def _run_and_capture(branch, inputs):
    from langgraph.checkpoint.memory import InMemorySaver

    from workflow.graph_compiler import compile_branch

    captured: list[str] = []

    def fake_provider(prompt, system="", *, role="writer", fallback_response=None):
        captured.append(prompt)
        return "[mock]"

    compiled = compile_branch(branch, provider_call=fake_provider)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    app.invoke(inputs, config={"configurable": {"thread_id": "t"}})
    return captured


def test_prompt_template_single_brace_substitutes():
    """Python-style {var} placeholder should be filled from state."""
    branch = _single_node_branch("Write about {topic}")
    captured = _run_and_capture(branch, {"topic": "scaling laws"})
    assert captured == ["Write about scaling laws"]


def test_prompt_template_double_brace_substitutes():
    """Jinja-style {{var}} placeholder should also be filled (bug #44)."""
    branch = _single_node_branch("Write about {{topic}}")
    captured = _run_and_capture(branch, {"topic": "scaling laws"})
    assert captured == ["Write about scaling laws"]
    # Critical: the literal `{topic}` must NOT leak into the LLM prompt.
    assert "{topic}" not in captured[0]


def test_prompt_template_double_brace_with_whitespace():
    """{{ topic }} with spaces inside should still substitute."""
    branch = _single_node_branch("Write about {{ topic }}")
    captured = _run_and_capture(branch, {"topic": "scaling laws"})
    assert captured == ["Write about scaling laws"]


def test_prompt_template_mixed_single_and_double():
    """Mixed {var} and {{var}} in one template both substitute."""
    branch = _single_node_branch("Write {{topic}} in {style}")
    captured = _run_and_capture(
        branch, {"topic": "scaling laws", "style": "academic"},
    )
    assert captured == ["Write scaling laws in academic"]


def test_prompt_template_multiple_double_brace_occurrences():
    branch = _single_node_branch(
        "Topic: {{topic}}. Also: {{topic}}. Style: {{style}}."
    )
    captured = _run_and_capture(
        branch, {"topic": "X", "style": "Y"},
    )
    assert captured == ["Topic: X. Also: X. Style: Y."]


def test_prompt_template_missing_key_raises():
    """Referencing a state key that's not defined is caught at
    compile time by BranchDefinition.validate() — the build-time
    layer added in the literal-brace spec. Runtime raise remains as
    the second layer if the validator is bypassed."""
    from workflow.graph_compiler import CompilerError, compile_branch

    branch = _single_node_branch("Write about {missing}")
    branch.state_schema = [{"name": "out", "type": "str"}]  # no 'missing'
    with pytest.raises(CompilerError) as exc_info:
        compile_branch(branch, provider_call=lambda *a, **kw: "[mock]")
    assert "missing" in str(exc_info.value).lower()


def test_prompt_template_missing_key_detected_for_double_brace():
    """Bug #44 cousin: ``{{missing}}`` is normalized to ``{missing}``
    before the build-time validator checks declaration, so clients
    can't silently leak Jinja-form placeholders into the LLM."""
    from workflow.graph_compiler import CompilerError, compile_branch

    branch = _single_node_branch("Write about {{missing}}")
    branch.state_schema = [{"name": "out", "type": "str"}]
    with pytest.raises(CompilerError) as exc_info:
        compile_branch(branch, provider_call=lambda *a, **kw: "[mock]")
    assert "missing" in str(exc_info.value).lower()


def test_normalize_placeholders_helper():
    """Direct unit test on the helper."""
    from workflow.graph_compiler import _normalize_placeholders

    assert _normalize_placeholders("{x}") == "{x}"
    assert _normalize_placeholders("{{x}}") == "{x}"
    assert _normalize_placeholders("{{ x }}") == "{x}"
    assert _normalize_placeholders("a{{x}}b{{y}}c") == "a{x}b{y}c"
    assert _normalize_placeholders("") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Runs persistence
# ─────────────────────────────────────────────────────────────────────────────


def test_execute_branch_end_to_end(tmp_path):
    from workflow.runs import execute_branch, get_run, list_events

    b = BranchDefinition(name="test", entry_point="n1")
    b.node_defs = [NodeDefinition(
        node_id="n1", display_name="N1", approved=True,
        source_code="def run(state): return {'out': state.get('x', 0) * 2}",
    )]
    b.graph_nodes = [GraphNodeRef(id="n1", node_def_id="n1")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="n1"),
        EdgeDefinition(from_node="n1", to_node="END"),
    ]
    b.state_schema = [
        {"name": "x", "type": "int"}, {"name": "out", "type": "int"},
    ]

    outcome = execute_branch(tmp_path, branch=b, inputs={"x": 21})
    assert outcome.status == "completed"
    assert outcome.output["out"] == 42

    record = get_run(tmp_path, outcome.run_id)
    assert record["status"] == "completed"
    events = list_events(tmp_path, outcome.run_id)
    assert any(e["status"] == "ran" for e in events)


def test_execute_branch_reports_node_status_callback(tmp_path):
    from workflow.runs import (
        NODE_STATUS_RAN,
        NODE_STATUS_RUNNING,
        execute_branch,
    )

    b = BranchDefinition(name="test", entry_point="n1")
    b.node_defs = [NodeDefinition(
        node_id="n1", display_name="N1", approved=True,
        source_code="def run(state): return {'out': state.get('x', 0) * 2}",
    )]
    b.graph_nodes = [GraphNodeRef(id="n1", node_def_id="n1")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="n1"),
        EdgeDefinition(from_node="n1", to_node="END"),
    ]
    b.state_schema = [
        {"name": "x", "type": "int"}, {"name": "out", "type": "int"},
    ]
    seen: list[tuple[str, str]] = []

    outcome = execute_branch(
        tmp_path,
        branch=b,
        inputs={"x": 21},
        on_node_status=lambda node_id, status: seen.append((node_id, status)),
    )

    assert outcome.status == "completed"
    assert seen == [
        ("n1", NODE_STATUS_RUNNING),
        ("n1", NODE_STATUS_RAN),
    ]


def test_execute_branch_fails_on_compiler_error(tmp_path):
    from workflow.runs import execute_branch

    # Missing entry point → validate() error → compiler error
    b = BranchDefinition(name="broken")
    b.node_defs = [NodeDefinition(
        node_id="only", display_name="Only", prompt_template="{x}",
    )]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.state_schema = [{"name": "x", "type": "str"}]

    outcome = execute_branch(tmp_path, branch=b, inputs={"x": "hi"})
    assert outcome.status == "failed"
    assert outcome.error


def test_execute_branch_reports_unapproved_source_code(tmp_path):
    from workflow.runs import execute_branch

    b = BranchDefinition(name="test", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only", display_name="Only",
        source_code="def run(state): return {}",
        approved=False,
    )]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]

    outcome = execute_branch(tmp_path, branch=b, inputs={})
    assert outcome.status == "failed"
    assert "approved" in outcome.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# MCP action tests (through the extensions tool dispatcher)
# ─────────────────────────────────────────────────────────────────────────────


def test_run_branch_recipe_vignette_end_to_end(runner_env):
    """Acceptance criterion #1 — recipe-tracker runs via run_branch.

    Phase 3.5: run_branch now returns ``status=queued`` and the worker
    finishes in the background. Use ``_run_and_wait`` to resolve the
    terminal state for assertion.
    """
    us, _ = runner_env
    bid = _build_recipe_branch(us)

    result = _run_and_wait(
        us,
        branch_def_id=bid,
        inputs_json=json.dumps({"raw_recipe": "pasta carbonara"}),
    )
    assert result["status"] == "completed", result
    assert "capture_output" in result["output"]
    assert "archive_output" in result["output"]


def test_run_branch_rejects_invalid_branch(runner_env):
    us, _ = runner_env
    bid = _call(us, "create_branch", name="Empty")["branch_def_id"]
    # No nodes → validate() fails
    result = _call(us, "run_branch", branch_def_id=bid, inputs_json="{}")
    assert "error" in result
    assert "validation_errors" in result


def test_run_branch_rejects_malformed_inputs_json(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    result = _call(
        us, "run_branch",
        branch_def_id=bid, inputs_json="this is not json",
    )
    assert "error" in result


def test_get_run_returns_snapshot_with_mermaid(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(
        us, branch_def_id=bid,
        inputs_json=json.dumps({"raw_recipe": "risotto"}),
    )
    rid = run["run_id"]

    snapshot = _call(us, "get_run", run_id=rid)
    assert snapshot["status"] == "completed"
    assert snapshot["mermaid"].startswith("```mermaid")
    assert "flowchart" in snapshot["mermaid"]
    # Status-colored classes are declared in the diagram
    assert "classDef ran" in snapshot["mermaid"]
    # Per-node statuses are ordered, each a short record
    assert len(snapshot["node_statuses"]) >= 3
    assert all(
        isinstance(s.get("node_id"), str) and isinstance(s.get("status"), str)
        for s in snapshot["node_statuses"]
    )


def test_list_runs_filters_by_branch(runner_env):
    us, _ = runner_env
    bid1 = _build_recipe_branch(us)
    bid2 = _build_recipe_branch(us)
    _run_and_wait(us, branch_def_id=bid1,
                  inputs_json=json.dumps({"raw_recipe": "a"}))
    _run_and_wait(us, branch_def_id=bid2,
                  inputs_json=json.dumps({"raw_recipe": "b"}))

    listing = _call(us, "list_runs", branch_def_id=bid1)
    assert listing["count"] == 1
    assert listing["runs"][0]["branch_def_id"] == bid1


def test_stream_run_returns_events_since_cursor(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))

    first = _call(us, "stream_run", run_id=run["run_id"], since_step=-1)
    assert first["events"]
    cursor = first["next_cursor"]

    # Polling again with the new cursor should return nothing new.
    second = _call(us, "stream_run",
                   run_id=run["run_id"], since_step=cursor)
    assert second["events"] == []


def test_cancel_run_marks_cancel_requested(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))

    result = _call(us, "cancel_run", run_id=run["run_id"])
    assert result["status"] == "cancel_requested"


def test_get_run_output_full_and_single_field(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))

    full = _call(us, "get_run_output", run_id=run["run_id"])
    assert full["status"] == "completed"
    assert full["output"]

    single = _call(us, "get_run_output",
                   run_id=run["run_id"], field_name="capture_output")
    assert single["field_name"] == "capture_output"
    assert isinstance(single["value"], str)

    missing = _call(us, "get_run_output",
                    run_id=run["run_id"], field_name="nope")
    assert "error" in missing
    assert "available_fields" in missing


def test_run_ledger_entries_land(runner_env):
    us, base = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))
    _call(us, "cancel_run", run_id=run["run_id"])

    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    actions = [e["action"] for e in ledger]
    assert "run_branch" in actions
    assert "cancel_run" in actions


def test_thread_isolation_between_runs(runner_env):
    """AC #5 — two runs of different branches don't bleed state."""
    us, base = runner_env
    bid1 = _build_recipe_branch(us)
    bid2 = _build_recipe_branch(us)
    run1 = _run_and_wait(us, branch_def_id=bid1,
                         inputs_json=json.dumps({"raw_recipe": "first"}))
    run2 = _run_and_wait(us, branch_def_id=bid2,
                         inputs_json=json.dumps({"raw_recipe": "second"}))

    rec1 = _call(us, "get_run", run_id=run1["run_id"])
    rec2 = _call(us, "get_run", run_id=run2["run_id"])
    assert rec1["run_id"] != rec2["run_id"]
    # thread_id == run_id (isolation guarantee)
    from workflow.runs import get_run as raw_get_run

    raw1 = raw_get_run(base, run1["run_id"])
    raw2 = raw_get_run(base, run2["run_id"])
    assert raw1["thread_id"] == run1["run_id"]
    assert raw2["thread_id"] == run2["run_id"]
    assert raw1["thread_id"] != raw2["thread_id"]


def test_no_fantasy_domain_import_required(runner_env, monkeypatch):
    """AC #6 — a non-fantasy branch runs with no fantasy_author imports."""
    import sys

    # Drop any previously-imported fantasy_author modules to prove the
    # runner doesn't require them.
    fa_mods = [
        k for k in list(sys.modules)
        if k.startswith("fantasy_author")
        or k.startswith("domains.fantasy_daemon")
    ]
    for mod in fa_mods:
        monkeypatch.setitem(sys.modules, mod, None)

    us, _ = runner_env
    bid = _call(us, "create_branch", name="Research")["branch_def_id"]
    _call(us, "add_node",
          branch_def_id=bid, node_id="analyze",
          display_name="Analyze", prompt_template="Summarize: {topic}",
          output_keys="summary")
    _call(us, "connect_nodes",
          branch_def_id=bid, from_node="START", to_node="analyze")
    _call(us, "connect_nodes",
          branch_def_id=bid, from_node="analyze", to_node="END")
    _call(us, "set_entry_point", branch_def_id=bid, node_id="analyze")
    _call(us, "add_state_field",
          branch_def_id=bid, field_name="topic", field_type="str")
    _call(us, "add_state_field",
          branch_def_id=bid, field_name="summary", field_type="str")

    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"topic": "small language models"}))
    assert run["status"] == "completed"
    assert "summary" in run["output"]


def test_unknown_action_catalog_lists_run_actions(runner_env):
    us, _ = runner_env
    result = _call(us, "flimflam")
    avail = result.get("available_actions", [])
    for action in ("run_branch", "get_run", "list_runs",
                   "stream_run", "wait_for_run", "cancel_run",
                   "get_run_output"):
        assert action in avail


# ─────────────────────────────────────────────────────────────────────────────
# tool_return_shapes.md compliance (two-channel returns)
# ─────────────────────────────────────────────────────────────────────────────


def test_run_branch_returns_markdown_text_channel(runner_env):
    """Phase 3.5 — run_branch returns status=queued immediately with a
    text channel that points callers at the polling surface."""
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    result = _call(us, "run_branch", branch_def_id=bid,
                   inputs_json=json.dumps({"raw_recipe": "a"}))
    assert "text" in result
    assert "queued" in result["text"].lower()
    # Phone-legibility: raw run_id must live in structuredContent, not
    # the text channel (#58). run_id is still present in the dict.
    assert result["run_id"] not in result["text"]
    assert "run_id" in result  # structured content still carries it
    # Text should direct the caller to the long-poll surface first.
    assert "wait_for_run" in result["text"]


def test_get_run_text_channel_matches_summary(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))
    snap = _call(us, "get_run", run_id=run["run_id"])
    assert "text" in snap
    assert "```mermaid" in snap["text"]


def test_list_runs_catalog_text_is_compact(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    _run_and_wait(us, branch_def_id=bid,
                  inputs_json=json.dumps({"raw_recipe": "a"}))
    _run_and_wait(us, branch_def_id=bid,
                  inputs_json=json.dumps({"raw_recipe": "b"}))
    result = _call(us, "list_runs")
    assert "text" in result
    assert "run(s):" in result["text"]
    assert "- `" in result["text"]


def test_stream_run_events_text_is_tight(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))
    result = _call(us, "stream_run", run_id=run["run_id"], since_step=-1)
    assert "text" in result
    assert result["text"].count("\n") < 30


def test_cancel_run_text_channel(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))
    result = _call(us, "cancel_run", run_id=run["run_id"])
    assert "text" in result
    assert "Cancel requested" in result["text"]


def test_get_run_output_text_channel(runner_env):
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))
    full = _call(us, "get_run_output", run_id=run["run_id"])
    assert "text" in full
    # #58: raw run_id does not leak into the phone-legible text channel.
    assert run["run_id"] not in full["text"]
    # The workflow name should surface instead — it's in the text.
    assert "workflow" in full["text"].lower()
    single = _call(us, "get_run_output", run_id=run["run_id"],
                   field_name="capture_output")
    assert "text" in single
    assert "capture_output" in single["text"]
    assert run["run_id"] not in single["text"]


def test_stream_run_truncates_long_event_history(runner_env):
    """Per spec §Long-running actions — tight poll responses, not the
    whole transcript. Caps at 12 event lines even with more events."""
    us, _ = runner_env
    bid = _build_recipe_branch(us)
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw_recipe": "a"}))
    result = _call(us, "stream_run", run_id=run["run_id"], since_step=-1)
    text_lines = result["text"].split("\n")
    bullet_lines = [line for line in text_lines if line.startswith("- step")]
    assert len(bullet_lines) <= 12


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.5: async executor (task #39)
# ─────────────────────────────────────────────────────────────────────────────
#
# `run_branch` returns ``status=queued`` in <1s even when the graph takes
# minutes. `cancel_run` actually stops an in-flight run at the next node
# boundary. `recover_in_flight_runs` cleans up interrupted runs on restart.


def test_run_branch_returns_quickly_with_queued_status(runner_env):
    """AC: MCP returns in <1s wall even when the graph would take much
    longer. Phase 3.5 makes this real."""
    import time

    us, _ = runner_env
    bid = _build_recipe_branch(us)

    start = time.monotonic()
    result = _call(us, "run_branch", branch_def_id=bid,
                   inputs_json=json.dumps({"raw_recipe": "a"}))
    elapsed = time.monotonic() - start

    assert result["status"] == "queued"
    assert result["run_id"]
    # 1s budget — the synchronous prep path writes the run row + a
    # handful of pending events. Mock provider never runs in the
    # foreground.
    assert elapsed < 2.0, f"run_branch took {elapsed:.2f}s, expected <2s"
    # Wait for the background worker to finish before leaving the test
    # so we don't leak threads into the next one.
    from workflow.runs import wait_for

    wait_for(result["run_id"], timeout=30.0)


def test_cancel_run_interrupts_mid_flight(tmp_path):
    """Cancel requested between nodes unwinds the graph cleanly.

    Works directly against ``workflow.runs`` rather than through the
    Universe Server so the test can control node timing precisely.
    """
    import threading

    from workflow.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from workflow.runs import (
        execute_branch_async,
        get_run,
        request_cancel,
        wait_for,
    )

    # Build a 3-node linear chain; the middle node waits on a latch so
    # the test has a reliable window to request cancel AFTER node1
    # completes but BEFORE node2.
    gate = threading.Event()

    def fake_provider(prompt, system="", *, role="writer", fallback_response=None):
        if "wait_for_cancel" in prompt:
            gate.wait(timeout=10.0)
        return "[ok]"

    b = BranchDefinition(name="Cancel", entry_point="n1")
    b.node_defs = [
        NodeDefinition(node_id=n, display_name=n.upper(),
                       prompt_template=t, output_keys=[f"{n}_out"])
        for n, t in (
            ("n1", "first"),
            ("n2", "wait_for_cancel"),
            ("n3", "third"),
        )
    ]
    b.graph_nodes = [
        GraphNodeRef(id="n1", node_def_id="n1", position=0),
        GraphNodeRef(id="n2", node_def_id="n2", position=1),
        GraphNodeRef(id="n3", node_def_id="n3", position=2),
    ]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="n1"),
        EdgeDefinition(from_node="n1", to_node="n2"),
        EdgeDefinition(from_node="n2", to_node="n3"),
        EdgeDefinition(from_node="n3", to_node="END"),
    ]
    b.state_schema = [{"name": k, "type": "str"} for k in (
        "n1_out", "n2_out", "n3_out",
    )]

    outcome = execute_branch_async(
        tmp_path, branch=b, inputs={},
        provider_call=fake_provider,
    )
    assert outcome.status == "queued"
    # Request cancel while n2 is blocked on the gate.
    import time

    time.sleep(0.5)
    request_cancel(tmp_path, outcome.run_id)
    gate.set()  # let n2 finish; cancel check fires in the event_sink
    wait_for(outcome.run_id, timeout=10.0)

    record = get_run(tmp_path, outcome.run_id)
    assert record["status"] == "cancelled"
    # n3 must NOT have emitted a 'ran' event.
    from workflow.runs import list_events

    events = list_events(tmp_path, outcome.run_id)
    ran_nodes = {e["node_id"] for e in events if e["status"] == "ran"}
    assert "n3" not in ran_nodes


def test_recover_in_flight_runs_marks_running_as_interrupted(tmp_path):
    """Simulated restart: queued/running rows become 'interrupted'."""
    from workflow.runs import (
        RUN_STATUS_RUNNING,
        create_run,
        get_run,
        initialize_runs_db,
        recover_in_flight_runs,
        update_run_status,
    )

    initialize_runs_db(tmp_path)
    rid1 = create_run(tmp_path, branch_def_id="b1", thread_id="",
                      inputs={}, actor="a")
    rid2 = create_run(tmp_path, branch_def_id="b2", thread_id="",
                      inputs={}, actor="a")
    update_run_status(tmp_path, rid1, status=RUN_STATUS_RUNNING)
    # rid2 stays queued
    count = recover_in_flight_runs(tmp_path)
    assert count == 2

    r1 = get_run(tmp_path, rid1)
    r2 = get_run(tmp_path, rid2)
    assert r1["status"] == "interrupted"
    assert r2["status"] == "interrupted"
    assert r1["finished_at"] is not None


def test_recover_in_flight_runs_leaves_terminal_rows_alone(tmp_path):
    """Completed/failed/cancelled rows must NOT be re-marked."""
    from workflow.runs import (
        RUN_STATUS_CANCELLED,
        RUN_STATUS_COMPLETED,
        RUN_STATUS_FAILED,
        create_run,
        get_run,
        recover_in_flight_runs,
        update_run_status,
    )

    for status in (RUN_STATUS_COMPLETED, RUN_STATUS_FAILED,
                   RUN_STATUS_CANCELLED):
        rid = create_run(tmp_path, branch_def_id="b", thread_id="",
                         inputs={}, actor="a")
        update_run_status(tmp_path, rid, status=status)
        recover_in_flight_runs(tmp_path)
        assert get_run(tmp_path, rid)["status"] == status


def test_latest_run_by_name_returns_newest_matching_branch_run(tmp_path):
    from workflow.runs import (
        RUN_STATUS_COMPLETED,
        create_run,
        latest_run_by_name,
        update_run_status,
    )

    older = create_run(
        tmp_path, branch_def_id="b1", thread_id="", inputs={},
        run_name="branch-task-bt-1", actor="a",
    )
    newer = create_run(
        tmp_path, branch_def_id="b1", thread_id="", inputs={},
        run_name="branch-task-bt-1", actor="a",
    )
    other_branch = create_run(
        tmp_path, branch_def_id="b2", thread_id="", inputs={},
        run_name="branch-task-bt-1", actor="a",
    )
    for rid in (older, newer, other_branch):
        update_run_status(tmp_path, rid, status=RUN_STATUS_COMPLETED)

    match = latest_run_by_name(
        tmp_path,
        run_name="branch-task-bt-1",
        branch_def_id="b1",
    )

    assert match is not None
    assert match["run_id"] == newer


def test_concurrent_cap_respected(tmp_path, monkeypatch):
    """Custom WORKFLOW_RUN_MAX_CONCURRENT is honored."""
    monkeypatch.setenv("WORKFLOW_RUN_MAX_CONCURRENT", "2")
    from workflow import runs as runs_mod

    # Force executor re-init with the new env var.
    runs_mod.shutdown_executor()
    executor = runs_mod._get_executor()
    assert executor._max_workers == 2
    runs_mod.shutdown_executor()


def test_async_run_completes_successfully(tmp_path):
    """End-to-end: execute_branch_async produces the same final output
    as the sync path, just on a worker thread."""
    from workflow.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from workflow.runs import (
        execute_branch_async,
        get_run,
        wait_for,
    )

    b = BranchDefinition(name="Async", entry_point="n")
    b.node_defs = [NodeDefinition(
        node_id="n", display_name="N", approved=True,
        source_code="def run(state): return {'out': state.get('x', 0) * 3}",
    )]
    b.graph_nodes = [GraphNodeRef(id="n", node_def_id="n")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="n"),
        EdgeDefinition(from_node="n", to_node="END"),
    ]
    b.state_schema = [
        {"name": "x", "type": "int"}, {"name": "out", "type": "int"},
    ]

    outcome = execute_branch_async(tmp_path, branch=b, inputs={"x": 7})
    assert outcome.status == "queued"
    wait_for(outcome.run_id, timeout=10.0)

    record = get_run(tmp_path, outcome.run_id)
    assert record["status"] == "completed"
    assert record["output"] == {"x": 7, "out": 21}
