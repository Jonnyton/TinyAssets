"""#59 — prompt_template must preserve literal braces (JSON examples,
code fences, math expressions) without forcing authors to double-escape.

Before the fix, a template containing ``{"doc": "X"}`` raised a
``ValueError`` from ``str.format_map`` because the braces weren't part
of a valid format spec. Authors had to escape every brace as ``{{`` /
``}}``, but the Jinja-style normalizer then re-ate one level. Chicken-
and-egg churn that user-sim's Mission 6 ran into on 2026-04-13.

The fix: replace ``str.format_map`` with a regex substitution that only
matches valid identifier placeholders, leaving other braces alone.
"""

from __future__ import annotations

import pytest

from tinyassets.graph_compiler import _render_template

# ─── _render_template unit tests ─────────────────────────────────────────


def test_render_substitutes_valid_identifier_placeholder():
    out = _render_template("Hello, {name}!", {"name": "world"})
    assert out == "Hello, world!"


def test_render_preserves_json_example_with_literal_braces():
    template = 'Output as {"doc": "X", "page": 3}'
    out = _render_template(template, {})
    # Critical: the JSON braces survive verbatim. No escape needed.
    assert out == 'Output as {"doc": "X", "page": 3}'


def test_render_handles_mix_of_placeholder_and_literal_braces():
    template = 'topic: {topic}, example: {"doc": "X"}'
    out = _render_template(template, {"topic": "whales"})
    assert out == 'topic: whales, example: {"doc": "X"}'


def test_render_preserves_multiple_json_literal_blocks():
    template = 'first: {"a": 1}, middle: {var}, second: {"b": 2}'
    out = _render_template(template, {"var": "X"})
    assert out == 'first: {"a": 1}, middle: X, second: {"b": 2}'


def test_render_preserves_code_fence_braces():
    template = (
        "Python:\n```\ndef f(x): return {x: x*2}\n```\n"
        "topic: {topic}"
    )
    out = _render_template(template, {"topic": "hashing"})
    assert "def f(x): return {x: x*2}" in out
    assert "topic: hashing" in out


def test_render_preserves_math_expression_braces():
    template = "Set theory: {a, b, c} is a set. Topic: {topic}"
    out = _render_template(template, {"topic": "discrete math"})
    assert out == "Set theory: {a, b, c} is a set. Topic: discrete math"


def test_render_raises_keyerror_on_missing_state_key():
    with pytest.raises(KeyError):
        _render_template("Hello {name}!", {})


def test_render_leaves_malformed_single_brace_alone():
    """``abc {incomplete`` has a single unmatched brace — not a
    placeholder, not a JSON fragment. It should survive unchanged, not
    corrupt output silently."""
    template = "abc {incomplete"
    out = _render_template(template, {})
    assert out == "abc {incomplete"


def test_render_empty_template_returns_empty():
    assert _render_template("", {}) == ""


def test_render_placeholder_substitution_coerces_non_str_values():
    out = _render_template("count={n}, ok={flag}",
                           {"n": 42, "flag": True})
    assert out == "count=42, ok=True"


# ─── End-to-end: compile + invoke a node with a JSON-heavy template ──────


def _make_branch(template: str, state_keys: list[str]) -> object:
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    branch = BranchDefinition(name="brace test", entry_point="only")
    branch.node_defs = [NodeDefinition(
        node_id="only",
        display_name="Only",
        prompt_template=template,
        output_keys=["result"],
        input_keys=list(state_keys),
    )]
    branch.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    branch.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]
    branch.state_schema = [
        {"name": key, "type": "str", "default": ""} for key in state_keys
    ] + [{"name": "result", "type": "str", "default": ""}]
    return branch


def test_compile_and_run_template_with_json_example():
    """End-to-end: a node whose prompt_template contains a literal JSON
    example compiles, runs, and produces a prompt with the JSON intact."""
    from langgraph.checkpoint.memory import InMemorySaver

    from tinyassets.graph_compiler import compile_branch

    captured: dict[str, str] = {}

    def _provider(prompt: str, system: str, *, role: str) -> str:
        captured["prompt"] = prompt
        return "ok"

    branch = _make_branch(
        'Return as JSON: {"doc": "X", "topic": "{topic}"}',
        ["topic"],
    )
    compiled = compile_branch(branch, provider_call=_provider)
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    out = runnable.invoke(
        {"topic": "whales"},
        config={"configurable": {"thread_id": "t1"}},
    )
    # The JSON braces survived substitution; only {topic} got replaced.
    assert 'Return as JSON: {"doc": "X", "topic": "whales"}' == captured["prompt"]
    assert out["result"] == "ok"


