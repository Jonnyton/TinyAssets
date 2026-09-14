"""Exact single-inference data and usage accounting, no provider calls."""

from dataclasses import FrozenInstanceError

import pytest

from tinyassets.providers.agent_inference import AgentInferenceRequest, openrouter_usage_cost


@pytest.mark.parametrize(
    "wire,expected",
    [
        ('{"usage":{"cost":0}}', 0),
        ('{"usage":{"cost":1.2345671}}', 1234568),
        ('{"usage":{"cost":0.00000000001}}', 1),
        ('{"usage":{"cost":1e-9999999}}', 1),
        ('{"usage":{"cost":9223372036854.775807}}', 2**63 - 1),
        ('{"usage":{"cost":9223372036854.775808}}', None),
        ('{"usage":{"cost":-0.1}}', None),
        ('{"usage":{"cost":true}}', None),
        ('{"usage":{"cost":"0"}}', None),
        ('{"usage":{"cost":NaN}}', None),
        ('{"usage":{"cost":Infinity}}', None),
        ('{"usage":{"cost":1e9999999}}', None),
        ('{"usage":{"cost":0,"cost":1}}', None),
        ('{"usage":{"upstream_inference_cost":0}}', None),
        ("{}", None),
        ("not-json", None),
    ],
)
def test_documented_account_charge_is_conservative_and_unknown_is_not_zero(wire, expected):
    assert openrouter_usage_cost(wire) == expected


def test_request_inventory_is_immutable_and_detached():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read",
                "description": "",
                "parameters": {"type": "object"},
            },
        }
    ]
    request = AgentInferenceRequest(tools=tools)
    tools[0]["function"]["name"] = "changed"
    assert request.tools()[0]["function"]["name"] == "read"
    with pytest.raises(FrozenInstanceError):
        request.tools_json = "{}"
    with pytest.raises(ValueError):
        AgentInferenceRequest(tools=tools, history=[])
