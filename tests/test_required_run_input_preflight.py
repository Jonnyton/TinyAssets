"""Pre-admission required-input analysis for Branch runs."""

from __future__ import annotations

import json
import sqlite3

import pytest

from tinyassets.branches import (
    BranchDefinition,
    ConditionalEdge,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.runs import (
    MissingRequiredInputs,
    execute_branch_async,
    execute_branch_version_async,
    preflight_required_inputs,
)


def _branch(
    nodes: list[NodeDefinition],
    edges: list[EdgeDefinition],
    *,
    conditional_edges: list[ConditionalEdge] | None = None,
    entry: str | None = None,
    schema: list[dict] | None = None,
) -> BranchDefinition:
    return BranchDefinition(
        branch_def_id="preflight-branch",
        name="Preflight proof",
        author="maintainer-fixture",
        graph_nodes=[GraphNodeRef(id=node.node_id) for node in nodes],
        node_defs=nodes,
        edges=edges,
        conditional_edges=conditional_edges or [],
        entry_point=entry or nodes[0].node_id,
        state_schema=schema or [],
    )


def _node(
    node_id: str,
    *,
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
) -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id,
        display_name=node_id,
        input_keys=list(inputs),
        output_keys=list(outputs),
        prompt_template=(
            " ".join(f"{{{key}}}" for key in inputs)
            if inputs
            else "constant prompt"
        ),
    )


def test_declared_but_unused_input_remains_optional() -> None:
    branch = _branch(
        [NodeDefinition(
            node_id="entry",
            display_name="entry",
            input_keys=["optional_context"],
            prompt_template="constant prompt",
        )],
        [EdgeDefinition("entry", "END")],
    )
    preflight_required_inputs(branch, {})


def test_code_state_get_is_optional_but_subscript_is_required() -> None:
    optional = _branch(
        [NodeDefinition(
            node_id="entry",
            display_name="entry",
            input_keys=["context"],
            output_keys=["result"],
            source_code="def run(state):\n    return {'result': state.get('context', {})}\n",
        )],
        [EdgeDefinition("entry", "END")],
    )
    preflight_required_inputs(optional, {})

    required = _branch(
        [NodeDefinition(
            node_id="entry",
            display_name="entry",
            input_keys=["context"],
            output_keys=["result"],
            source_code="def run(state):\n    return {'result': state['context']}\n",
        )],
        [EdgeDefinition("entry", "END")],
    )
    with pytest.raises(MissingRequiredInputs) as caught:
        preflight_required_inputs(required, {})
    assert caught.value.missing_input_keys == ["context"]


def test_missing_keys_are_sorted_with_schema_guidance() -> None:
    branch = _branch(
        [_node("entry", inputs=("zeta", "context"))],
        [EdgeDefinition("entry", "END")],
        schema=[
            {"name": "zeta", "type": "list"},
            {
                "name": "context",
                "type": "dict",
                "description": "Structured request context",
            },
        ],
    )

    with pytest.raises(MissingRequiredInputs) as caught:
        preflight_required_inputs(branch, {})

    assert caught.value.missing_input_keys == ["context", "zeta"]
    assert caught.value.input_guidance == {
        "context": {
            "type": "dict",
            "example": {},
            "description": "Structured request context",
        },
        "zeta": {"type": "list", "example": []},
    }
    assert caught.value.failure_class == "missing_required_inputs"


@pytest.mark.parametrize("value", ["", 0, False, [], {}, None])
def test_falsey_caller_value_counts_as_supplied(value: object) -> None:
    branch = _branch(
        [_node("entry", inputs=("context",))],
        [EdgeDefinition("entry", "END")],
    )
    preflight_required_inputs(branch, {"context": value})


@pytest.mark.parametrize("key", ["default_value", "default"])
def test_canonical_and_legacy_schema_defaults_count_as_available(key: str) -> None:
    branch = _branch(
        [_node("entry", inputs=("context",))],
        [EdgeDefinition("entry", "END")],
        schema=[{"name": "context", "type": "boolean", key: False}],
    )
    preflight_required_inputs(branch, {})


def test_guaranteed_predecessor_output_satisfies_consumer() -> None:
    branch = _branch(
        [
            _node("produce", outputs=("context",)),
            _node("consume", inputs=("context",)),
        ],
        [EdgeDefinition("produce", "consume"), EdgeDefinition("consume", "END")],
    )
    preflight_required_inputs(branch, {})


def test_plain_parallel_fan_in_merges_one_arms_output_before_consumer() -> None:
    branch = _branch(
        [
            _node("fan_out"),
            _node("producer", outputs=("context",)),
            _node("sibling"),
            _node("consume", inputs=("context",)),
        ],
        [
            EdgeDefinition("fan_out", "producer"),
            EdgeDefinition("fan_out", "sibling"),
            EdgeDefinition("producer", "consume"),
            EdgeDefinition("sibling", "consume"),
            EdgeDefinition("consume", "END"),
        ],
    )
    assert branch.validate() == []
    preflight_required_inputs(branch, {})


