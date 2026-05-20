"""BUG-085 — strict_input_isolation diagnostic + state_schema defaults.

Two distinct fixes covered here:

**B1 — Contradictory error message.** Before the fix, a placeholder
referencing a DECLARED input_key that simply wasn't present in state
(upstream node hadn't produced it yet, or a state_schema default wasn't
seeded) raised a CompilerError saying the key was "outside declared
input_keys" — while listing the key inside the declared list. The
operator saw a self-contradicting message.

After the fix, the error path partitions missing keys into:

- ``truly_outside``: keys NOT in declared_inputs → real isolation
  violation; the existing "outside declared input_keys" message stands.
- ``declared_but_unavailable``: keys IN declared_inputs but absent from
  state at execution time → a different error explaining the actual
  failure mode.

**B2 — state_schema defaults not seeded.** State_schema fields with a
declared ``default_value`` should be available to strict-isolation
prompt placeholders even when the caller didn't pass them in ``inputs``.
The fix exposes ``seed_initial_state`` which merges defaults UNDER
caller inputs.
"""

from __future__ import annotations

import pytest

from workflow.branches import NodeDefinition
from workflow.graph_compiler import (
    CompilerError,
    _build_prompt_template_node,
    _state_schema_defaults,
    seed_initial_state,
)


def _make_prompt_fn(
    node: NodeDefinition,
    *,
    provider_call=lambda prompt, system, role="writer": f"RENDERED::{prompt}",
    event_sink=None,
):
    return _build_prompt_template_node(
        node, provider_call=provider_call, event_sink=event_sink,
    )


# ─── B1: declared-but-unavailable diagnostic ──────────────────────────────


def test_strict_isolation_declared_but_missing_in_state_emits_clear_message():
    """A declared input_key that isn't present in state at execution
    time must NOT be reported as 'outside declared input_keys'. The
    error must clearly state the key IS declared but not present."""
    node = NodeDefinition(
        node_id="n1",
        display_name="n1",
        # goal_ladder + surface_status are declared, but state will
        # not contain them — mirrors the BUG-085 reproduction shape.
        input_keys=["goal_ladder", "surface_status"],
        output_keys=["draft"],
        prompt_template="Ladder: {goal_ladder}\nStatus: {surface_status}",
        strict_input_isolation=True,
    )
    fn = _make_prompt_fn(node)
    with pytest.raises(CompilerError) as exc:
        fn({})  # state has neither key
    msg = str(exc.value)
    # The error should NOT claim these keys are "outside declared input_keys".
    assert "outside declared input_keys" not in msg, msg
    # It should say they are not present in state.
    assert "not present in state" in msg
    # It should name the declared keys.
    assert "goal_ladder" in msg
    assert "surface_status" in msg


def test_strict_isolation_undeclared_key_still_reports_outside():
    """Pure isolation violation (placeholder NOT in declared inputs)
    must still emit the original 'outside declared input_keys' error."""
    node = NodeDefinition(
        node_id="n1",
        display_name="n1",
        input_keys=["topic"],
        output_keys=["draft"],
        prompt_template="Write {topic} with {leaked_key}.",
        strict_input_isolation=True,
    )
    fn = _make_prompt_fn(node)
    with pytest.raises(CompilerError) as exc:
        fn({"topic": "whales", "leaked_key": "leaked"})
    msg = str(exc.value)
    assert "outside declared input_keys" in msg
    assert "leaked_key" in msg
    # The original strict_input_isolation marker still appears so
    # existing assertions in test_input_keys_isolation.py keep passing.
    assert "strict_input_isolation=true" in msg


