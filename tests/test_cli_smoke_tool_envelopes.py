"""The startup probe must follow wire shape, not a compiled model list."""

import pytest

from scripts.codex_cli_smoke import request_tool_roots


@pytest.mark.parametrize("envelope", ["classic", "lite"])
def test_nested_tool_specs_survive_both_encodings(envelope):
    specs = [{"type": "namespace", "name": "functions", "tools": [
        {"type": "custom", "name": "exec", "description": "fixture"},
    ]}]
    request = ({"tools": specs} if envelope == "classic" else {
        "input": [{"type": "additional_tools", "tools": specs}],
    })
    assert request_tool_roots(request) == specs


def test_both_envelopes_are_inspected_without_dropping_either():
    direct = {"type": "function", "name": "read_graph"}
    nested = {"type": "function", "name": "exec_command"}
    assert request_tool_roots({
        "tools": [direct], "input": [{"type": "additional_tools", "tools": [nested]}],
    }) == [direct, nested]


@pytest.mark.parametrize("payload", [
    {}, {"tools": []}, {"tools": None}, {"input": "invalid"},
    {"input": [{"type": "additional_tools"}]},
    {"input": [{"type": "additional_tools", "tools": {}}]},
    {"input": [{"type": "message", "tools": [{"name": "not-a-tool-spec"}]}]},
])
def test_absent_or_malformed_tools_fail_loud(payload):
    with pytest.raises(ValueError):
        request_tool_roots(payload)
