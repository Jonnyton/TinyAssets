"""Tests for structured JSON output on multi-output + typed prompt nodes.

STATUS.md Approved-bugs 2026-04-22 (Option A — compiler-only). Closes
two sibling silent-drop bugs at the same layer:

1. Multi-output silent-drop: a node declared with ``output_keys =
   ["a", "b"]`` used to write the entire LLM response to ``a`` only,
   silently dropping ``b``.
2. Typed-output no-op: ``state_schema`` entries declared ``int``/
   ``bool``/``list``/``dict`` were treated as declarative — runtime
   never coerced prose into the declared type, so a ``retry_count: int``
   field would stay at its prior value while the LLM emitted the new
   value as prose.

The compiler now appends a JSON-schema contract to the prompt when
(a) the node has >=2 output_keys, OR (b) any declared output_key has a
non-``str`` type in ``state_schema``. The response is parsed as JSON;
each declared key is extracted; values are coerced per state_schema.
Missing key / wrong type / malformed JSON all raise ``CompilerError``
— hard-rule #8 (fail loudly, never silent-drop).

Single-output + str-typed path is unchanged (backward-compat).
"""

from __future__ import annotations

import pytest

from tinyassets.branches import NodeDefinition
from tinyassets.graph_compiler import (
    CompilerError,
    _build_prompt_template_node,
    _coerce_value,
    _extract_json_object,
    _needs_json_contract,
    _state_type_map,
)


def _make_fn(
    node: NodeDefinition,
    *,
    response: str,
    state_schema: list[dict] | None = None,
):
    return _build_prompt_template_node(
        node,
        provider_call=lambda prompt, system, role="writer", **_kw: response,
        event_sink=None,
        state_schema=state_schema,
    )


# ─── Gate selection ────────────────────────────────────────────────────────


def test_needs_json_contract_single_str_output_returns_false():
    node = NodeDefinition(
        node_id="n", display_name="n",
        input_keys=[], output_keys=["draft"],
        prompt_template="write",
    )
    assert _needs_json_contract(node, {"draft": "str"}) is False
    # Default type when unmapped is str.
    assert _needs_json_contract(node, {}) is False


def test_needs_json_contract_multi_output_returns_true():
    node = NodeDefinition(
        node_id="n", display_name="n",
        input_keys=[], output_keys=["a", "b"],
        prompt_template="write",
    )
    assert _needs_json_contract(node, {}) is True


def test_needs_json_contract_typed_output_returns_true():
    node = NodeDefinition(
        node_id="n", display_name="n",
        input_keys=[], output_keys=["retry_count"],
        prompt_template="pick",
    )
    assert _needs_json_contract(node, {"retry_count": "int"}) is True


# ─── JSON extraction helpers ───────────────────────────────────────────────


def test_extract_json_object_plain():
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_tolerates_code_fence():
    assert _extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_object_tolerates_embedded_prose():
    assert _extract_json_object('here you go: {"a": 1}') == {"a": 1}


def test_extract_json_object_raises_on_malformed():
    with pytest.raises(ValueError):
        _extract_json_object("not json at all")


def test_extract_json_object_raises_on_non_object():
    with pytest.raises(ValueError):
        _extract_json_object("[1, 2, 3]")


# ─── Type coercion ─────────────────────────────────────────────────────────


def test_coerce_value_int_from_int():
    assert _coerce_value(42, "int") == 42


def test_coerce_value_int_from_string_raises():
    with pytest.raises(ValueError):
        _coerce_value("not a number", "int")


def test_coerce_value_bool_from_various_shapes():
    assert _coerce_value(True, "bool") is True
    assert _coerce_value("true", "bool") is True
    assert _coerce_value("no", "bool") is False
    with pytest.raises(TypeError):
        _coerce_value("maybe", "bool")


def test_coerce_value_list_wrong_type_raises():
    with pytest.raises(TypeError):
        _coerce_value("not a list", "list")


# ─── End-to-end: prompt_template node with JSON contract ───────────────────


def test_multi_output_parses_and_assigns_all_keys():
    """Fixes the multi-output silent-drop bug."""
    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["title", "body"],
        prompt_template="write a post",
    )
    fn = _make_fn(node, response='{"title": "Hi", "body": "World"}')
    result = fn({})
    assert result == {"title": "Hi", "body": "World"}


def test_multi_output_missing_key_raises():
    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["a", "b"],
        prompt_template="write",
    )
    fn = _make_fn(node, response='{"a": "ok"}')
    with pytest.raises(CompilerError) as exc_info:
        fn({})
    assert "'b'" in str(exc_info.value)


def test_typed_output_coerces_int():
    """Fixes the typed-output no-op bug."""
    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["retry_count"],
        prompt_template="how many retries",
    )
    state_schema = [{"name": "retry_count", "type": "int"}]
    fn = _make_fn(
        node,
        response='{"retry_count": 3}',
        state_schema=state_schema,
    )
    result = fn({})
    assert result == {"retry_count": 3}
    assert isinstance(result["retry_count"], int)


def test_typed_output_wrong_type_raises():
    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["count"],
        prompt_template="count",
    )
    state_schema = [{"name": "count", "type": "int"}]
    fn = _make_fn(
        node,
        response='{"count": "not a number"}',
        state_schema=state_schema,
    )
    with pytest.raises(CompilerError) as exc_info:
        fn({})
    assert "count" in str(exc_info.value)
    assert "int" in str(exc_info.value)


def test_malformed_json_raises():
    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["a", "b"],
        prompt_template="write",
    )
    fn = _make_fn(node, response="this is not JSON")
    with pytest.raises(CompilerError) as exc_info:
        fn({})
    assert "JSON" in str(exc_info.value)


def test_single_str_output_backward_compat_unchanged():
    """The single-str-output path must NOT invoke the JSON contract —
    the response goes through as a plain string assignment to the lone
    output_key. This preserves every existing user branch."""
    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["draft"],
        prompt_template="write",
    )
    fn = _make_fn(node, response="Once upon a time")
    result = fn({})
    assert result == {"draft": "Once upon a time"}


def test_json_contract_suffix_appears_in_prompt():
    """Provider sees the schema contract so the LLM knows to produce
    JSON. Verified by capturing the prompt the provider was called
    with."""
    captured: dict = {}

    def provider(prompt, system, role="writer", **_kw):
        captured["prompt"] = prompt
        return '{"title": "t", "body": "b"}'

    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["title", "body"],
        prompt_template="seed",
    )
    fn = _build_prompt_template_node(
        node, provider_call=provider, event_sink=None,
    )
    fn({})
    assert "RESPONSE FORMAT" in captured["prompt"]
    assert "'title'" in captured["prompt"]
    assert "'body'" in captured["prompt"]


def test_state_type_map_filters_unnamed_entries():
    schema = [
        {"name": "a", "type": "int"},
        {"name": "", "type": "int"},
        {"name": "b", "type": "bool"},
    ]
    assert _state_type_map(schema) == {"a": "int", "b": "bool"}


def test_typed_output_list_passes_through():
    node = NodeDefinition(
        node_id="n1", display_name="n1",
        input_keys=[], output_keys=["items"],
        prompt_template="list things",
    )
    state_schema = [{"name": "items", "type": "list"}]
    fn = _make_fn(
        node,
        response='{"items": ["a", "b", "c"]}',
        state_schema=state_schema,
    )
    assert fn({}) == {"items": ["a", "b", "c"]}
