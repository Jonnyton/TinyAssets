"""Portable completed history requirements, without model or tool execution."""

import json

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from tinyassets.providers import agent_chat_codec as codec


def tools(name="old_tool"):
    return codec.tool_definitions((Tool(name=name, inputSchema={"type": "object"}),))


def completed(source="source-a", model="model-a", call_id="reused"):
    reply = codec.decode_openai_chat_agent(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "exact assistant text",
                        "reasoning": "private source reasoning",
                        "reasoning_details": [
                            {"type": "encrypted", "data": "opaque-source-signature"}
                        ],
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": "old_tool",
                                    "arguments": ' {"exact": "🪐"} ',
                                },
                            }
                        ],
                    },
                }
            ]
        },
        source_ref=source,
        requested_model=model,
        tool_names=frozenset({"old_tool"}),
    )
    outcome = codec.tool_outcome(
        reply.tool_requests[0],
        CallToolResult(
            content=[TextContent(type="text", text=" exact\nknown result 🪐 ")],
            isError=True,
        ),
    )
    return codec.ToolRound(reply, (outcome,))


def render(history, *, source="source-b", model="model-b", current_tools=None):
    captured = tuple(codec.CapturedToolRound(round=item, tools=tools()) for item in history)
    return codec.encode_openai_chat_agent_portable(
        prompt=" exact\nuser input ",
        system="system\n",
        source_ref=source,
        model=model,
        tools=tools() if current_tools is None else current_tools,
        history=captured,
    )[1]


@pytest.mark.parametrize("source,model", [("source-b", "model-a"), ("source-a", "model-b")])
def test_switch_preserves_known_results_but_excludes_source_reasoning(source, model):
    old = completed()
    body = render((old,), source=source, model=model)
    assistant, tool = body["messages"][2:]
    assert assistant == {
        "role": "assistant",
        "content": "exact assistant text",
        "tool_calls": json.loads(old.reply.continuation_json)["tool_calls"],
    }
    assert tool == {
        "role": "tool",
        "tool_call_id": "reused",
        "content": old.outcomes[0].result_json,
    }
    assert "private source reasoning" not in json.dumps(body)
    assert "opaque-source-signature" not in json.dumps(body)
    assert body["model"] == model


def test_same_source_model_keeps_supported_continuation():
    body = render((completed(),), source="source-a", model="model-a")
    assert body["messages"][2]["reasoning"] == "private source reasoning"


def test_retired_tool_result_does_not_enable_the_retired_tool():
    old = completed()
    body = render((old,), current_tools=tools("new_tool"))
    assert body["tools"] == list(tools("new_tool"))
    assert body["messages"][2]["tool_calls"][0]["function"]["name"] == "old_tool"
    assert body["messages"][3]["content"] == old.outcomes[0].result_json


def test_wire_id_reuse_is_correlated_per_batch_not_rewritten():
    first, second = completed(), completed()
    body = render((first, second))
    assert [
        message["tool_call_id"] for message in body["messages"] if message["role"] == "tool"
    ] == [
        "reused",
        "reused",
    ]
    assert len(body["messages"]) == 6


def test_history_schema_and_results_are_validated_separately_from_current_inventory():
    captured = codec.CapturedToolRound(round=completed(), tools=tools("different_historical_tool"))
    with pytest.raises(ValueError):
        codec.encode_openai_chat_agent_portable(
            prompt="user",
            system="",
            source_ref="source-b",
            model="model-b",
            tools=tools("new_tool"),
            history=(captured,),
        )


def test_captured_inventory_is_detached_from_mutable_input():
    inventory = tools()
    captured = codec.CapturedToolRound(round=completed(), tools=inventory)
    inventory[0]["function"]["name"] = "changed_after_capture"
    body = codec.encode_openai_chat_agent_portable(
        prompt="user",
        system="",
        source_ref="source-b",
        model="model-b",
        tools=tools("new_tool"),
        history=(captured,),
    )[1]
    assert body["messages"][1]["tool_calls"][0]["function"]["name"] == "old_tool"
    assert "changed_after_capture" not in captured.tools_json


@pytest.mark.parametrize("history", [None, "not history", (completed(),)])
def test_uncaptured_history_rejected(history):
    with pytest.raises(ValueError):
        codec.encode_openai_chat_agent_portable(
            prompt="user",
            system="",
            source_ref="source-b",
            model="model-b",
            tools=tools(),
            history=history,
        )


def test_incomplete_historical_results_cannot_be_used_for_fallback():
    old = completed()
    with pytest.raises(ValueError):
        render((codec.ToolRound(old.reply, ()),))