def test_conditional_join_requires_key_missing_on_one_route() -> None:
    branch = _branch(
        [
            _node("route"),
            _node("with_context", outputs=("context",)),
            _node("without_context"),
            _node("consume", inputs=("context",)),
        ],
        [
            EdgeDefinition("with_context", "consume"),
            EdgeDefinition("without_context", "consume"),
            EdgeDefinition("consume", "END"),
        ],
        conditional_edges=[ConditionalEdge(
            "route",
            {"with": "with_context", "without": "without_context"},
        )],
    )

    with pytest.raises(MissingRequiredInputs) as caught:
        preflight_required_inputs(branch, {})
    assert caught.value.missing_input_keys == ["context"]


def test_alternate_routes_each_producing_key_satisfy_join() -> None:
    branch = _branch(
        [
            _node("route"),
            _node("left", outputs=("context",)),
            _node("right", outputs=("context",)),
            _node("consume", inputs=("context",)),
        ],
        [
            EdgeDefinition("left", "consume"),
            EdgeDefinition("right", "consume"),
            EdgeDefinition("consume", "END"),
        ],
        conditional_edges=[ConditionalEdge("route", {"l": "left", "r": "right"})],
    )
    preflight_required_inputs(branch, {})


def test_loop_output_is_not_available_on_first_entry() -> None:
    branch = _branch(
        [
            _node("consume", inputs=("context",)),
            _node("later", outputs=("context",)),
        ],
        [EdgeDefinition("consume", "later")],
        conditional_edges=[ConditionalEdge("later", {"again": "consume", "done": "END"})],
    )

    with pytest.raises(MissingRequiredInputs) as caught:
        preflight_required_inputs(branch, {})
    assert caught.value.missing_input_keys == ["context"]


def test_async_refusal_creates_no_run_and_never_calls_provider(tmp_path) -> None:
    calls = 0

    def provider_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "must not run"

    branch = _branch(
        [_node("entry", inputs=("context",), outputs=("result",))],
        [EdgeDefinition("entry", "END")],
    )

    with pytest.raises(MissingRequiredInputs):
        execute_branch_async(
            tmp_path,
            branch=branch,
            inputs={},
            actor="user:test",
            provider_call=provider_call,
        )

    assert calls == 0
    assert not (tmp_path / ".runs.db").exists()


def test_immutable_version_refusal_creates_no_run_row(tmp_path) -> None:
    from tinyassets.branch_versions import publish_branch_version

    branch = _branch(
        [_node("entry", inputs=("context",))],
        [EdgeDefinition("entry", "END")],
    )
    version = publish_branch_version(
        tmp_path,
        branch.to_dict(),
        publisher="maintainer-fixture",
    )

    with pytest.raises(MissingRequiredInputs):
        execute_branch_version_async(
            tmp_path,
            branch_version_id=version.branch_version_id,
            inputs={},
            actor="user:test",
        )

    with sqlite3.connect(tmp_path / ".runs.db") as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "runs" not in tables


def test_live_and_version_handlers_share_public_error_shape(monkeypatch, tmp_path) -> None:
    from tinyassets import daemon_server
    from tinyassets import runs as run_core
    from tinyassets.api import branches as api_branches
    from tinyassets.api import runs as api_runs

    branch = _branch(
        [_node("entry", inputs=("context",))],
        [EdgeDefinition("entry", "END")],
        schema=[{"name": "context", "type": "dict"}],
    )
    failure = MissingRequiredInputs(
        ["context"],
        {"context": {"type": "dict", "example": {}}},
    )

    monkeypatch.setattr(api_runs, "_ensure_runs_recovery", lambda: None)
    monkeypatch.setattr(api_runs, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(api_runs, "_run_actor_for_kwargs", lambda _kwargs: "user:test")
    monkeypatch.setattr(api_runs, "_bind_run_provider_call", lambda call, _uid: call)
    monkeypatch.setattr(api_branches, "resolve_branch_id_for_read", lambda _s, _b: "branch")
    monkeypatch.setattr(daemon_server, "get_branch_definition", lambda *_a, **_k: branch.to_dict())

    def refuse(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(run_core, "execute_branch_async", refuse)
    monkeypatch.setattr(run_core, "execute_branch_version_async", refuse)

    live = json.loads(api_runs._action_run_branch({"branch_def_id": "branch"}))
    version = json.loads(api_runs._action_run_branch_version({
        "branch_version_id": "branch@version",
    }))

    for payload in (live, version):
        assert payload["failure_class"] == "missing_required_inputs"
        assert payload["missing_input_keys"] == ["context"]
        assert payload["input_guidance"] == {
            "context": {"type": "dict", "example": {}},
        }
        assert payload["actionable_by"] == "chatbot"
        assert "run_id" not in payload
