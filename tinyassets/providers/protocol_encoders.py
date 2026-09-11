"""Protocol encoders for the ``api_key_http`` compute executor.

Pure request/response translation between TinyAssets' provider contract
(``prompt`` + ``system`` + :class:`~tinyassets.providers.base.ModelConfig` ->
:class:`~tinyassets.providers.base.ProviderResponse`) and the two HTTP protocol
shapes an open compute provider speaks:

- ``openai_chat`` — the OpenAI Chat Completions shape (POST ``/v1/chat/completions``).
  This one shape covers OpenAI, OpenRouter, Kimi/Moonshot, xAI, Groq, and most
  API-key providers, so a user brings any of them with no per-vendor code.
- ``anthropic_messages`` — the Anthropic Messages shape (POST ``/v1/messages``),
  for a Claude **API key** (never a subscription — see
  ``anthropic-forbids-third-party-subscription-oauth``).

These functions are DELIBERATELY pure and credential-free: they build the request
BODY + PATH only. The bearer credential is applied INSIDE the credential-blind
broker worker (design §3 / Codex: never a vendor SDK on an arbitrary ``base_url``),
so nothing here ever sees or embeds a secret. Fail loud on a malformed response —
never fabricate an empty (or whitespace-only) completion (Hard Rule #8).

The fail-loud contract governs the COMPLETION TEXT. Token ``usage`` is best-effort
OPTIONAL telemetry: absent or malformed usage fields decode to ``None`` (unknown) —
deliberately not a completion-shape failure, since many providers omit or vary usage
and a valid reply must not be discarded over metadata.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

# Canonical request paths per protocol. The host comes from the connection's
# allowlisted endpoint (the user's ``base_url``); these are the standard paths.
OPENAI_CHAT_PATH = "/v1/chat/completions"
ANTHROPIC_MESSAGES_PATH = "/v1/messages"

# Anthropic requires an explicit max_tokens; use a sane cap when the config leaves
# it None (mirrors the served per-call reservation intent, bounded per reply).
_DEFAULT_MAX_TOKENS = 4096


class ProtocolDecodeError(ValueError):
    """A provider response did not match the declared protocol shape."""


def reported_model(response_body: Any) -> str:
    """Optional model receipt shared by both wire protocols; empty means unknown.

    A requested alias is not evidence of which model answered. Keep remote
    metadata bounded and printable, but do not discard a valid completion when
    a compatible endpoint omits this optional field. This label is telemetry,
    never a provider identity, routing choice or grant of authority.
    """
    return model_receipt(response_body.get("model") if isinstance(response_body, dict) else None)


def model_receipt(value: Any) -> str:
    """Normalize an optional receipt value, independently of its wire location."""
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or not value.isprintable():
        return ""
    return value.strip()


def _messages(prompt: str, system: str) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


def encode_openai_chat(
    *, prompt: str, system: str, model: str, temperature: float | None = None,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(path, body)`` for an OpenAI Chat Completions request.

    Credential-free: the ``Authorization: Bearer`` header is applied by the broker
    worker, not here.
    """
    body: dict[str, Any] = {"model": model, "messages": _messages(prompt, system)}
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    return OPENAI_CHAT_PATH, body


