"""Composite branch actions — `build_branch` and `patch_branch`.

Covers acceptance criteria from
`docs/specs/composite_branch_actions.md`:

1. Recipe-tracker builds in a single `build_branch` call.
2. Validation failure returns `suggestions`; applying them succeeds.
3. Invalid op in `patch_branch` batch rejects everything atomically.
4. One ledger entry per composite call, not per internal op.
5. Fine-grained actions still work unchanged.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver


@pytest.fixture
def comp_env(tmp_path, monkeypatch):
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


RECIPE_SPEC = {
    "name": "Recipe tracker",
    "description": "Capture, categorize, archive recipes",
    "entry_point": "capture",
    "node_defs": [
        {"node_id": "capture", "display_name": "Capture raw recipe",
         "prompt_template": "Extract: {raw_recipe}"},
        {"node_id": "categorize", "display_name": "Categorize",
         "prompt_template": "Classify: {capture_output}"},
        {"node_id": "archive", "display_name": "Archive",
         "prompt_template": "File: {categorize_output}"},
    ],
    "edges": [
        {"from": "START", "to": "capture"},
        {"from": "capture", "to": "categorize"},
        {"from": "categorize", "to": "archive"},
        {"from": "archive", "to": "END"},
    ],
    "state_schema": [
        {"name": "raw_recipe", "type": "str"},
        {"name": "capture_output", "type": "str"},
        {"name": "categorize_output", "type": "str"},
        {"name": "archive_output", "type": "str"},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# AC #1 — one-shot recipe-tracker build
# ─────────────────────────────────────────────────────────────────────────────


def _build_approved_source_branch(us, *, node_id="approved_calc"):
    _call(
        us,
        "register",
        node_id=node_id,
        display_name="Approved calc",
        description="Approved source-code node",
        phase="custom",
        input_keys="",
        output_keys="answer",
        source_code="def run(state): return {'answer': 1}",
        dependencies="",
    )
    prior_actor = os.environ.get("UNIVERSE_SERVER_USER")
    os.environ["UNIVERSE_SERVER_USER"] = "host-operator"
    try:
        approved = _call(us, "approve", node_id=node_id)
    finally:
        if prior_actor is None:
            os.environ.pop("UNIVERSE_SERVER_USER", None)
        else:
            os.environ["UNIVERSE_SERVER_USER"] = prior_actor
    assert approved["approved"] is True
    spec = {
        "name": "Approved source branch",
        "entry_point": node_id,
        "node_defs": [{
            "node_id": node_id,
            "node_ref": {"source": "standalone", "node_id": node_id},
        }],
        "edges": [
            {"from": "START", "to": node_id},
            {"from": node_id, "to": "END"},
        ],
        "state_schema": [{"name": "answer", "type": "int"}],
    }
    built = _call(us, "build_branch", spec_json=json.dumps(spec))
    assert built["batch_receipt"]["source_code_approval"]["runnable"] is True
    return built


def test_recipe_tracker_builds_in_one_call(comp_env):
    us, _ = comp_env
    result = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    assert result["status"] == "built", result
    assert result["node_count"] == 3
    assert result["edge_count"] == 4
    assert result["branch_def_id"]
    assert "text" in result
    assert "Recipe tracker" in result["text"]
    assert "```mermaid" in result["text"]


def test_build_branch_returns_batch_receipt(comp_env):
    us, _ = comp_env
    result = _call(
        us,
        "build_branch",
        spec_json=json.dumps(RECIPE_SPEC),
        request_id="chat-plan-123",
    )

    receipt = result["batch_receipt"]
    assert receipt["receipt_type"] == "branch_authoring_batch"
    assert receipt["action"] == "build_branch"
    assert receipt["actor"] == "tester"
    assert receipt["branch_def_id"] == result["branch_def_id"]
    assert receipt["branch_name"] == "Recipe tracker"
    assert receipt["operation_count"] == 1
    assert receipt["node_count"] == 3
    assert receipt["edge_count"] == 4
    assert receipt["skill_count"] == 0
    assert receipt["validation"] == {
        "status": "ok",
        "valid": True,
        "error_count": 0,
    }
    assert receipt["source_code_approval"]["runnable"] is True
    assert receipt["source_code_approval"]["unapproved_count"] == 0
    assert receipt["plan_context"]["request_id"] == "chat-plan-123"
    assert receipt["plan_context"]["authoritative"] is False
    assert receipt["authorization_effect"] == {
        "grants_authorization": False,
        "grants_scoped_trust_session": False,
        "bypasses_client_approval_prompts": False,
        "approved_action_scope": [],
        "revocation_handle": None,
        "note": (
            "Evidence-only receipt: clients may display or audit it, but must "
            "not treat it as permission to execute future writes."
        ),
    }
    assert "not an authorization grant" in receipt["caveats"][0]


def test_build_branch_receipt_reports_unapproved_source_code(comp_env):
    us, _ = comp_env
    spec = {
        "name": "Code-backed check",
        "entry_point": "calculate",
        "node_defs": [{
            "node_id": "calculate",
            "display_name": "Calculate",
            "source_code": "def run(state): return {'answer': 42}",
            "output_keys": ["answer"],
        }],
        "edges": [
            {"from": "START", "to": "calculate"},
            {"from": "calculate", "to": "END"},
        ],
        "state_schema": [{"name": "answer", "type": "int"}],
    }

    result = _call(us, "build_branch", spec_json=json.dumps(spec))

    assert result["status"] == "built", result
    approval = result["batch_receipt"]["source_code_approval"]
    assert approval["source_code_node_count"] == 1
    assert approval["approved_count"] == 0
    assert approval["unapproved_count"] == 1
    assert approval["runnable"] is False
    assert approval["unapproved_nodes"] == [{
        "node_id": "calculate",
        "display_name": "Calculate",
    }]


def test_patch_branch_source_code_mutation_clears_prior_approval(comp_env):
    us, _ = comp_env
    built = _build_approved_source_branch(us)
    bid = built["branch_def_id"]

    result = _call(
        us,
        "patch_branch",
        branch_def_id=bid,
        changes_json=json.dumps([{
            "op": "update_node",
            "node_id": "approved_calc",
            "source_code": "def run(state): return {'answer': 2}",
        }]),
    )

    assert result["status"] == "patched", result
    approval = result["batch_receipt"]["source_code_approval"]
    assert approval["source_code_node_count"] == 1
    assert approval["approved_count"] == 0
    assert approval["unapproved_count"] == 1
    assert approval["runnable"] is False
    got = _call(us, "get_branch", branch_def_id=bid)
    node = next(n for n in got["node_defs"] if n["node_id"] == "approved_calc")
    assert node["approved"] is False
    assert got["runnable"] is False


def test_build_branch_returns_full_branch_in_structured(comp_env):
    us, _ = comp_env
    result = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    assert result["status"] == "built"
    assert result["name"] == "Recipe tracker"
    assert result["node_count"] == 3


def test_build_branch_persists(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    # Atomic get_branch returns the same branch.
    got = _call(us, "get_branch", branch_def_id=bid)
    assert got["name"] == "Recipe tracker"


def test_build_branch_preserves_node_timeout_seconds(comp_env):
    us, _ = comp_env
    spec = {
        **RECIPE_SPEC,
        "node_defs": [{
            **RECIPE_SPEC["node_defs"][0],
            "timeout_seconds": 45,
        }],
        "edges": [
            {"from": "START", "to": "capture"},
            {"from": "capture", "to": "END"},
        ],
        "state_schema": [
            {"name": "raw_recipe", "type": "str"},
            {"name": "capture_output", "type": "str"},
        ],
    }

    built = _call(us, "build_branch", spec_json=json.dumps(spec))

    assert built["status"] == "built", built
    got = _call(us, "get_branch", branch_def_id=built["branch_def_id"])
    capture = next(n for n in got["node_defs"] if n["node_id"] == "capture")
    assert capture["timeout_seconds"] == 45.0


def test_build_branch_preserves_explicit_non_strict_input_isolation(comp_env):
    us, _ = comp_env
    spec = {
        **RECIPE_SPEC,
        "node_defs": [{
            "node_id": "capture",
            "display_name": "Capture raw recipe",
            "input_keys": ["raw_recipe"],
            "output_keys": ["capture_output"],
            "prompt_template": "Extract {raw_recipe} using {style_guide}",
            "strict_input_isolation": False,
        }],
        "edges": [
            {"from": "START", "to": "capture"},
            {"from": "capture", "to": "END"},
        ],
        "state_schema": [
            {"name": "raw_recipe", "type": "str"},
            {"name": "style_guide", "type": "str"},
            {"name": "capture_output", "type": "str"},
        ],
    }

    built = _call(us, "build_branch", spec_json=json.dumps(spec))

    assert built["status"] == "built", built
    got = _call(us, "get_branch", branch_def_id=built["branch_def_id"])
    capture = next(n for n in got["node_defs"] if n["node_id"] == "capture")
    assert capture["strict_input_isolation"] is False

    from workflow.branches import BranchDefinition
    from workflow.graph_compiler import compile_branch

    prompts: list[str] = []

    def provider(prompt, system="", *, role="writer", fallback_response=None):
        prompts.append(prompt)
        return "captured"

    branch = BranchDefinition.from_dict(got)
    app = compile_branch(branch, provider_call=provider).graph.compile(
        checkpointer=InMemorySaver(),
    )
    result = app.invoke(
        {"raw_recipe": "pasta", "style_guide": "terse"},
        config={"configurable": {"thread_id": "non-strict-build-branch"}},
    )
    assert prompts == ["Extract pasta using terse"]
    assert result["capture_output"] == "captured"


def test_build_branch_fork_from_inherits_parent_topology(comp_env):
    us, base = comp_env
    from workflow.branch_versions import publish_branch_version

    parent = _call(us, "build_branch", spec_json=json.dumps({
        **RECIPE_SPEC,
        "skills": [{
            "skill_id": "recipe-parser",
            "name": "Recipe Parser",
            "version": "1.0.0",
            "body": "Parse a recipe.",
        }],
    }))
    parent_branch = _call(us, "get_branch", branch_def_id=parent["branch_def_id"])
    parent_version = publish_branch_version(
        base,
        parent_branch,
        notes="publish parent",
        publisher="tester",
    )

    child = _call(us, "build_branch", spec_json=json.dumps({
        "name": "Recipe tracker remix",
        "description": "Forked without repeating the graph",
        "fork_from": parent_version.branch_version_id,
    }))

    assert child["status"] == "built", child
    assert child["node_count"] == 3
    assert child["edge_count"] == 4
    assert child["skill_count"] == 1

    got = _call(us, "get_branch", branch_def_id=child["branch_def_id"])
    assert got["fork_from"] == parent_version.branch_version_id
    assert got["parent_def_id"] == parent["branch_def_id"]
    assert got["entry_point"] == "capture"
    assert [n["node_id"] for n in got["node_defs"]] == [
        n["node_id"] for n in parent_branch["node_defs"]
    ]
    assert got["graph"]["edges"] == parent_branch["graph"]["edges"]
    assert got["state_schema"] == parent_branch["state_schema"]
    assert got["skills"] == parent_branch["skills"]


# ─────────────────────────────────────────────────────────────────────────────
# AC #2 — strict-with-suggestions
# ─────────────────────────────────────────────────────────────────────────────


def test_build_branch_rejects_missing_entry_point_with_suggestion(comp_env):
    us, _ = comp_env
    spec = dict(RECIPE_SPEC)
    spec = {**spec, "entry_point": ""}
    result = _call(us, "build_branch", spec_json=json.dumps(spec))
    assert result["status"] == "rejected"
    assert result["errors"]
    assert result["suggestions"]
    # Suggestion should name a concrete fallback
    fixes = " ".join(s["proposed_fix"] for s in result["suggestions"])
    assert "entry_point" in fixes or "capture" in fixes
    # attempted_spec echoed for the client
    assert result["attempted_spec"]["name"] == "Recipe tracker"


def test_applying_suggestion_succeeds(comp_env):
    us, _ = comp_env
    # First call: no entry_point → rejected with suggestion
    bad = {**RECIPE_SPEC, "entry_point": ""}
    first = _call(us, "build_branch", spec_json=json.dumps(bad))
    assert first["status"] == "rejected"
    # Spec suggests capture (first node with no incoming non-START edge).
    # Apply it and retry.
    fixed = {**RECIPE_SPEC, "entry_point": "capture"}
    second = _call(us, "build_branch", spec_json=json.dumps(fixed))
    assert second["status"] == "built"


def test_build_branch_rejects_missing_name_with_suggestion(comp_env):
    us, _ = comp_env
    spec = {**RECIPE_SPEC, "name": ""}
    result = _call(us, "build_branch", spec_json=json.dumps(spec))
    assert result["status"] == "rejected"
    assert any(
        "name" in s["proposed_fix"].lower() for s in result["suggestions"]
    )


def test_build_branch_rejects_malformed_json(comp_env):
    us, _ = comp_env
    result = _call(us, "build_branch", spec_json="not json at all")
    assert result["status"] == "rejected"
    assert "suggestions" in result


def test_build_branch_rejects_empty_spec(comp_env):
    us, _ = comp_env
    result = _call(us, "build_branch", spec_json="")
    assert result["status"] == "rejected"
    assert result["suggestions"]


def test_build_branch_rejects_duplicate_node_ids(comp_env):
    us, _ = comp_env
    spec = {
        **RECIPE_SPEC,
        "node_defs": [
            {"node_id": "dup", "display_name": "A", "prompt_template": "a"},
            {"node_id": "dup", "display_name": "B", "prompt_template": "b"},
        ],
        "entry_point": "dup",
        "edges": [
            {"from": "START", "to": "dup"},
            {"from": "dup", "to": "END"},
        ],
    }
    result = _call(us, "build_branch", spec_json=json.dumps(spec))
    assert result["status"] == "rejected"


def test_build_branch_coerces_unknown_state_type_and_reports(comp_env):
    """Unknown state types get coerced to 'any' but the error list should
    surface the coercion so users can correct it."""
    us, _ = comp_env
    spec = {
        **RECIPE_SPEC,
        "state_schema": [
            {"name": "raw_recipe", "type": "strang"},  # typo
            {"name": "capture_output", "type": "str"},
            {"name": "categorize_output", "type": "str"},
            {"name": "archive_output", "type": "str"},
        ],
    }
    result = _call(us, "build_branch", spec_json=json.dumps(spec))
    # Build is rejected because the staging error surfaces the coercion.
    assert result["status"] == "rejected"
    assert any("strang" in e for e in result["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# AC #3 — transactional patch_branch
# ─────────────────────────────────────────────────────────────────────────────


def test_patch_branch_batch_succeeds(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]

    changes = [
        {"op": "add_node", "node_id": "novelty_check",
         "display_name": "Novelty assessor",
         "prompt_template": "Rate: {capture_output}"},
        {"op": "add_state_field", "name": "novelty_score",
         "type": "float"},
        {"op": "remove_edge", "from": "capture", "to": "categorize"},
        {"op": "add_edge", "from": "capture", "to": "novelty_check"},
        {"op": "add_edge", "from": "novelty_check", "to": "categorize"},
    ]
    result = _call(us, "patch_branch", branch_def_id=bid,
                   changes_json=json.dumps(changes))
    assert result["status"] == "patched", result
    assert result["ops_applied"] == 5
    assert result["node_count"] == 4
    receipt = result["batch_receipt"]
    assert receipt["action"] == "patch_branch"
    assert receipt["operation_count"] == 5
    assert receipt["branch_def_id"] == bid
    assert receipt["node_count"] == 4
    assert receipt["source_code_approval"]["runnable"] is True

    got = _call(us, "get_branch", branch_def_id=bid)
    assert any(n["node_id"] == "novelty_check" for n in got["node_defs"])


def test_patch_branch_publishes_versioned_snapshot(comp_env):
    us, base = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]

    result = _call(
        us,
        "patch_branch",
        branch_def_id=bid,
        changes_json=json.dumps([
            {
                "op": "add_state_field",
                "name": "review_output",
                "type": "str",
            },
        ]),
    )

    assert result["status"] == "patched", result
    assert result["branch_version_id"]
    assert result["parent_version_id"]

    from workflow.branch_versions import get_branch_version

    parent = get_branch_version(base, result["parent_version_id"])
    version = get_branch_version(base, result["branch_version_id"])
    assert parent is not None
    assert version is not None
    assert parent.branch_version_id != version.branch_version_id
    assert version.parent_version_id == parent.branch_version_id
    assert parent.snapshot["branch_def_id"] == bid
    assert version.snapshot["branch_def_id"] == bid
    assert all(f["name"] != "review_output" for f in parent.snapshot["state_schema"])
    assert any(f["name"] == "review_output" for f in version.snapshot["state_schema"])


def test_patch_branch_rollback_on_any_op_failure(comp_env):
    """AC #3 — if op 3 is invalid, zero rows mutated. All errors reported."""
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]

    before = _call(us, "get_branch", branch_def_id=bid)
    before_node_count = len(before["node_defs"])

    changes = [
        {"op": "add_node", "node_id": "step_a",
         "display_name": "A", "prompt_template": "a"},
        {"op": "add_node", "node_id": "step_b",
         "display_name": "B", "prompt_template": "b"},
        {"op": "remove_node", "node_id": "does_not_exist"},  # op 2 fails
        {"op": "add_node", "node_id": "step_c",
         "display_name": "C", "prompt_template": "c"},
        {"op": "add_node", "node_id": "step_d",
         "display_name": "D", "prompt_template": "d"},
    ]
    result = _call(us, "patch_branch", branch_def_id=bid,
                   changes_json=json.dumps(changes))
    assert result["status"] == "rejected"
    assert "batch_receipt" not in result
    # Per-op errors include the op_index so clients can target the fix.
    err_indices = [e["op_index"] for e in result["errors"]]
    assert 2 in err_indices

    # Branch is unchanged on disk.
    after = _call(us, "get_branch", branch_def_id=bid)
    assert len(after["node_defs"]) == before_node_count


