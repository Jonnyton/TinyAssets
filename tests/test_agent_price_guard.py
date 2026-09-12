"""The bounded HTTP shape admits tools, not transport/plugin/model overrides."""

import copy

import pytest

from tinyassets.providers.agent_chat_codec import encode_openai_chat_agent
from tinyassets.providers.discovery_protocols import discovery_protocol

CONTRACT = discovery_protocol("openrouter_user_models_v1")
CAPS = tuple((field, 0) for field in sorted(CONTRACT.price_components))


def body():
    return encode_openai_chat_agent(
        prompt="user", system="system", source_ref="source", model="opaque/new",
        tools=({"type": "function", "function": {
            "name": "current", "description": "", "parameters": {"type": "object"},
        }},),
    )[1]


def historical():
    value = body()
    value["messages"].extend([
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "exact-id", "type": "function", "function": {
                "name": "retired", "arguments": "{}",
            },
        }]},
        {"role": "tool", "tool_call_id": "exact-id",
         "content": '{"content":[{"type":"text","text":"known"}],'
                    '"structuredContent":null,"isError":false}'},
    ])
    return value


@pytest.mark.parametrize("make_body", [body, historical])
def test_tool_request_keeps_all_zero_price_caps_and_require_parameters(make_body):
    original = make_body()
    bounded = CONTRACT.constrain_inference(original, CAPS)
    assert bounded == {**original, "provider": {
        "max_price": {"prompt": "0", "completion": "0", "request": "0", "image": "0"},
        "require_parameters": True,
    }}
    assert "provider" not in original


@pytest.mark.parametrize("key,value", [
    ("plugins", []), ("provider", {}), ("models", ["other"]),
    ("stream", True), ("web_search_options", {}), ("tools", []),
    ("tool_choice", {"type": "function"}),
])
def test_agent_shape_cannot_expand_bounded_wire_surface(key, value):
    candidate = body()
    candidate[key] = value
    with pytest.raises(ValueError):
        CONTRACT.constrain_inference(candidate, CAPS)


@pytest.mark.parametrize("change", [
    "missing_result", "wrong_id", "duplicate_call", "bad_result", "system_in_history",
    "extra_assistant_field", "unknown_result_field", "non_object_message",
])
def test_malformed_or_incomplete_history_rejected(change):
    candidate = historical()
    if change == "missing_result":
        candidate["messages"].pop()
    elif change == "wrong_id":
        candidate["messages"][-1]["tool_call_id"] = "other"
    elif change == "duplicate_call":
        calls = candidate["messages"][-2]["tool_calls"]
        calls.append(copy.deepcopy(calls[0]))
    elif change == "bad_result":
        candidate["messages"][-1]["content"] = "not-json"
    elif change == "system_in_history":
        candidate["messages"][-2]["role"] = "system"
    elif change == "extra_assistant_field":
        candidate["messages"][-2]["audio"] = {}
    elif change == "unknown_result_field":
        candidate["messages"][-1]["url"] = "https://not-authorized.invalid"
    else:
        candidate["messages"][0] = None
    with pytest.raises(ValueError):
        CONTRACT.constrain_inference(candidate, CAPS)
