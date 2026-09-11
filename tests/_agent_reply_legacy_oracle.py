"""Frozen d5ef5c5d reply decoder/loader: differential spec, never production code."""

from typing import Any

from tinyassets.providers import agent_chat_codec as codec
from tinyassets.providers.agent_chat_codec import (
    _NAME,
    AgentReply,
    StopReason,
    _assistant,
    _bad,
    _calls,
    _dump,
    _identifier,
)
from tinyassets.providers.protocol_encoders import reported_model
from tinyassets.storage.agent_turn_records import (
    STOP_STATE,
    RoundInput,
    document,
    fields,
    integer,
    invalid,
)


def legacy_decode(
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


def legacy_load_reply(raw: str, candidate: RoundInput) -> codec.AgentReply:
    value = fields(document(raw), {"version", *codec.AgentReply.__dataclass_fields__})
    if (value["source_ref"], value["requested_model"]) != (candidate.source_ref, candidate.model):
        raise invalid()
    for name in ("input_tokens", "output_tokens"):
        if value[name] is not None:
            integer(value[name])
    if not isinstance(value["reported_model"], str) or (
        value["reported_model"] and not value["reported_model"].strip()
    ):
        raise invalid()
    if value["stop"] not in STOP_STATE or not isinstance(value["raw_finish_reason"], str):
        raise invalid()
    if not isinstance(value["dropped_fields"], list) or any(
        not isinstance(key, str) for key in value["dropped_fields"]
    ):
        raise invalid()
    assistant = document(value["continuation_json"])
    projection, dropped, _ = codec._assistant(assistant)
    if dropped or projection != assistant:
        raise invalid()
    calls = codec._calls(assistant.get("tool_calls"), candidate.tool_names())
    if not isinstance(value["tool_requests"], list):
        raise invalid()
    requests = []
    for call in value["tool_requests"]:
        if (
            not isinstance(call, dict)
            or call.keys() != codec.ToolRequest.__dataclass_fields__.keys()
        ):
            raise invalid()
        requests.append(codec.ToolRequest(**call))
    if tuple(requests) != (calls if value["stop"] == "tool_requests" else ()):
        raise invalid()
    message = {**assistant, "refusal": value["refusal"]}
    decoded = legacy_decode(
        {
            "choices": [{"message": message, "finish_reason": value["raw_finish_reason"]}],
            "model": value["reported_model"],
            "usage": {
                "prompt_tokens": value["input_tokens"],
                "completion_tokens": value["output_tokens"],
            },
        },
        source_ref=candidate.source_ref,
        requested_model=candidate.model,
        tool_names=candidate.tool_names(),
    )
    # Unknown non-empty dropped fields were intentionally not retained by the codec.
    # Their absence may improve a re-decode, but must never promote the held snapshot.
    held_unknown = value["stop"] == "unknown" and bool(value["dropped_fields"])
    if (decoded.stop != value["stop"] and not held_unknown) or (
        decoded.text != value["text"] or decoded.refusal != value["refusal"]
    ):
        raise invalid()
    values = {key: val for key, val in value.items() if key != "version"}
    values["tool_requests"] = tuple(requests)
    values["dropped_fields"] = tuple(value["dropped_fields"])
    return codec.AgentReply(**values)

