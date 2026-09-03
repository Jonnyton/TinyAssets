"""Fail-closed OpenAI Realtime client-secret broker for the shared app.

Realtime is an auxiliary speech transport, never a TinyAssets writer.  This
module knows nothing about conversation authoring: the browser's only session
tool calls the existing authenticated ``converse`` MCP operation.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

REALTIME_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"
REALTIME_MODEL = "gpt-realtime-2.1"
VOICE_DISCLOSURE_VERSION = 2
VOICE_SESSION_MAX_SECONDS = 30 * 60
VOICE_MINT_WINDOW_SECONDS = 60.0
VOICE_MINTS_PER_WINDOW = 10
_TIMEOUT = 15.0
_TRUTHY = {"1", "true", "yes", "on"}
_mint_buckets: dict[str, tuple[float, int]] = {}

ClientFactory = Callable[[], httpx.AsyncClient]


class RealtimeVoiceError(RuntimeError):
    """A stable, secret-free failure suitable for the app boundary."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def realtime_voice_enabled() -> bool:
    """True only when the adapter and its host-side kill switch are enabled.

    These flags make the adapter reachable; they are not spend authority.  A
    compatible resource explicitly bound to the requesting universe remains
    mandatory.
    """

    return _truthy("TINYASSETS_REALTIME_VOICE_ENABLED") and _truthy(
        "TINYASSETS_ALLOW_REALTIME_VOICE_API"
    )


def public_voice_config() -> dict[str, Any]:
    """Non-secret configuration injected into the shared browser client."""

    return {
        "enabled": realtime_voice_enabled(),
        "model": REALTIME_MODEL,
        "calls_url": REALTIME_CALLS_URL,
        "disclosure_version": VOICE_DISCLOSURE_VERSION,
        "max_session_seconds": VOICE_SESSION_MAX_SECONDS,
    }


def voice_capability(universe_dir: str | Path | None) -> dict[str, Any]:
    """Return a secret-free view of this universe's voice capability.

    OpenAI's public Realtime API documents API credentials as its authority.
    A Codex/ChatGPT subscription binding is therefore not treated as a
    compatible Realtime credential.  That is an adapter limitation, not a
    license to borrow a process-global or maintainer credential.
    """

    if not realtime_voice_enabled():
        return {"available": False, "state": "disabled", "reason": "voice_disabled"}
    if universe_dir is None:
        return {
            "available": False,
            "state": "locked",
            "reason": "no_home_universe",
        }

    from tinyassets.credential_vault import resolve_llm_api_key

    if resolve_llm_api_key(universe_dir, "OPENAI_API_KEY"):
        return {
            "available": True,
            "state": "ready",
            "resource": "user_bound_openai_api_credential",
        }
    return {
        "available": False,
        "state": "locked",
        "reason": "voice_compatible_resource_required",
    }


def allow_client_secret_mint(user_id: str, *, now: float | None = None) -> bool:
    """Bound accidental/replayed session creation for one authenticated owner."""

    moment = time.monotonic() if now is None else now
    start, count = _mint_buckets.get(user_id, (moment, 0))
    if moment - start >= VOICE_MINT_WINDOW_SECONDS:
        start, count = moment, 0
    if count >= VOICE_MINTS_PER_WINDOW:
        return False
    _mint_buckets[user_id] = (start, count + 1)
    return True


def session_request() -> dict[str, Any]:
    """Server-owned Realtime session policy; the browser cannot widen it."""

    return {
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": (
                "You are only the speech interface for a TinyAssets universe. "
                "For each completed user utterance, call converse exactly once "
                "with the user's intended words. Never answer as the universe. "
                "After converse returns, speak only its result and add nothing."
            ),
            "audio": {
                "input": {
                    "turn_detection": {
                        "type": "semantic_vad",
                        "eagerness": "medium",
                        "create_response": True,
                        "interrupt_response": True,
                    }
                },
                "output": {"voice": "marin"},
            },
            "tools": [
                {
                    "type": "function",
                    "name": "converse",
                    "description": (
                        "Send the founder's complete spoken turn to their "
                        "TinyAssets universe and receive its canonical reply."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "The founder's complete utterance.",
                            }
                        },
                        "required": ["message"],
                        "additionalProperties": False,
                    },
                }
            ],
            "tool_choice": "required",
        }
    }


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT)


async def mint_client_secret(
    universe_dir: str | Path,
    *,
    client_factory: ClientFactory = _default_client,
) -> dict[str, Any]:
    """Mint one scoped ephemeral secret from the owner's deposited API key.

    No process-global key is consulted.  Returned data is deliberately reduced
    to the temporary bearer and the minimum public metadata the client needs.
    """

    if not realtime_voice_enabled():
        raise RealtimeVoiceError("voice_disabled", 404)

    from tinyassets.credential_vault import resolve_llm_api_key

    api_key = resolve_llm_api_key(universe_dir, "OPENAI_API_KEY")
    if not api_key:
        raise RealtimeVoiceError("voice_compatible_resource_required", 409)

    try:
        async with client_factory() as client:
            response = await client.post(
                REALTIME_CLIENT_SECRETS_URL,
                json=session_request(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise RealtimeVoiceError("voice_provider_unreachable", 502) from exc

    if response.status_code == 429:
        raise RealtimeVoiceError("voice_provider_rate_limited", 503)
    if response.status_code in {401, 403}:
        raise RealtimeVoiceError("voice_openai_credential_rejected", 409)
    if not response.is_success:
        raise RealtimeVoiceError("voice_provider_failed", 502)

    try:
        payload = response.json()
    except ValueError as exc:
        raise RealtimeVoiceError("voice_provider_bad_response", 502) from exc
    value = str(payload.get("value") or "") if isinstance(payload, dict) else ""
    if not 20 <= len(value) <= 4096:
        raise RealtimeVoiceError("voice_provider_bad_response", 502)
    try:
        expires_at = int(payload.get("expires_at") or 0)
    except (TypeError, ValueError):
        expires_at = 0

    return {
        "value": value,
        "expires_at": expires_at,
        "model": REALTIME_MODEL,
        "calls_url": REALTIME_CALLS_URL,
        "max_session_seconds": VOICE_SESSION_MAX_SECONDS,
    }


__all__ = [
    "REALTIME_CALLS_URL",
    "REALTIME_CLIENT_SECRETS_URL",
    "REALTIME_MODEL",
    "RealtimeVoiceError",
    "allow_client_secret_mint",
    "mint_client_secret",
    "public_voice_config",
    "realtime_voice_enabled",
    "session_request",
    "voice_capability",
]