def test_strict_isolation_mixed_missing_keys_prioritizes_outside_violation():
    """When BOTH categories are present, the message must clearly call
    out the truly-outside keys (the real isolation violation) and ALSO
    surface the declared-but-unavailable keys so the operator sees the
    full picture, not a contradictory single-message dump."""
    node = NodeDefinition(
        node_id="n1",
        display_name="n1",
        # 'topic' is declared but missing; 'leaked' is the real
        # isolation violation.
        input_keys=["topic"],
        output_keys=["draft"],
        prompt_template="Topic: {topic}; Extra: {leaked}",
        strict_input_isolation=True,
    )
    fn = _make_prompt_fn(node)
    with pytest.raises(CompilerError) as exc:
        fn({"leaked": "value"})  # 'topic' missing, 'leaked' is undeclared
    msg = str(exc.value)
    assert "outside declared input_keys" in msg
    assert "leaked" in msg
    # The declared-but-unavailable key should also be surfaced.
    assert "topic" in msg
    assert "not present in state" in msg


def test_strict_isolation_declared_keys_present_still_renders():
    """Sanity: declared input_keys that ARE present in state render
    normally — no error path triggered."""
    node = NodeDefinition(
        node_id="n1",
        display_name="n1",
        input_keys=["goal_ladder"],
        output_keys=["draft"],
        prompt_template="Ladder: {goal_ladder}",
        strict_input_isolation=True,
    )
    fn = _make_prompt_fn(node)
    out = fn({"goal_ladder": "step1"})
    assert out == {"draft": "RENDERED::Ladder: step1"}


# ─── B2: state_schema defaults seeded into initial state ──────────────────


def test_state_schema_defaults_extracts_default_values():
    """``_state_schema_defaults`` returns a dict of {name: default_value}
    for every state_schema entry carrying a non-None default."""
    schema = [
        {"name": "topic", "type": "string", "default_value": "whales"},
        {"name": "count", "type": "number", "default_value": 5},
        {"name": "no_default", "type": "string"},
        {"name": "explicit_none", "type": "string", "default_value": None},
    ]
    result = _state_schema_defaults(schema)
    assert result == {"topic": "whales", "count": 5}


def test_state_schema_defaults_handles_empty_or_none():
    assert _state_schema_defaults(None) == {}
    assert _state_schema_defaults([]) == {}


def test_seed_initial_state_merges_defaults_under_inputs():
    """Caller inputs always win; defaults only fill keys the caller did
    not provide."""
    schema = [
        {"name": "topic", "type": "string", "default_value": "default-topic"},
        {"name": "mood", "type": "string", "default_value": "cheerful"},
    ]
    inputs = {"topic": "explicit-topic"}
    seeded = seed_initial_state(inputs, schema)
    assert seeded["topic"] == "explicit-topic"  # caller wins
    assert seeded["mood"] == "cheerful"  # default fills gap


def test_seed_initial_state_returns_independent_dict():
    """The returned dict must not be the same object as inputs (no
    surprise mutation of the caller's dict)."""
    schema = [{"name": "x", "type": "string", "default_value": "d"}]
    inputs = {"y": 1}
    seeded = seed_initial_state(inputs, schema)
    assert seeded is not inputs
    assert "x" not in inputs  # caller's dict untouched


def test_seed_initial_state_no_schema_returns_copy_of_inputs():
    inputs = {"a": 1}
    seeded = seed_initial_state(inputs, None)
    assert seeded == {"a": 1}
    assert seeded is not inputs


def test_strict_isolation_state_schema_default_available_to_placeholder():
    """End-to-end: a state_schema field with a default, declared as an
    input_key, is available to a strict-isolation placeholder even when
    the caller did not pass it in ``inputs`` — provided the caller used
    ``seed_initial_state`` to build the initial state."""
    schema = [
        {"name": "style", "type": "string", "default_value": "formal"},
    ]
    node = NodeDefinition(
        node_id="n1",
        display_name="n1",
        input_keys=["style"],
        output_keys=["draft"],
        prompt_template="Style: {style}",
        strict_input_isolation=True,
    )
    fn = _make_prompt_fn(node)
    initial_state = seed_initial_state({}, schema)
    out = fn(initial_state)
    assert out == {"draft": "RENDERED::Style: formal"}
