"""Private, versioned journal snapshots. Progress is data, never execution authority."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from mcp.types import CallToolResult, ContentBlock
from pydantic import TypeAdapter

from tinyassets.providers import agent_chat_codec as codec

MAX_INT = 2**63 - 1
STATES = frozenset(
    {
        "ready",
        "abandoned",
        "inference_started",
        "tools_pending",
        "completed",
        "held_refusal",
        "held_truncated",
        "held_filter",
        "held_unknown_stop",
        "held_transport",
        "held_tool_not_sent",
        "held_tool_unknown",
        "held_unsupported_result",
    }
)
STOP_STATE = {
    "completed": "completed",
    "tool_requests": "tools_pending",
    "refusal": "held_refusal",
    "truncated": "held_truncated",
    "content_filter": "held_filter",
    "unknown": "held_unknown_stop",
}
_CONTENT = TypeAdapter(ContentBlock)


def invalid() -> ValueError:
    return ValueError("invalid agent turn snapshot")


def integer(value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_INT:
        raise invalid()
    return value


def identity(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or (
            value != value.strip()
            or not value.isprintable()
            or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
        )
    ):
        raise invalid()
    return value


def dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (ValueError, TypeError, RecursionError):
        raise invalid() from None


def document(raw: str) -> dict:
    # Codec strict JSON rejects duplicate keys, nonfinite constants and exponent overflow.
    return codec._object(raw)


def fields(value: Any, names: set[str]) -> dict:
    if not isinstance(value, dict) or value.keys() != names or value.get("version") != 1:
        raise invalid()
    if type(value["version"]) is not int:
        raise invalid()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class RoundInput:
    source_ref: str
    model: str
    tools_json: str
    binding_id: str
    reservation_id: str
    binding_generation: int
    binding_digest: str
    request_digest: str

    def canonical_json(self) -> str:
        for name in ("source_ref", "model", "binding_id", "reservation_id"):
            identity(getattr(self, name))
        integer(self.binding_generation, minimum=1)
        for value in (self.binding_digest, self.request_digest):
            if (
                not isinstance(value, str)
                or not value.startswith("sha256:")
                or (len(value) != 71 or any(c not in "0123456789abcdef" for c in value[7:]))
            ):
                raise invalid()
        tools = document(self.tools_json)
        fields(tools, {"version", "tools"})
        codec._definitions(tools["tools"])
        return dump({"version": 1, **asdict(self)})

    @classmethod
    def from_json(cls, raw: str) -> RoundInput:
        value = fields(document(raw), {"version", *cls.__dataclass_fields__})
        result = cls(**{key: val for key, val in value.items() if key != "version"})
        if result.canonical_json() != raw:
            raise invalid()
        return result

    def tool_names(self) -> frozenset[str]:
        return frozenset(t["function"]["name"] for t in document(self.tools_json)["tools"])


def reply_json(reply: codec.AgentReply, candidate: RoundInput) -> str:
    if type(reply) is not codec.AgentReply:
        raise invalid()
    raw = dump({"version": 1, **asdict(reply)})
    if load_reply(raw, candidate) != reply:
        raise invalid()
    return raw


def load_reply(raw: str, candidate: RoundInput) -> codec.AgentReply:
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
    decoded = codec.decode_openai_chat_agent(
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


def result_json(result: CallToolResult) -> tuple[str, str, bool]:
    if not isinstance(result, CallToolResult):
        raise invalid()
    # Preserve the standard content union, not the text-only inference projection.
    content = [
        _CONTENT.validate_python(block).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude={"meta"},
        )
        for block in result.content
    ]
    raw = dump(
        {
            "version": 1,
            "content": content,
            "structuredContent": result.structuredContent,
            "isError": result.isError,
        }
    )
    return raw, *load_result(raw)[1:]


def load_result(raw: str) -> tuple[CallToolResult, str, bool]:
    value = fields(document(raw), {"version", "content", "structuredContent", "isError"})
    if (
        not isinstance(value["content"], list)
        or type(value["isError"]) is not bool
        or (
            value["structuredContent"] is not None
            and not isinstance(value["structuredContent"], dict)
        )
    ):
        raise invalid()
    content = [_CONTENT.validate_python(block) for block in value["content"]]
    for source, parsed in zip(value["content"], content):
        if (
            parsed.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"meta"})
            != source
        ):
            raise invalid()
    kind = "text_only" if all(block.type == "text" for block in content) else "non_text"
    return (
        CallToolResult(
            content=content, structuredContent=value["structuredContent"], isError=value["isError"]
        ),
        kind,
        value["isError"],
    )


@dataclass(frozen=True, slots=True, repr=False)
class ToolSnapshot:
    ordinal: int
    request: codec.ToolRequest
    state: str
    result_json: str | None = field(repr=False)
    content_kind: str | None
    is_error: bool | None


@dataclass(frozen=True, slots=True, repr=False)
class RoundSnapshot:
    ordinal: int
    candidate: RoundInput
    state: str
    reply: codec.AgentReply | None
    tools: tuple[ToolSnapshot, ...]
    cost_microusd: int | None


@dataclass(frozen=True, slots=True, repr=False)
class TurnSnapshot:
    turn_id: str
    generation: int
    state: str
    prompt: str
    system: str
    policy_generation: int | None
    created_at: str
    rounds: tuple[RoundSnapshot, ...]


@dataclass(frozen=True, slots=True)
class Transition:
    status: str
    snapshot: TurnSnapshot = field(repr=False)
