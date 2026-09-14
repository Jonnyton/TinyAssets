"""Frozen cbe36655 agent envelope functions for differential tests only."""

import math
from collections.abc import Sequence
from typing import Any, Literal

from tinyassets.providers.agent_chat_codec import (
    AgentReply,
    CapturedToolRound,
    ToolOutcome,
    ToolRound,
    _assistant,
    _bad,
    _calls,
    _definitions,
    _dump,
    _identifier,
    _object,
    _result_projection,
    _sequence,
    reply_state,
    validate_reply_context,
)
from tinyassets.providers.protocol_encoders import OPENAI_CHAT_PATH, reported_model


def decode_openai_chat_agent(
    response_body: Any, *, source_ref: str, requested_model: str, tool_names: frozenset[str],
) -> AgentReply:
    """Validate a complete response before exposing any requested tool."""
    validate_reply_context(source_ref, requested_model, tool_names)
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
    stop, text, refusal = reply_state(
        message, finish=finish, calls=calls, incompatible=incompatible,
    )
    usage = response_body.get("usage")

    def tokens(name: str) -> int | None:
        value = usage.get(name) if isinstance(usage, dict) else None
        return value if type(value) is int and value >= 0 else None

    return AgentReply(
        stop, text, refusal, calls if stop == "tool_requests" else (),
        _dump(projection), dropped, source_ref, requested_model, reported_model(response_body),
        finish, tokens("prompt_tokens"), tokens("completion_tokens"),
    )


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


def encode_openai_chat_agent_portable(
    *, prompt: str, system: str, source_ref: str, model: str,
    tools: Sequence[dict[str, Any]], history: Sequence[CapturedToolRound] = (),
    temperature: float | None = None, max_tokens: int | None = None,
    tool_choice: Literal["auto", "none", "required"] = "auto",
) -> tuple[str, dict[str, Any]]:
    """Render known results across selections without carrying foreign reasoning.

    Historical inventories validate historical calls, never today's permission
    to execute them. Wire identities are local to each completed tool batch.
    The caller must still admit every new inference and tool dispatch.
    """
    path, body = encode_openai_chat_agent(
        prompt=prompt, system=system, source_ref=source_ref, model=model,
        tools=tools, temperature=temperature, max_tokens=max_tokens,
        tool_choice=tool_choice,
    )
    if not _sequence(history):
        raise _bad("captured completed history required")
    for captured in history:
        if not isinstance(captured, CapturedToolRound) or not isinstance(
            captured.round.reply, AgentReply,
        ):
            raise _bad("invalid captured history")
        reply = captured.round.reply
        # Reuse the strict single-source validator for ONE historical batch.
        # It checks completeness, exact arguments/results and wire correlation;
        # its per-request ID set must not span independent historical rounds.
        _, historical = encode_openai_chat_agent(
            prompt="", system="", source_ref=reply.source_ref,
            model=reply.requested_model,
            tools=_object(captured.tools_json).get("tools"),
            rounds=(captured.round,),
        )
        messages = historical["messages"][1:]
        if (reply.source_ref, reply.requested_model) != (source_ref, model):
            messages[0] = {
                key: value for key, value in messages[0].items()
                if key in {"role", "content", "tool_calls"}
            }
        body["messages"].extend(messages)
    return path, body