def decode_openai_chat(response_body: Any) -> tuple[str, int | None, int | None]:
    """Return ``(text, input_tokens, output_tokens)`` from an OpenAI-shaped body.

    Raises :class:`ProtocolDecodeError` on any shape mismatch — never returns an
    empty completion silently (a blank reply that looks real is worse than a crash).
    """
    if not isinstance(response_body, dict):
        raise ProtocolDecodeError("openai_chat response is not a JSON object")
    if "error" in response_body:
        err = response_body.get("error")
        detail = err.get("message") if isinstance(err, dict) else str(err)
        raise ProtocolDecodeError(f"provider returned an error: {detail}")
    choices = response_body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProtocolDecodeError("openai_chat response has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    text = message.get("content") if isinstance(message, dict) else None
    # Whitespace-only content is a semantically empty reply — fail loud, don't pass it
    # off as a real completion (Codex review; Hard Rule #8).
    if not isinstance(text, str) or not text.strip():
        raise ProtocolDecodeError("openai_chat response has no assistant content")
    usage = response_body.get("usage")
    in_tok = out_tok = None
    if isinstance(usage, dict):
        in_tok = usage.get("prompt_tokens")
        out_tok = usage.get("completion_tokens")
        in_tok = in_tok if isinstance(in_tok, int) else None
        out_tok = out_tok if isinstance(out_tok, int) else None
    return text, in_tok, out_tok


def encode_anthropic_messages(
    *, prompt: str, system: str, model: str, temperature: float | None = None,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(path, body)`` for an Anthropic Messages request (API key only).

    ``system`` is a top-level field (not a message) in the Anthropic shape.
    ``max_tokens`` is REQUIRED by the API, so it is always set.
    """
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens if isinstance(max_tokens, int) and max_tokens > 0
        else _DEFAULT_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    if temperature is not None:
        body["temperature"] = temperature
    return ANTHROPIC_MESSAGES_PATH, body


def decode_anthropic_messages(response_body: Any) -> tuple[str, int | None, int | None]:
    """Return ``(text, input_tokens, output_tokens)`` from an Anthropic-shaped body."""
    if not isinstance(response_body, dict):
        raise ProtocolDecodeError("anthropic_messages response is not a JSON object")
    if response_body.get("type") == "error" or "error" in response_body:
        err = response_body.get("error")
        detail = err.get("message") if isinstance(err, dict) else str(err)
        raise ProtocolDecodeError(f"provider returned an error: {detail}")
    content = response_body.get("content")
    if not isinstance(content, list) or not content:
        raise ProtocolDecodeError("anthropic_messages response has no content")
    text_parts = [
        block.get("text")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    text = "".join(p for p in text_parts if p)
    if not text.strip():  # whitespace-only is a semantically empty reply — fail loud
        raise ProtocolDecodeError("anthropic_messages response has no text block")
    usage = response_body.get("usage")
    in_tok = out_tok = None
    if isinstance(usage, dict):
        in_tok = usage.get("input_tokens")
        out_tok = usage.get("output_tokens")
        in_tok = in_tok if isinstance(in_tok, int) else None
        out_tok = out_tok if isinstance(out_tok, int) else None
    return text, in_tok, out_tok


@dataclass(frozen=True, slots=True)
class AgentCodec:
    """Installed wire capability, not a remote claim or inference grant."""

    encode: Callable
    decode: Callable


@dataclass(frozen=True, slots=True)
class WireProtocol:
    encode: Callable
    decode: Callable
    headers: tuple[tuple[str, str], ...] = ()
    agent_factory: Callable[[], AgentCodec] | None = None
    request_validator: Callable[[dict], None] | None = None
    request_fields: frozenset[str] = frozenset()
    legacy_request_validator: Callable[[dict], None] | None = None


def _validate_chat_request(body, *, legacy=False):
    """Installed wire structure only; no knowledge of a source's extensions."""
    import math

    is_object = isinstance(body, dict) if legacy else type(body) is dict
    if not is_object or not {"model", "messages"} <= body.keys() <= {
        "model", "messages", "temperature", "max_tokens", "tools", "tool_choice",
    }:
        raise ValueError("unsupported constrained wire body")
    if not legacy and "max_tokens" in body and (type(body["max_tokens"]) is not int
                                 or not 1 <= body["max_tokens"] <= 10**18):
        raise ValueError("invalid constrained wire output limit")
    if not legacy and "temperature" in body:
        value = body["temperature"]
        try:
            valid = type(value) in (float, int) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("invalid constrained wire temperature")
    if "tools" in body or "tool_choice" in body:
        from tinyassets.providers.agent_chat_codec import validate_agent_body

        validate_agent_body(body)
        return
    model, messages = body["model"], body["messages"]
    if legacy:
        if not isinstance(model, str) or not isinstance(messages, list) or any(
            not isinstance(message, dict) or message.keys() != {"role", "content"}
            or message["role"] not in ("system", "user", "assistant")
            or not isinstance(message["content"], str) for message in messages
        ):
            raise ValueError("unsupported constrained wire messages")
        return
    if (type(model) is not str or not model or len(model) > 200
            or not model.isprintable() or model != model.strip()
            or type(messages) is not list or any(
                type(message) is not dict or message.keys() != {"role", "content"}
                or message["role"] not in ("system", "user", "assistant")
                or type(message["content"]) is not str for message in messages)):
        raise ValueError("unsupported constrained wire messages")


def _chat_agent_codec() -> AgentCodec:
    # Installed envelope capability, separate from canonical history validation.
    from tinyassets.providers.agent_wire_codec import installed_agent_wire

    shape = installed_agent_wire()
    return AgentCodec(shape.encode, shape.decode)

#: The Anthropic Messages API REQUIRES an ``anthropic-version`` request header
#: (independent of the api key). Pinned to the stable GA version.
ANTHROPIC_VERSION = "2023-06-01"

#: Protocol -> static (credential-free) request headers the executor must send on
#: every call, beyond the auth header the broker applies from the connection's
#: auth_scheme. anthropic_messages needs ``anthropic-version`` or the API 400s; the
#: api key itself rides the connection's auth (auth_scheme="header",
#: header_name="x-api-key" for Anthropic — never in these static headers).
PROTOCOLS = {
    "openai_chat": WireProtocol(
        encode_openai_chat, decode_openai_chat, agent_factory=_chat_agent_codec,
        request_validator=_validate_chat_request,
        legacy_request_validator=partial(_validate_chat_request, legacy=True),
        request_fields=frozenset({"model", "messages", "temperature", "max_tokens",
                                  "tools", "tool_choice"}),
    ),
    "anthropic_messages": WireProtocol(
        encode_anthropic_messages, decode_anthropic_messages,
        headers=(("anthropic-version", ANTHROPIC_VERSION),),
    ),
}

# Preserve legacy text-only lookup shapes. Agent readiness is a separate,
# optional local capability and never changes a legacy text encoder's contract.
ENCODERS = {key: (value.encode, value.decode) for key, value in PROTOCOLS.items()}
STATIC_HEADERS = {key: dict(value.headers) for key, value in PROTOCOLS.items()}


def agent_codec_for(protocol: str) -> AgentCodec | None:
    """Resolve installed full-agent support independently of source branding."""
    contract = PROTOCOLS.get(protocol)
    if contract is None or contract.agent_factory is None:
        return None
    return contract.agent_factory()


def static_headers_for(protocol: str) -> dict[str, str]:
    """Static request headers for a protocol (empty for an unknown one)."""
    return dict(STATIC_HEADERS.get(protocol, {}))
