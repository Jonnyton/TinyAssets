"""Installed HTTP envelopes around the canonical text/tool message capability.

This finite data adapter owns paths and outer field locations, not credentials,
model admission, tools, spending or retry. It is deliberately NOT an owner-
authorable source-contract extension or a general translator for unknown CLIs.
Inner messages still require the installed canonical text/tool representation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from tinyassets.providers.agent_chat_codec import (
    AgentReply,
    _bad,
    build_portable_agent_body,
    decode_agent_message,
    validate_reply_context,
)
from tinyassets.providers.discovery_catalogue import Pointer

_REQUEST_FIELDS = frozenset({
    "model", "messages", "tools", "tool_choice", "temperature", "max_tokens",
})
_RESPONSE_FIELDS = frozenset({
    "choices", "error", "model", "input_tokens", "output_tokens",
})
_CHOICE_FIELDS = frozenset({"message", "finish", "error"})
_MALFORMED = object()


def _closed(value: Any, names: frozenset[str]) -> dict:
    if type(value) is not dict or value.keys() != names:
        raise ValueError("unsupported installed agent envelope fields")
    return value


def _pointers(value: Any, names: frozenset[str]) -> tuple[tuple[str, Pointer], ...]:
    result = []
    for name, pointer in _closed(value, names).items():
        compiled = Pointer.compile(pointer)
        if not compiled.tokens:
            raise ValueError("agent envelope selector must select a field")
        result.append((name, compiled))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class AgentWireShape:
    path: str
    request_fields: tuple[tuple[str, str], ...]
    response_fields: tuple[tuple[str, Pointer], ...]
    choice_fields: tuple[tuple[str, Pointer], ...]

    @classmethod
    def compile(cls, document: Any) -> AgentWireShape:
        """Compile closed, bounded installed data; no evaluated callbacks."""
        _closed(document, frozenset({"path", "request", "response", "choice"}))
        path = document["path"]
        if (type(path) is not str or len(path) > 512
                or not re.fullmatch(r"/[A-Za-z0-9_/-]+", path) or "//" in path):
            raise ValueError("agent envelope path must be a relative request path")
        fields = _closed(document["request"], _REQUEST_FIELDS)
        values = list(fields.values())
        if any(type(value) is not str or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]{0,63}", value,
        ) for value in values) or len(set(values)) != len(values):
            raise ValueError("agent request field mapping must be unique names")
        return cls(
            path, tuple(fields.items()),
            _pointers(document["response"], _RESPONSE_FIELDS),
            _pointers(document["choice"], _CHOICE_FIELDS),
        )

    def wrap_body(self, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Wrap an already validated canonical body, preserving field order."""
        if type(body) is not dict or body.keys() - _REQUEST_FIELDS:
            raise _bad("unsupported request fields")
        fields = dict(self.request_fields)
        return self.path, {fields[name]: value for name, value in body.items()}

    def encode(self, **kwargs) -> tuple[str, dict[str, Any]]:
        return self.wrap_body(build_portable_agent_body(**kwargs))

    def decode(
        self, response_body: Any, *, source_ref: str, requested_model: str,
        tool_names: frozenset[str],
    ) -> AgentReply:
        """Reject envelope failures before canonical validation exposes tools."""
        validate_reply_context(source_ref, requested_model, tool_names)
        root = dict(self.response_fields)
        if (not isinstance(response_body, dict)
                or root["error"].read(response_body, malformed=_MALFORMED) is not None):
            raise _bad("response unavailable")
        choices = root["choices"].read(response_body)
        if (not isinstance(choices, list) or len(choices) != 1
                or not isinstance(choices[0], dict)):
            raise _bad("exactly one choice required")
        choice = choices[0]
        fields = dict(self.choice_fields)
        if fields["error"].read(choice, malformed=_MALFORMED) is not None:
            raise _bad("choice unavailable")
        return decode_agent_message(
            fields["message"].read(choice), finish=fields["finish"].read(choice),
            receipt=root["model"].read(response_body),
            input_tokens=root["input_tokens"].read(response_body),
            output_tokens=root["output_tokens"].read(response_body),
            source_ref=source_ref, requested_model=requested_model, tool_names=tool_names,
        )


@cache
def installed_agent_wire() -> AgentWireShape:
    """CWD-independent immutable installed capability; not connection metadata."""
    document = json.loads(Path(__file__).with_name("agent_wire_shape.json").read_text("utf-8"))
    return AgentWireShape.compile(document)