def test_patch_branch_validation_failure_reverts(comp_env):
    """Op-level success but validate() failure must still revert."""
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]

    # Add a node but don't wire it — validation will flag it as
    # unreachable. Expect rollback.
    changes = [
        {"op": "add_node", "node_id": "orphan",
         "display_name": "Orphan", "prompt_template": "?"},
    ]
    result = _call(us, "patch_branch", branch_def_id=bid,
                   changes_json=json.dumps(changes))
    assert result["status"] == "rejected"
    assert result["validation_errors"]

    # The orphan must NOT be persisted.
    after = _call(us, "get_branch", branch_def_id=bid)
    assert not any(n["node_id"] == "orphan" for n in after["node_defs"])


def test_patch_branch_rejects_unknown_op(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    result = _call(us, "patch_branch", branch_def_id=bid,
                   changes_json=json.dumps([{"op": "nonsense"}]))
    assert result["status"] == "rejected"


def test_patch_branch_requires_branch_id(comp_env):
    us, _ = comp_env
    result = _call(us, "patch_branch", changes_json="[]")
    assert result["status"] == "rejected"


def test_patch_branch_requires_changes_json(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    result = _call(us, "patch_branch", branch_def_id=built["branch_def_id"])
    assert result["status"] == "rejected"


# ─────────────────────────────────────────────────────────────────────────────
# AC #4 — one ledger entry per composite call
# ─────────────────────────────────────────────────────────────────────────────


def test_build_branch_writes_one_ledger_entry(comp_env):
    us, base = comp_env
    _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    actions = [e["action"] for e in ledger]
    # Exactly one build_branch entry — not three add_nodes + four
    # connect_nodes + four add_state_fields + one set_entry_point.
    assert actions.count("build_branch") == 1
    # No atomic actions should be in the ledger from this build.
    for atomic in ("add_node", "connect_nodes", "set_entry_point",
                   "add_state_field"):
        assert atomic not in actions


def test_patch_branch_writes_one_ledger_entry(comp_env):
    us, base = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    _call(us, "patch_branch", branch_def_id=bid,
          changes_json=json.dumps([
              {"op": "add_node", "node_id": "x",
               "display_name": "X", "prompt_template": "x"},
              {"op": "add_edge", "from": "capture", "to": "x"},
              {"op": "add_edge", "from": "x", "to": "categorize"},
              {"op": "remove_edge", "from": "capture", "to": "categorize"},
              {"op": "add_state_field", "name": "x_output", "type": "str"},
          ]))
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    patch_entries = [e for e in ledger if e["action"] == "patch_branch"]
    assert len(patch_entries) == 1


def test_rejected_build_does_not_ledger(comp_env):
    us, base = comp_env
    bad = {**RECIPE_SPEC, "entry_point": ""}
    _call(us, "build_branch", spec_json=json.dumps(bad))
    ledger_path = Path(base) / "ledger.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text("utf-8"))
    else:
        ledger = []
    assert not any(e["action"] == "build_branch" for e in ledger)


def test_rejected_patch_does_not_ledger(comp_env):
    us, base = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    _call(us, "patch_branch", branch_def_id=bid,
          changes_json=json.dumps([{"op": "nonsense"}]))
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    assert not any(e["action"] == "patch_branch" for e in ledger)


# ─────────────────────────────────────────────────────────────────────────────
# AC #5 — fine-grained actions still work unchanged (regression gate)
# ─────────────────────────────────────────────────────────────────────────────


def test_atomic_actions_still_work(comp_env):
    """Regression gate — atomic Phase 2 actions remain functional."""
    us, _ = comp_env
    bid = _call(us, "create_branch", name="Atomic only")["branch_def_id"]
    add = _call(us, "add_node", branch_def_id=bid,
                node_id="n1", display_name="N1",
                prompt_template="hello {x}")
    assert add["status"] == "added"
    _call(us, "connect_nodes", branch_def_id=bid,
          from_node="START", to_node="n1")
    _call(us, "connect_nodes", branch_def_id=bid,
          from_node="n1", to_node="END")
    _call(us, "set_entry_point", branch_def_id=bid, node_id="n1")
    _call(us, "add_state_field", branch_def_id=bid,
          field_name="x", field_type="str")
    validated = _call(us, "validate_branch", branch_def_id=bid)
    assert validated["valid"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Return shape compliance — tool_return_shapes.md
# ─────────────────────────────────────────────────────────────────────────────


def test_build_branch_text_channel_includes_ack_and_mermaid(comp_env):
    us, _ = comp_env
    result = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    assert "text" in result
    assert "Built branch" in result["text"]
    assert "```mermaid" in result["text"]


def test_patch_branch_text_channel_on_success(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    result = _call(us, "patch_branch",
                   branch_def_id=built["branch_def_id"],
                   changes_json=json.dumps([
                       {"op": "add_state_field",
                        "name": "extra", "type": "str"},
                   ]))
    assert "text" in result
    assert "Patched" in result["text"]


def test_build_branch_truncates_mermaid_above_12_nodes(comp_env):
    us, _ = comp_env
    # Build a 13-node linear chain.
    node_defs = [
        {"node_id": f"n{i}", "display_name": f"N{i}",
         "prompt_template": f"step {i}"}
        for i in range(13)
    ]
    edges = [{"from": "START", "to": "n0"}]
    edges += [
        {"from": f"n{i}", "to": f"n{i+1}"} for i in range(12)
    ]
    edges.append({"from": "n12", "to": "END"})
    spec = {
        "name": "Linear 13",
        "entry_point": "n0",
        "node_defs": node_defs,
        "edges": edges,
        "state_schema": [],
    }
    result = _call(us, "build_branch", spec_json=json.dumps(spec))
    assert result["status"] == "built"
    # Text notes the phone-legibility truncation explicitly.
    assert "12-node" in result["text"] or "structuredContent" in result["text"]


def test_unknown_action_catalog_lists_composite_actions(comp_env):
    us, _ = comp_env
    result = _call(us, "notarealaction")
    avail = result.get("available_actions", [])
    assert "build_branch" in avail
    assert "patch_branch" in avail
    assert "update_node" in avail


# ─────────────────────────────────────────────────────────────────────────────
# update_node (#45) — stable-id edits, version bump, ledger inherited
# ─────────────────────────────────────────────────────────────────────────────


def test_update_node_changes_prompt_template(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]

    upd = _call(us, "update_node", branch_def_id=bid, node_id="capture",
                prompt_template="NEW: {raw_recipe}")
    assert upd["status"] == "updated"
    assert upd["node_id"] == "capture"
    assert "prompt_template" in upd["changed_fields"]

    got = _call(us, "get_branch", branch_def_id=bid)
    capture = next(n for n in got["node_defs"] if n["node_id"] == "capture")
    assert capture["prompt_template"] == "NEW: {raw_recipe}"


def test_update_node_bumps_branch_version(comp_env):
    """AC: update_node bumps BranchDefinition.version so Phase 4 lineage
    can distinguish pre/post-edit runs."""
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]

    before = _call(us, "get_branch", branch_def_id=bid)
    assert before["version"] == 1

    upd = _call(us, "update_node", branch_def_id=bid, node_id="capture",
                display_name="Renamed capture")
    assert upd["version_before"] == 1
    assert upd["version_after"] == 2

    after = _call(us, "get_branch", branch_def_id=bid)
    assert after["version"] == 2


def test_update_node_preserves_node_id(comp_env):
    """Critical Phase 4 invariant — node_id survives the edit. Judgments
    keyed on node_id must resolve the same node before and after."""
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    _call(us, "update_node", branch_def_id=bid, node_id="capture",
          display_name="X", description="Y",
          prompt_template="Z: {raw_recipe}")

    got = _call(us, "get_branch", branch_def_id=bid)
    ids = {n["node_id"] for n in got["node_defs"]}
    assert "capture" in ids
    assert len([n for n in got["node_defs"]
                if n["node_id"] == "capture"]) == 1


def test_update_node_via_changes_json(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]

    changes = {"description": "Updated via JSON", "display_name": "Label"}
    upd = _call(us, "update_node", branch_def_id=bid, node_id="capture",
                changes_json=json.dumps(changes))
    assert upd["status"] == "updated"
    assert set(upd["changed_fields"]) == {"description", "display_name"}

    got = _call(us, "get_branch", branch_def_id=bid)
    capture = next(n for n in got["node_defs"] if n["node_id"] == "capture")
    assert capture["description"] == "Updated via JSON"
    assert capture["display_name"] == "Label"


def test_update_node_rejects_missing_node(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    result = _call(us, "update_node", branch_def_id=bid,
                   node_id="nonexistent", display_name="X")
    assert result["status"] == "rejected"
    assert "not found" in result["error"].lower()


def test_update_node_rejects_missing_branch(comp_env):
    us, _ = comp_env
    result = _call(us, "update_node", branch_def_id="deadbeef",
                   node_id="anything", display_name="X")
    assert result["status"] == "rejected"


def test_update_node_requires_ids(comp_env):
    us, _ = comp_env
    r1 = _call(us, "update_node", node_id="x", display_name="X")
    assert r1["status"] == "rejected"
    r2 = _call(us, "update_node", branch_def_id="foo", display_name="X")
    assert r2["status"] == "rejected"


def test_update_node_rejects_empty_update(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    result = _call(us, "update_node", branch_def_id=bid, node_id="capture")
    assert result["status"] == "rejected"
    assert "no fields" in result["error"].lower()


def test_update_node_rejects_both_template_and_source_code(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    result = _call(us, "update_node", branch_def_id=bid, node_id="capture",
                   prompt_template="a {x}",
                   source_code="def run(s): return {}")
    assert result["status"] == "rejected"
    assert "both" in result["error"].lower()


def test_update_node_switches_from_template_to_source_code(comp_env):
    """When source_code is set, prompt_template should be cleared (and
    vice versa) so the node has a single body."""
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    _call(us, "update_node", branch_def_id=bid, node_id="capture",
          source_code="def run(state): return {'capture_output': 'x'}")

    got = _call(us, "get_branch", branch_def_id=bid)
    capture = next(n for n in got["node_defs"] if n["node_id"] == "capture")
    assert capture["source_code"]
    assert capture["prompt_template"] == ""


def test_update_node_source_code_mutation_clears_prior_approval(comp_env):
    us, _ = comp_env
    built = _build_approved_source_branch(us, node_id="approved_update")
    bid = built["branch_def_id"]

    result = _call(
        us,
        "update_node",
        branch_def_id=bid,
        node_id="approved_update",
        source_code="def run(state): return {'answer': 3}",
    )

    assert result["status"] == "updated", result
    got = _call(us, "get_branch", branch_def_id=bid)
    node = next(n for n in got["node_defs"] if n["node_id"] == "approved_update")
    assert node["approved"] is False
    assert got["runnable"] is False
    assert got["unapproved_source_code_nodes"] == [{
        "node_id": "approved_update",
        "display_name": "Approved calc",
    }]


def test_update_node_rejects_invalid_phase(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    result = _call(us, "update_node", branch_def_id=bid, node_id="capture",
                   changes_json=json.dumps({"phase": "notaphase"}))
    assert result["status"] == "rejected"
    assert "phase" in result["error"].lower()


def test_update_node_updates_input_output_keys(comp_env):
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    upd = _call(us, "update_node", branch_def_id=bid, node_id="capture",
                input_keys="a,b,c", output_keys="out")
    assert upd["status"] == "updated"

    got = _call(us, "get_branch", branch_def_id=bid)
    capture = next(n for n in got["node_defs"] if n["node_id"] == "capture")
    assert capture["input_keys"] == ["a", "b", "c"]
    assert capture["output_keys"] == ["out"]


def test_update_node_writes_ledger(comp_env):
    us, base = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    _call(us, "update_node", branch_def_id=bid, node_id="capture",
          display_name="X")
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    actions = [e["action"] for e in ledger]
    assert "update_node" in actions


def test_update_node_rejected_call_does_not_ledger(comp_env):
    us, base = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    _call(us, "update_node", branch_def_id=bid, node_id="nonexistent",
          display_name="X")
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    update_entries = [e for e in ledger if e["action"] == "update_node"]
    assert update_entries == []


def test_update_node_text_channel_reports_changed_fields(comp_env):
    """tool_return_shapes.md compliance — one-line ack + preview."""
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    upd = _call(us, "update_node", branch_def_id=bid, node_id="capture",
                prompt_template="New prompt: {raw_recipe}")
    assert "text" in upd
    assert "Updated node" in upd["text"]
    assert "capture" in upd["text"]
    assert "prompt_template" in upd["text"]


def test_update_node_preserves_topology_and_state_schema(comp_env):
    """Editing one node must not change edges, other nodes, or state."""
    us, _ = comp_env
    built = _call(us, "build_branch", spec_json=json.dumps(RECIPE_SPEC))
    bid = built["branch_def_id"]
    before = _call(us, "get_branch", branch_def_id=bid)

    _call(us, "update_node", branch_def_id=bid, node_id="capture",
          display_name="Renamed")

    after = _call(us, "get_branch", branch_def_id=bid)
    assert after["graph"]["edges"] == before["graph"]["edges"]
    assert after["entry_point"] == before["entry_point"]
    assert [n["node_id"] for n in after["node_defs"]] == \
        [n["node_id"] for n in before["node_defs"]]
    assert after["state_schema"] == before["state_schema"]
