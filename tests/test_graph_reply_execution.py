"""Only an exact direct reply writer may supply single-model attribution."""

from copy import deepcopy

import pytest


def proof():
    snapshot = {"node_defs": [
        {"node_id": "angle", "prompt_template": "research", "output_keys": ["angle"]},
        {"node_id": "synth", "prompt_template": "synthesise", "output_keys": ["reply"]},
    ], "state_schema": [{"name": "reply", "type": "str"}]}
    receipt = {"provider": "owned", "model": "actual", "model_status": "reported"}
    events = [
        {"node_id": "angle", "status": "ran", "detail": {
            "response": "research", "execution": {**receipt, "provider": "other"}}},
        {"node_id": "synth", "status": "ran", "detail": {
            "response": "final answer", "execution": receipt}},
    ]
    return snapshot, events, receipt


def test_unique_synthesis_response_uses_its_own_observation_not_first_graph_call():
    from tinyassets.providers.graph_reply_execution import direct_reply_execution

    snapshot, events, receipt = proof()
    assert direct_reply_execution(snapshot, "reply", "final answer", events) == receipt


@pytest.mark.parametrize("change", [
    "combined", "reducer", "repeat", "different_reply", "multi_output", "configured_only",
    "missing", "bad_receipt", "aliased_reuse",
])
def test_ambiguous_or_unproven_output_stays_unknown(change):
    from tinyassets.providers.graph_reply_execution import direct_reply_execution

    snapshot, events, _ = proof()
    if change == "combined":
        snapshot["node_defs"].append({"node_id": "combine", "source_code": "pass",
                                      "output_keys": ["reply"]})
    elif change == "reducer":
        snapshot["state_schema"][0]["reducer"] = "append"
    elif change == "repeat":
        events.append(deepcopy(events[-1]))
    elif change == "different_reply":
        events[-1]["detail"]["response"] = "intermediate reply"
    elif change == "multi_output":
        snapshot["node_defs"][-1]["output_keys"].append("extra")
    elif change == "configured_only":
        events[-1]["detail"] = {"response": "final answer", "provider_model": "alias"}
    elif change == "missing":
        events.pop()
    elif change == "bad_receipt":
        events[-1]["detail"]["execution"]["model_status"] = "selected"
    elif change == "aliased_reuse":
        snapshot["graph_nodes"] = [{"id": "first", "node_def_id": "synth"},
                                   {"id": "second", "node_def_id": "synth"}]
    assert direct_reply_execution(snapshot, "reply", "final answer", events) is None
