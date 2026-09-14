"""Finite work allowance, without adding author-repair knobs or tool permission."""

import json
import sqlite3

import pytest

from tests.test_run_provider_session import _branch, _run_branch
from tests.test_work_model_selection import http_wire  # noqa: F401 - pytest fixture
from tinyassets.foreground_run_provider import _work_invocation_allowance
from tinyassets.provider_assignment_manifest import ModelAccess
from tinyassets.storage.provider_work_authority import db_path


def snapshot(*, agent=False):
    return {"node_defs": [{
        "node_id": "step", "prompt_template": "Do the work", "model_hint": "writer",
        "tools_allowed": ["universe_self"] if agent else [],
    }]}


@pytest.mark.parametrize("minimum,ceiling", [(1, 1), (1, 8), (3, 8), (12, 12)])
@pytest.mark.parametrize("agent", [False, True])
def test_existing_ceiling_is_shared_only_by_opted_in_work(minimum, ceiling, agent):
    assert _work_invocation_allowance(
        snapshot(agent=agent), minimum=minimum, ceiling=ceiling,
    ) == (ceiling if agent else minimum)


@pytest.mark.parametrize("minimum,ceiling", [(0, 10), (2, 1), (1, 0), (True, 3), (1, True)])
@pytest.mark.parametrize("agent", [False, True])
def test_invalid_or_infeasible_budget_cannot_enable_rounds(minimum, ceiling, agent):
    with pytest.raises(PermissionError, match="allowance"):
        _work_invocation_allowance(snapshot(agent=agent), minimum=minimum, ceiling=ceiling)


def test_other_tools_and_mutable_inputs_cannot_request_agent_allowance():
    branch = snapshot()
    branch["inputs"] = {"universe_self": True, "max_agent_rounds": 100}
    branch["node_defs"][0]["tools_allowed"] = ["read_page"]
    assert _work_invocation_allowance(branch, minimum=1, ceiling=20) == 1


def test_invalid_agent_subject_does_not_gain_allowance():
    branch = snapshot(agent=True)
    branch["node_defs"].append(snapshot()["node_defs"][0])
    with pytest.raises(ValueError, match="requires_one_prompt_node"):
        _work_invocation_allowance(branch, minimum=2, ceiling=20)


@pytest.mark.parametrize("agent", [False, True])
@pytest.mark.parametrize("open_provider", [False, True])
@pytest.mark.usefixtures("http_wire")
def test_actual_foreground_receipt_uses_existing_binding_ceiling(
    tmp_path, monkeypatch, authenticate_request, agent, open_provider,
):
    # Exercise admission only for agent work. Its current tool-route refusal is
    # expected here; this test does not claim the unimplemented tool loop works.
    branch = _branch(node_count=1)
    if agent:
        branch.node_defs[0].tools_allowed = ["universe_self"]
    _run_branch(
        tmp_path, monkeypatch, authenticate_request, branch, open_provider=open_provider,
        model_access=ModelAccess("discovered") if open_provider else None,
    )
    with sqlite3.connect(db_path(tmp_path)) as conn:
        receipts = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_work_receipts",
        )]
        bindings = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_work_bindings",
        )]
    assert len(receipts) == 1
    receipt = receipts[0]
    if open_provider:
        assert receipt["authority_scope"] == "manifest" and receipt["binding_id"] is None
        assert len(bindings) == 1
        binding = bindings[0]
    else:
        binding = next(b for b in bindings if b["binding_id"] == receipt["binding_id"])
    # Open-provider fixture supplies a policy (three compiler retry slots).
    assert receipt["max_invocations"] == (
        binding["max_invocations"] if agent else 3 if open_provider else 1
    )
    assert receipt["max_tokens"] == binding["max_tokens"]
    assert receipt["max_cost_microunits"] == binding["max_cost_microunits"]
