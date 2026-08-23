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
never fabricate an empty completion (Hard Rule #8).
"""

from __future__ import annotations

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
    if not isinstance(text, str) or not text:
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
    if not text:
        raise ProtocolDecodeError("anthropic_messages response has no text block")
    usage = response_body.get("usage")
    in_tok = out_tok = None
    if isinstance(usage, dict):
        in_tok = usage.get("input_tokens")
        out_tok = usage.get("output_tokens")
        in_tok = in_tok if isinstance(in_tok, int) else None
        out_tok = out_tok if isinstance(out_tok, int) else None
    return text, in_tok, out_tok


# Protocol -> (encoder, decoder) dispatch. The api_key_http executor selects by the
# ProviderDefinition.protocol; there is no per-vendor branch.
ENCODERS = {
    "openai_chat": (encode_openai_chat, decode_openai_chat),
    "anthropic_messages": (encode_anthropic_messages, decode_anthropic_messages),
}