def test_compile_reports_missing_state_key_cleanly():
    from langgraph.checkpoint.memory import InMemorySaver

    from tinyassets.graph_compiler import compile_branch

    branch = _make_branch("topic: {topic}", ["topic"])
    compiled = compile_branch(branch, provider_call=lambda *a, **k: "ok")
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(Exception) as exc_info:
        runnable.invoke(
            {},  # no topic
            config={"configurable": {"thread_id": "t2"}},
        )
    # LangGraph may wrap the CompilerError, but the message should
    # surface the missing-key hint.
    assert "topic" in str(exc_info.value)


def test_empty_provider_response_raises_compiler_error():
    """Empty string from provider must raise CompilerError, not silently
    set result='', which would cascade as phantom success downstream."""
    from langgraph.checkpoint.memory import InMemorySaver

    from tinyassets.graph_compiler import CompilerError, compile_branch

    branch = _make_branch("topic: {topic}", ["topic"])
    compiled = compile_branch(
        branch,
        provider_call=lambda *a, **k: "",  # empty response
    )
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(Exception) as exc_info:
        runnable.invoke(
            {"topic": "test"},
            config={"configurable": {"thread_id": "t-empty"}},
        )
    assert "empty response" in str(exc_info.value).lower() or isinstance(
        exc_info.value.__context__ or exc_info.value, CompilerError
    )


def test_jinja_style_double_braces_still_substitute():
    """The #44 Jinja-style normalizer must still fire — templates using
    ``{{var}}`` keep working unchanged."""
    from langgraph.checkpoint.memory import InMemorySaver

    from tinyassets.graph_compiler import compile_branch

    captured: dict[str, str] = {}

    def _provider(prompt: str, system: str, *, role: str) -> str:
        captured["prompt"] = prompt
        return "ok"

    branch = _make_branch("Hello {{name}}!", ["name"])
    compiled = compile_branch(branch, provider_call=_provider)
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    runnable.invoke(
        {"name": "world"},
        config={"configurable": {"thread_id": "t3"}},
    )
    assert captured["prompt"] == "Hello world!"


# ─── Build-time placeholder validation (BUG-014 Part B) ─────────────────────


def _make_validation_branch(template: str, input_keys: list[str], state_keys: list[str]):
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    branch = BranchDefinition(name="validation test", entry_point="n1")
    branch.node_defs = [NodeDefinition(
        node_id="n1",
        display_name="N1",
        prompt_template=template,
        output_keys=["out"],
        input_keys=list(input_keys),
    )]
    branch.graph_nodes = [GraphNodeRef(id="n1", node_def_id="n1")]
    branch.edges = [
        EdgeDefinition(from_node="START", to_node="n1"),
        EdgeDefinition(from_node="n1", to_node="END"),
    ]
    branch.state_schema = [
        {"name": k, "type": "str", "default": ""} for k in state_keys
    ] + [{"name": "out", "type": "str", "default": ""}]
    return branch


def test_validate_raises_for_undeclared_placeholder():
    """build_branch validate() must name both the node and the missing key."""
    branch = _make_validation_branch(
        template="Hello {undeclared_key}!",
        input_keys=[],
        state_keys=[],
    )
    errors = branch.validate()
    assert any("n1" in e and "undeclared_key" in e for e in errors), (
        f"Expected error naming node 'n1' and key 'undeclared_key'. Got: {errors}"
    )


def test_validate_no_error_for_escaped_placeholder():
    """\\{key\\} is a literal brace sequence — not a placeholder reference.

    Even if 'key' is absent from input_keys and state_schema, validate()
    must NOT raise an error, because the backslash escape marks it as
    literal output.
    """
    branch = _make_validation_branch(
        template=r"Literal brace: \{key\}",
        input_keys=[],
        state_keys=[],
    )
    errors = branch.validate()
    placeholder_errors = [
        e for e in errors
        if "key" in e and "prompt_template" in e
    ]
    assert not placeholder_errors, (
        f"Escaped placeholder should not trigger validation error. Got: {placeholder_errors}"
    )
