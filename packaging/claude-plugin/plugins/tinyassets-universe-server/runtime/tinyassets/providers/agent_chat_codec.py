"""Pure, private text/tool translation; not a registered provider or authority.

Each immutable round can be persisted by a future authoritative journal. This
module performs no inference, tool dispatch, retry, storage or model selection.
Legacy text codecs and full-agent eligibility deliberately remain unchanged.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from mcp.types import CallToolResult, Tool

from tinyassets.providers.protocol_encoders import (
    OPENAI_CHAT_PATH,
    ProtocolDecodeError,
    reported_model,
)

StopReason = Literal[
    "completed", "tool_requests", "truncated", "content_filter", "refusal", "unknown",
]
_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_CONTINUATION = frozenset({"role", "content", "tool_calls", "reasoning", "reasoning_details"})


def _bad(detail: str) -> ProtocolDecodeError:
    return ProtocolDecodeError("agent chat " + detail)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise _bad("JSON contains duplicate keys")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise _bad("JSON contains nonfinite numbers")


def _dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError):
        raise _bad("value is not JSON data") from None


def _object(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise _bad("JSON object string required")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        # JSON exponent overflow also becomes infinity without parse_constant.
        _dump(value)
    except (ValueError, TypeError, RecursionError):
        raise _bad("invalid JSON object") from None
    if not isinstance(value, dict):
        raise _bad("JSON object required")
    return value


def _identifier(value: Any, maximum: int = 256) -> bool:
    return (
        isinstance(value, str) and 0 < len(value) <= maximum
        and bool(value.strip()) and value.isprintable()
    )


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


@dataclass(frozen=True, slots=True)
class ToolRequest:
    call_id: str
    name: str
    arguments_json: str = field(repr=False)

    def arguments(self) -> dict[str, Any]:
        """Detached parsed arguments; never normalize the stored wire string."""
        return _object(self.arguments_json)


@dataclass(frozen=True, slots=True)
class AgentReply:
    stop: StopReason
    text: str | None = field(repr=False)
    refusal: str | None = field(repr=False)
    tool_requests: tuple[ToolRequest, ...]
    continuation_json: str = field(repr=False)
    dropped_fields: tuple[str, ...] = field(repr=False)
    source_ref: str
    requested_model: str
    reported_model: str
    raw_finish_reason: str = field(repr=False)
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    call_id: str
    result_json: str = field(repr=False)
    is_error: bool


@dataclass(frozen=True, slots=True)
class ToolRound:
    reply: AgentReply
    outcomes: tuple[ToolOutcome, ...]


def _calls(raw: Any, names: frozenset[str]) -> tuple[ToolRequest, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise _bad("tool calls must be a list")
    calls: list[ToolRequest] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"id", "type", "function"}:
            raise _bad("unsupported tool call shape")
        call_id = item["id"]
        fn = item["function"]
        if not _identifier(call_id) or call_id in seen or item["type"] != "function":
            raise _bad("invalid or duplicate tool call identity")
        if not isinstance(fn, dict) or set(fn) != {"name", "arguments"}:
            raise _bad("unsupported tool function shape")
        name, arguments = fn["name"], fn["arguments"]
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name not in names:
            raise _bad("tool name is not enabled")
        _object(arguments)
        calls.append(ToolRequest(call_id, name, arguments))
        seen.add(call_id)
    return tuple(calls)


def _assistant(message: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...], bool]:
    if message.get("role", "assistant") != "assistant":
        raise _bad("response message is not assistant")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise _bad("non-text assistant content is unsupported")
    result = {"role": "assistant", "content": content}
    if message.get("tool_calls"):
        result["tool_calls"] = message["tool_calls"]
    for name in ("reasoning", "reasoning_details"):
        value = message.get(name)
        if value is None:
            continue
        if name == "reasoning" and not isinstance(value, str):
            raise _bad("invalid reasoning continuation")
        if name == "reasoning_details" and (
            not isinstance(value, list) or any(not isinstance(item, dict) for item in value)
        ):
            raise _bad("invalid reasoning continuation")
        result[name] = value
    dropped = tuple(key for key in message if key not in _CONTINUATION)
    incompatible = any(message[key] not in (None, "", [], {}) for key in dropped)
    _dump(result)
    return result, dropped, incompatible


def decode_openai_chat_agent(
    response_body: Any, *, source_ref: str, requested_model: str, tool_names: frozenset[str],
) -> AgentReply:
    """Validate a complete response before exposing any requested tool."""
    if not _identifier(source_ref, 4096) or not _identifier(requested_model, 4096):
        raise _bad("source and requested model are required")
    if not isinstance(tool_names, frozenset) or any(
        not isinstance(name, str) or not _NAME.fullmatch(name) for name in tool_names
    ):
        raise _bad("invalid enabled tool names")
    if not isinstance(response_body, dict) or response_body.get("error") is not None:
        raise _bad("response unavailable")
    choices = response_body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise _bad("exactly one choice required")
    choice = choices[0]
    if choice.get("error") is not None or choice.get("finish_reason") == "error":
        raise _bad("choice unavailable")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise _bad("assistant message required")
    projection, dropped, incompatible = _assistant(message)
    calls = _calls(message.get("tool_calls"), tool_names)
    finish = choice.get("finish_reason")
    finish = finish if isinstance(finish, str) else ""
    refusal = message.get("refusal")
    if refusal is not None and not isinstance(refusal, str):
        raise _bad("invalid refusal field")
    refusal = refusal if refusal and refusal.strip() else None
    content = message.get("content")
    text = content if isinstance(content, str) and content.strip() else None
    stop: StopReason = "unknown"
    if calls and finish == "length":
        raise _bad("tool batch is incomplete")
    if refusal is not None:
        stop, text = "refusal", None
    elif finish == "content_filter":
        stop = "content_filter"
    elif finish == "length":
        stop = "truncated"
    elif calls and finish in {"stop", "tool_calls"} and not incompatible:
        stop = "tool_requests"
    elif not calls and finish == "stop" and text is not None and not any(
        message.get(key) not in (None, "", [], {}) for key in ("function_call", "audio")
    ):
        stop = "completed"
    elif not calls and finish == "tool_calls":
        raise _bad("tool finish without tool requests")
    usage = response_body.get("usage")

    def tokens(name: str) -> int | None:
        value = usage.get(name) if isinstance(usage, dict) else None
        return value if type(value) is int and value >= 0 else None

    return AgentReply(
        stop, text, refusal, calls if stop == "tool_requests" else (),
        _dump(projection), dropped, source_ref, requested_model, reported_model(response_body),
        finish, tokens("prompt_tokens"), tokens("completion_tokens"),
    )


def _definitions(definitions: Any) -> tuple[dict[str, Any], ...]:
    if not _sequence(definitions) or not definitions:
        raise _bad("tool definitions required")
    seen: set[str] = set()
    result = []
    for definition in definitions:
        if not isinstance(definition, dict) or set(definition) != {"type", "function"}:
            raise _bad("unsupported tool definition")
        fn = definition["function"]
        if definition["type"] != "function" or not isinstance(fn, dict) or set(fn) != {
            "name", "description", "parameters",
        }:
            raise _bad("unsupported function definition")
        name, description, parameters = fn["name"], fn["description"], fn["parameters"]
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
            raise _bad("invalid or duplicate tool definition name")
        if not isinstance(description, str) or len(description) > 65536:
            raise _bad("tool description is unsupported")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise _bad("object tool schema required")
        result.append(_object(_dump(definition)))
        seen.add(name)
    return tuple(result)


def tool_definitions(tools: Sequence[Tool]) -> tuple[dict[str, Any], ...]:
    """Project schemas from the validated engine-client inventory, no strict flag."""
    if not _sequence(tools) or any(not isinstance(tool, Tool) for tool in tools):
        raise _bad("MCP tool inventory required")
    return _definitions(tuple({"type": "function", "function": {
        "name": tool.name,
        "description": tool.description if tool.description is not None else "",
        "parameters": tool.inputSchema,
    }} for tool in tools))


def _result_projection(raw: dict[str, Any]) -> dict[str, Any]:
    if set(raw) != {"content", "structuredContent", "isError"}:
        raise _bad("unsupported tool result envelope")
    if type(raw["isError"]) is not bool or (
        raw["structuredContent"] is not None and not isinstance(raw["structuredContent"], dict)
    ):
        raise _bad("invalid tool result envelope")
    if not isinstance(raw["content"], list) or any(
        not isinstance(block, dict) or block.get("type") != "text"
        or not isinstance(block.get("text"), str)
        or set(block) - {"type", "text", "annotations"}
        for block in raw["content"]
    ):
        raise _bad("non-text tool content is unsupported")
    return _object(_dump(raw))


def tool_outcome(request: ToolRequest, result: CallToolResult) -> ToolOutcome:
    if not isinstance(request, ToolRequest) or not _identifier(request.call_id):
        raise _bad("tool request identity required")
    if not isinstance(result, CallToolResult):
        raise _bad("MCP tool result required")
    projected = {
        "content": [block.model_dump(
            mode="json", by_alias=True, exclude_none=True, include={"type", "text", "annotations"},
        ) for block in result.content],
        "structuredContent": result.structuredContent,
        "isError": result.isError,
    }
    return ToolOutcome(request.call_id, _dump(_result_projection(projected)), result.isError)


def encode_openai_chat_agent(
    *, prompt: str, system: str, source_ref: str, model: str,
    tools: Sequence[dict[str, Any]], rounds: Sequence[ToolRound] = (),
    temperature: float | None = None, max_tokens: int | None = None,
    tool_choice: Literal["auto", "none", "required"] = "auto",
) -> tuple[str, dict[str, Any]]:
    """Build a fresh same-source request from fully completed immutable rounds."""
    if not isinstance(prompt, str) or not isinstance(system, str):
        raise _bad("prompt and system must be text")
    if not _identifier(source_ref, 4096) or not _identifier(model, 4096):
        raise _bad("source and model are required")
    if tool_choice not in ("auto", "none", "required"):
        raise _bad("unsupported tool choice")
    definitions = _definitions(tools)
    names = frozenset(item["function"]["name"] for item in definitions)
    if not _sequence(rounds):
        raise _bad("completed rounds required")
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    seen: set[str] = set()
    for completed in rounds:
        if not isinstance(completed, ToolRound) or not isinstance(completed.reply, AgentReply):
            raise _bad("invalid completed round")
        reply = completed.reply
        if reply.stop != "tool_requests" or (reply.source_ref, reply.requested_model) != (
            source_ref, model,
        ):
            raise _bad("continuation source or state mismatch")
        assistant = _object(reply.continuation_json)
        projection, dropped, _ = _assistant(assistant)
        requests = _calls(assistant.get("tool_calls"), names)
        if dropped or not requests or requests != reply.tool_requests:
            raise _bad("continuation does not match tool requests")
        if not isinstance(completed.outcomes, tuple) or len(requests) != len(completed.outcomes):
            raise _bad("tool result count mismatch")
        messages.append(projection)
        for request, outcome in zip(requests, completed.outcomes):
            if request.call_id in seen or not isinstance(outcome, ToolOutcome) or (
                outcome.call_id != request.call_id or type(outcome.is_error) is not bool
            ):
                raise _bad("tool result correlation mismatch")
            result = _result_projection(_object(outcome.result_json))
            if result["isError"] != outcome.is_error:
                raise _bad("tool result error flag mismatch")
            messages.append({"role": "tool", "tool_call_id": outcome.call_id,
                             "content": outcome.result_json})
            seen.add(request.call_id)
    body: dict[str, Any] = {
        "model": model, "messages": messages, "tools": list(definitions),
        "tool_choice": tool_choice,
    }
    if temperature is not None:
        try:
            valid_temperature = type(temperature) in (float, int) and math.isfinite(temperature)
        except OverflowError:
            valid_temperature = False
        if not valid_temperature:
            raise _bad("invalid temperature")
        body["temperature"] = temperature
    if max_tokens is not None:
        if type(max_tokens) is not int or max_tokens < 1:
            raise _bad("invalid output token cap")
        body["max_tokens"] = max_tokens
    return OPENAI_CHAT_PATH, body
